"""Session login, logout, current user, TOTP multi-factor enrolment and verification, the list of
signed-in devices, and passwords: a link to choose one on a new account or when forgotten (item 1.22), and a
change by the signed-in person."""

from datetime import timedelta

import pyotp
from django.conf import settings
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from audit.services import record
from core.net import client_ip
from core.serializers import ErrorSerializer
from iam.accounts import (
    LINK_KINDS,
    accounts_for,
    link_kind,
    never_used,
    send_invitation,
    send_reset,
    user_from_link,
)
from iam.models import LoginAttempt, PasswordResetRequest, TotpDevice, UserSession
from iam.permissions import MFA_SESSION_KEY
from iam.services import account_locked, address_blocked, person_payload, requires_mfa, role_codes
from iam.sessions import close_sessions, describe_device, end_sessions
from privacy.services import notice_due


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)


class CodeSerializer(serializers.Serializer):
    code = serializers.CharField(min_length=6, max_length=8)


class MeSerializer(serializers.Serializer):
    """Describes _me_payload for the API documentation."""

    id = serializers.IntegerField()
    username = serializers.CharField()
    name = serializers.CharField()
    roles = serializers.ListField(child=serializers.CharField(), help_text="System role codes held")
    is_superuser = serializers.BooleanField()
    mfa_required = serializers.BooleanField()
    mfa_verified = serializers.BooleanField(help_text="True only once an authenticator code was given")
    person_id = serializers.IntegerField(allow_null=True)
    person_kind = serializers.CharField(allow_null=True, help_text="staff or student")
    external_id = serializers.CharField(
        allow_null=True, help_text="HRMS employee number or SRMS student number"
    )
    privacy_notice_due = serializers.IntegerField(
        allow_null=True, help_text="Version of the privacy notice still to be read, or null"
    )
    persona = serializers.ChoiceField(
        choices=["admin", "course_admin", "lecturer", "student", "office"], help_text="Which Home to show"
    )
    title = serializers.CharField(help_text="The role in words, for example 'Lecturer, AGR101'")


class MfaEnrolSerializer(serializers.Serializer):
    provisioning_uri = serializers.CharField(help_text="otpauth:// address to add to an authenticator app")


class SessionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    device = serializers.CharField(help_text="Browser and system, for example 'Chrome on Android'")
    ip = serializers.IPAddressField(allow_null=True)
    created_at = serializers.DateTimeField(help_text="When this session signed in")
    last_seen_at = serializers.DateTimeField()
    current = serializers.BooleanField(help_text="The session making this request")


class EndedSerializer(serializers.Serializer):
    ended = serializers.IntegerField()


def _me_payload(user, session) -> dict:
    from core.home import persona, title  # Home reads the courses, which read iam: import when used

    return {
        "id": user.id,
        "username": user.get_username(),
        "name": user.get_full_name() or user.get_username(),
        "roles": sorted(role_codes(user)),
        "is_superuser": bool(user.is_superuser),
        "mfa_required": requires_mfa(user),
        "mfa_verified": bool(session.get(MFA_SESSION_KEY, False)),
        "privacy_notice_due": notice_due(user),  # the notice version still to read (item 1.18)
        "persona": persona(user),  # which Home to show, and the role in words (items 2.07 to 2.09)
        "title": title(user),
        **person_payload(user),
    }


@extend_schema(
    request=LoginSerializer,
    responses={200: MeSerializer, 401: ErrorSerializer, 423: ErrorSerializer, 429: ErrorSerializer},
    summary="Sign in with a username and password",
)
@ensure_csrf_cookie
@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    data = LoginSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    username = data.validated_data["username"]
    address = client_ip(request)
    if address_blocked(address):
        return Response(
            {
                "code": "too_many_attempts",
                "detail": "Too many failed sign-ins from this network. "
                f"Try again in {settings.LOGIN_LOCKOUT_MINUTES} minutes.",
            },
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    if account_locked(username):
        return Response(
            {
                "code": "locked_out",
                "detail": f"Too many failed attempts. Try again in {settings.LOGIN_LOCKOUT_MINUTES} minutes.",
            },
            status=status.HTTP_423_LOCKED,
        )
    user = authenticate(request, username=username, password=data.validated_data["password"])
    LoginAttempt.objects.create(username=username, source_ip=address, success=user is not None)
    if user is None:
        return Response(
            {"code": "invalid_credentials", "detail": "Username or password is incorrect."}, status=401
        )
    login(request, user)
    # Set only by an authenticator code. A session never counts as verified merely because its roles did
    # not need a code at sign-in: a role that needs one, given later, must still ask for it.
    request.session[MFA_SESSION_KEY] = False
    record(request, "login", user)
    return Response(_me_payload(user, request.session))


@extend_schema(request=None, responses={204: None}, summary="Sign out of this session")
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request):
    record(request, "logout", request.user)
    logout(request)
    return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(responses=MeSerializer, summary="The signed-in user, their roles and verification state")
