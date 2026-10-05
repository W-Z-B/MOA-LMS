"""Session login, logout, current user, and TOTP multi-factor enrolment and verification."""

from datetime import timedelta

import pyotp
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from audit.services import record
from core.serializers import ErrorSerializer
from iam.models import LoginAttempt, TotpDevice
from iam.permissions import MFA_SESSION_KEY
from iam.services import person_payload, requires_mfa, role_codes


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
    mfa_verified = serializers.BooleanField()
    person_id = serializers.IntegerField(allow_null=True, help_text="The person record of this account")
    person_kind = serializers.CharField(allow_null=True, help_text="staff or student")
    external_id = serializers.CharField(allow_null=True, help_text="Employee number or student number")


class EnrolSerializer(serializers.Serializer):
    provisioning_uri = serializers.CharField(help_text="otpauth:// address, shown as a QR code")


def _me_payload(user, session) -> dict:
    return {
        "id": user.id,
        "username": user.get_username(),
        "name": user.get_full_name() or user.get_username(),
        "roles": sorted(role_codes(user)),
        "is_superuser": bool(user.is_superuser),
        "mfa_required": requires_mfa(user),
        "mfa_verified": bool(session.get(MFA_SESSION_KEY, False)),
        **person_payload(user),
    }


def _source_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR") or None


def _is_locked(username: str) -> bool:
    """True when the account has reached the failure limit inside the lockout window."""
    window_start = timezone.now() - timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
    recent = LoginAttempt.objects.filter(username=username, at__gte=window_start).order_by("-at")
    failures = 0
    for attempt in recent[: settings.LOGIN_MAX_FAILURES]:
        if attempt.success:
            break
        failures += 1
    return failures >= settings.LOGIN_MAX_FAILURES


@extend_schema(
    request=LoginSerializer,
    responses={200: MeSerializer, 401: ErrorSerializer, 423: ErrorSerializer},
    summary="Sign in with a username and password",
)
@ensure_csrf_cookie
@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    data = LoginSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    username = data.validated_data["username"]
    if _is_locked(username):
        return Response(
            {
                "code": "locked_out",
                "detail": f"Too many failed attempts. Try again in {settings.LOGIN_LOCKOUT_MINUTES} minutes.",
            },
            status=status.HTTP_423_LOCKED,
        )
    user = authenticate(request, username=username, password=data.validated_data["password"])
    LoginAttempt.objects.create(username=username, source_ip=_source_ip(request), success=user is not None)
    if user is None:
        return Response(
            {"code": "invalid_credentials", "detail": "Username or password is incorrect."}, status=401
        )
    login(request, user)
    request.session[MFA_SESSION_KEY] = not requires_mfa(user)
    record(request, "login", user)
    return Response(_me_payload(user, request.session))


@extend_schema(request=None, responses={204: None}, summary="Sign out")
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
    responses={200: EnrolSerializer, 409: ErrorSerializer},
    summary="Start enrolling an authenticator app",
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
    summary="Check an authenticator code",
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
