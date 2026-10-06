"""Item 1.10: one's own sign-in email address: seeing it, asking to change it, and confirming the change from
the link sent to the new address. Ported from the HRMS (iam/email_views.py)."""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from audit.services import record
from core.net import client_ip
from core.serializers import ErrorSerializer
from iam import email_change
from iam.models import LoginAttempt
from iam.services import account_locked, address_blocked

CONFLICTS = frozenset({"taken"})


class PendingEmailSerializer(serializers.Serializer):
    new_email = serializers.EmailField()
    expires_at = serializers.DateTimeField(help_text="The link sent to it works until then")


class SignInEmailSerializer(serializers.Serializer):
    email = serializers.CharField(allow_blank=True, help_text="Where links to choose a password go")
    pending = PendingEmailSerializer(allow_null=True, help_text="A change waiting for its confirmation")


class EmailChangeSerializer(serializers.Serializer):
    email = serializers.EmailField(help_text="The new address")
    password = serializers.CharField(trim_whitespace=False, max_length=128, help_text="Your password")


class EmailAskedSerializer(serializers.Serializer):
    detail = serializers.CharField()
    emailed = serializers.BooleanField(help_text="Whether the link could be sent")
    pending = PendingEmailSerializer()


class EmailConfirmSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=100)


class EmailConfirmedSerializer(serializers.Serializer):
    detail = serializers.CharField()
    email = serializers.EmailField()


def pending_of(user) -> dict | None:
    change = email_change.pending_for(user)
    return {"new_email": change.new_email, "expires_at": change.expires_at} if change else None


def refused(exc: email_change.Refused) -> Response:
    code = status.HTTP_409_CONFLICT if exc.code in CONFLICTS else status.HTTP_400_BAD_REQUEST
    return Response({"code": exc.code, "detail": exc.detail}, status=code)


@extend_schema(responses=SignInEmailSerializer, summary="My sign-in email address, and any change waiting")
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def email_view(request):
    return Response({"email": request.user.email or "", "pending": pending_of(request.user)})


@extend_schema(
    request=EmailChangeSerializer,
    responses={200: EmailAskedSerializer, 400: ErrorSerializer, 409: ErrorSerializer, 429: ErrorSerializer},
    summary="Change my sign-in email address: a link goes to the new one, and the old one is told",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def change_email_view(request):
    """The password is asked for; a wrong one counts towards the sign-in lockout, as at sign-in."""
    data = EmailChangeSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    user = request.user
    address = client_ip(request)
    if account_locked(user.get_username()) or address_blocked(address):
        return Response(
            {"code": "too_many_attempts", "detail": "Too many wrong passwords. Try again later."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    if not user.check_password(data.validated_data["password"]):
        LoginAttempt.objects.create(username=user.get_username(), source_ip=address, success=False)
        record(request, "email_change_failed", user)
        return Response(
            {"code": "wrong_password", "detail": "Your password is not right."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    LoginAttempt.objects.create(username=user.get_username(), source_ip=address, success=True)
    try:
        change, sent = email_change.ask(request, user, data.validated_data["email"])
    except email_change.Refused as exc:
        return refused(exc)
    if sent:
        detail = (
            f"A link to confirm it was sent to {change.new_email}. The address changes only when the link "
            "is followed."
        )
    else:
        detail = f"The link could not be sent to {change.new_email}. Check the address, then ask again."
    return Response({"detail": detail, "emailed": sent, "pending": pending_of(user)})


@extend_schema(
    request=EmailConfirmSerializer,
    responses={200: EmailConfirmedSerializer, 400: ErrorSerializer, 409: ErrorSerializer},
    summary="Confirm a new sign-in email address, from the link sent to it",
    auth=[],
)
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def confirm_email_view(request):
    """Open to whoever holds the link, signed in or not: holding it shows they read mail at that address."""
    data = EmailConfirmSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    try:
        change = email_change.confirm(request, data.validated_data["token"])
    except email_change.Refused as exc:
        return refused(exc)
    return Response(
        {"detail": f"The sign-in email address is now {change.new_email}.", "email": change.new_email}
    )