@ensure_csrf_cookie
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me_view(request):
    return Response(_me_payload(request.user, request.session))


@extend_schema(
    request=None,
    responses={200: MfaEnrolSerializer, 409: ErrorSerializer},
    summary="Start authenticator enrolment",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mfa_enrol(request):
    """Create (or reuse an unconfirmed) TOTP secret and return the provisioning URI."""
    device, _ = TotpDevice.objects.get_or_create(
        user=request.user, defaults={"secret": pyotp.random_base32()}
    )
    if device.is_confirmed:
        return Response({"code": "already_enrolled", "detail": "A confirmed device exists."}, status=409)
    uri = pyotp.TOTP(device.secret).provisioning_uri(name=request.user.get_username(), issuer_name="GSA LMS")
    return Response({"provisioning_uri": uri})


@extend_schema(
    request=CodeSerializer,
    responses={200: MeSerializer, 400: ErrorSerializer, 409: ErrorSerializer},
    summary="Verify an authenticator code for this session",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mfa_verify(request):
    """Confirm enrolment on first use, and mark the session as MFA-verified on every use."""
    data = CodeSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    device = TotpDevice.objects.filter(user=request.user).first()
    if device is None:
        return Response({"code": "not_enrolled", "detail": "Enrol a device first."}, status=409)
    if not pyotp.TOTP(device.secret).verify(data.validated_data["code"], valid_window=1):
        record(request, "mfa_failed", request.user)
        return Response({"code": "invalid_code", "detail": "The code is not valid."}, status=400)
    if not device.is_confirmed:
        device.confirmed_at = timezone.now()
        device.save(update_fields=["confirmed_at", "updated_at"])
    request.session[MFA_SESSION_KEY] = True
    record(request, "mfa_verified", request.user)
    return Response(_me_payload(request.user, request.session))


@extend_schema(responses=SessionSerializer(many=True), summary="Where I am signed in")
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def sessions_view(request):
    current = request.session.session_key
    rows = [
        {
            "id": row.id,
            "device": describe_device(row.user_agent),
            "ip": row.ip,
            "created_at": row.created_at,
            "last_seen_at": row.last_seen_at,
            "current": row.session_key == current,
        }
        for row in UserSession.objects.filter(user=request.user)
    ]
    return Response(SessionSerializer(rows, many=True).data)


@extend_schema(
    request=None,
    responses={204: None, 404: ErrorSerializer, 409: ErrorSerializer},
    summary="End one of my other sessions",
)
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def end_session_view(request, pk: int):
    target = UserSession.objects.filter(user=request.user, pk=pk)
    row = target.first()
    if row is None:
        return Response({"code": "not_found", "detail": "No such session."}, status=status.HTTP_404_NOT_FOUND)
    if row.session_key == request.session.session_key:
        return Response(
            {"code": "current_session", "detail": "This is the session you are using. Sign out to end it."},
            status=status.HTTP_409_CONFLICT,
        )
    end_sessions(target)
    record(
        request,
        "session_ended",
        request.user,
        after={"session": pk, "device": describe_device(row.user_agent)},
    )
    return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(request=None, responses=EndedSerializer, summary="End all my sessions except this one")
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def end_other_sessions_view(request):
    others = UserSession.objects.filter(user=request.user).exclude(session_key=request.session.session_key)
    ended = end_sessions(others)
    record(request, "sessions_ended", request.user, after={"ended": ended})
    return Response({"ended": ended})


# ---------------------------------------------------------------------------------------------------------
# Passwords (item 1.22, ported from the HRMS): a link to choose one on a new account or when forgotten, and
# a change by the signed-in person.


class ForgotPasswordSerializer(serializers.Serializer):
    login = serializers.CharField(max_length=254, help_text="Username or email address")


class PasswordLinkSerializer(serializers.Serializer):
    uid = serializers.CharField(max_length=64)
    token = serializers.CharField(max_length=128)


class PasswordSetSerializer(PasswordLinkSerializer):
    password = serializers.CharField(trim_whitespace=False, max_length=128)


class LinkSerializer(serializers.Serializer):
    username = serializers.CharField()
    kind = serializers.ChoiceField(choices=LINK_KINDS)


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(trim_whitespace=False, max_length=128)
    new_password = serializers.CharField(trim_whitespace=False, max_length=128)


class DetailSerializer(serializers.Serializer):
    detail = serializers.CharField()


LINK_ON_ITS_WAY = (
    "If that is the username or email address of an account, a link to choose a new password is on its way "
    "to the email address on the account. The link works once."
)
INVALID_LINK = {
    "code": "invalid_link",
    "detail": "This link has expired or has already been used. Ask for a new one from the sign-in page.",
}


def _window_start():
    return timezone.now() - timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)


def _check_new_password(password: str, user, field: str) -> None:
    try:
        validate_password(password, user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError({field: list(exc.messages)}) from exc


@extend_schema(
    request=ForgotPasswordSerializer,
    responses={200: DetailSerializer, 429: ErrorSerializer},
    summary="Ask for a link to choose a new password",
)
@api_view(["POST"])
@permission_classes([AllowAny])
def forgot_password_view(request):
    """The answer is the same whether or not an account matches, so it never tells who has an account.

    One address may ask PASSWORD_RESETS_PER_ADDRESS times in the lockout window, and one account is sent
    PASSWORD_RESETS_PER_ACCOUNT links in it; asking more often sends nothing more.
    """
    data = ForgotPasswordSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    address = client_ip(request)
    since = _window_start()
    asked = PasswordResetRequest.objects.filter(source_ip=address, at__gte=since).count() if address else 0
    if asked >= settings.PASSWORD_RESETS_PER_ADDRESS:
        return Response(
            {
                "code": "too_many_attempts",
                "detail": "Too many requests from this network. "
                f"Try again in {settings.LOGIN_LOCKOUT_MINUTES} minutes.",
            },
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    found = accounts_for(data.validated_data["login"])
    if not found:
        PasswordResetRequest.objects.create(user=None, source_ip=address)
    for user in found:
        already = PasswordResetRequest.objects.filter(user=user, at__gte=since).count()
        PasswordResetRequest.objects.create(user=user, source_ip=address)
        if already >= settings.PASSWORD_RESETS_PER_ACCOUNT:
            continue  # enough links are on their way; more would only fill the inbox
        kind = "invitation" if never_used(user) else "reset"
        emailed = send_invitation(user) if kind == "invitation" else send_reset(user)
        record(request, "password_link_sent", user, after={"kind": kind, "emailed": emailed, "asked": "self"})
    return Response({"detail": LINK_ON_ITS_WAY})


@extend_schema(
    request=PasswordLinkSerializer,
    responses={200: LinkSerializer, 400: ErrorSerializer},
    summary="Whether a password link still works, and the username it is for",
)
@api_view(["POST"])
@permission_classes([AllowAny])
def check_link_view(request):
    data = PasswordLinkSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    user = user_from_link(data.validated_data["uid"])
    kind = link_kind(user, data.validated_data["token"])
    if kind is None:
        return Response(INVALID_LINK, status=status.HTTP_400_BAD_REQUEST)
    return Response({"username": user.get_username(), "kind": kind})


@extend_schema(
    request=PasswordSetSerializer,
    responses={200: LinkSerializer, 400: ErrorSerializer},
    summary="Choose a password through an emailed link (an invitation or a reset)",
)
@api_view(["POST"])
@permission_classes([AllowAny])
def set_password_view(request):
    """Sets the password, ends every session the account had, and lifts a lockout: the link proves the
    person. The link then stops working, because it was signed over the old password."""
    data = PasswordSetSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    user = user_from_link(data.validated_data["uid"])
    kind = link_kind(user, data.validated_data["token"])
    if kind is None:
        return Response(INVALID_LINK, status=status.HTTP_400_BAD_REQUEST)
    _check_new_password(data.validated_data["password"], user, "password")
    with transaction.atomic():
        user.set_password(data.validated_data["password"])
        user.save(update_fields=["password"])
        LoginAttempt.objects.create(username=user.get_username(), source_ip=client_ip(request), success=True)
        ended = close_sessions(user)
        record(request, "password_set", user, after={"link": kind, "sessions_ended": ended})
    return Response({"username": user.get_username(), "kind": kind})


@extend_schema(
    request=PasswordChangeSerializer,
    responses={200: EndedSerializer, 400: ErrorSerializer},
    summary="Change my password; my other sessions end, this one stays signed in",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def change_password_view(request):
    data = PasswordChangeSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    user = request.user
    if not user.check_password(data.validated_data["current_password"]):
        record(request, "password_change_failed", user)
        return Response(
            {"code": "wrong_password", "detail": "Your current password is not right."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    _check_new_password(data.validated_data["new_password"], user, "new_password")
    with transaction.atomic():
        user.set_password(data.validated_data["new_password"])
        user.save(update_fields=["password"])
        current = request.session.session_key
        ended = end_sessions(UserSession.objects.filter(user=user).exclude(session_key=current))
        update_session_auth_hash(request, user)  # a new session key, so this browser stays signed in
        UserSession.objects.filter(session_key=current).update(session_key=request.session.session_key)
        record(request, "password_changed", user, after={"sessions_ended": ended})
    return Response({"ended": ended})
