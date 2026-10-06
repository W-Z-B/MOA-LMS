"""Own notifications: list (unread first), mark one or all as read; settings; push to this device."""

from django.conf import settings
from django.db import transaction
from django.urls import path
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from audit.services import masked, record
from core.serializers import ErrorSerializer
from notifications import push
from notifications.models import Notification, NotificationPreference, PushSubscription


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ("id", "kind", "title", "body", "link", "created_at", "read_at")


class NotificationListSerializer(serializers.Serializer):
    unread = serializers.IntegerField(help_text="How many are unread in all")
    results = NotificationSerializer(many=True)


class MarkedSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    read = serializers.BooleanField()


class MarkedAllSerializer(serializers.Serializer):
    marked = serializers.IntegerField(help_text="How many were marked as read")


@extend_schema(
    parameters=[OpenApiParameter("unread", OpenApiTypes.STR, enum=["1"], description="1 lists unread only")],
    responses=NotificationListSerializer,
    summary="My notifications, unread first (at most 100)",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_notifications(request):
    qs = Notification.objects.filter(recipient=request.user)
    if request.query_params.get("unread") == "1":
        qs = qs.filter(read_at__isnull=True)
    rows = qs.order_by("read_at", "-created_at")[:100]
    unread = Notification.objects.filter(recipient=request.user, read_at__isnull=True).count()
    return Response({"unread": unread, "results": NotificationSerializer(rows, many=True).data})


@extend_schema(
    request=None, responses={200: MarkedSerializer, 404: ErrorSerializer}, summary="Mark one as read"
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mark_read(request, pk: int):
    updated = Notification.objects.filter(recipient=request.user, pk=pk, read_at__isnull=True).update(
        read_at=timezone.now()
    )
    if not updated and not Notification.objects.filter(recipient=request.user, pk=pk).exists():
        return Response({"code": "not_found", "detail": "No such notification."}, status=404)
    return Response({"id": pk, "read": True})


@extend_schema(request=None, responses=MarkedAllSerializer, summary="Mark all of mine as read")
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mark_all_read(request):
    count = Notification.objects.filter(recipient=request.user, read_at__isnull=True).update(
        read_at=timezone.now()
    )
    return Response({"marked": count})


class PreferenceSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=Notification.Kind.choices)
    label = serializers.CharField(read_only=True)
    in_app = serializers.BooleanField(
        read_only=True, help_text="Always true: every notification is in the app"
    )
    email = serializers.ChoiceField(
        choices=NotificationPreference.Email.choices, help_text="instant, daily (in the summary) or off"
    )
    push = serializers.BooleanField(
        help_text="Also a push notice to each installed app the person turned push on in (item 4.04)"
    )


def _preferences(user) -> list[dict]:
    held = {p.kind: p for p in NotificationPreference.objects.filter(user=user)}
    rows = []
    for kind, label in Notification.Kind.choices:
        pref = held.get(kind)
        rows.append(
            {
                "kind": kind,
                "label": label,
                "in_app": True,
                "email": pref.email if pref else NotificationPreference.Email.INSTANT,
                "push": pref.push if pref else False,
            }
        )
    return rows


@extend_schema(
    methods=["GET"],
    responses=PreferenceSerializer(many=True),
    summary="My notification settings, one row per kind of notification (item 2.33)",
)
@extend_schema(
    methods=["PUT"],
    request=PreferenceSerializer(many=True),
    responses={200: PreferenceSerializer(many=True), 400: ErrorSerializer},
    summary="Change my notification settings; kinds not sent keep their setting",
)
@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated])
def preferences(request):
    if request.method == "PUT":
        data = PreferenceSerializer(data=request.data, many=True)
        data.is_valid(raise_exception=True)
        for row in data.validated_data:
            NotificationPreference.objects.update_or_create(
                user=request.user, kind=row["kind"], defaults={"email": row["email"], "push": row["push"]}
            )
    return Response(_preferences(request.user))


class PushStateSerializer(serializers.Serializer):
    available = serializers.BooleanField(help_text="Whether this LMS sends push notices (VAPID keys are set)")
    public_key = serializers.CharField(
        allow_null=True, help_text="The applicationServerKey the browser subscribes with (base64url)"
    )
    devices = serializers.IntegerField(help_text="How many of the person's installed apps receive push")


class KeysSerializer(serializers.Serializer):
    p256dh = serializers.CharField(max_length=200)
    auth = serializers.CharField(max_length=60)


class SubscribeSerializer(serializers.Serializer):
    """A browser's PushSubscription as PushSubscription.toJSON() gives it, and which device it is."""

    endpoint = serializers.URLField(max_length=1000)
    keys = KeysSerializer()
    device = serializers.CharField(max_length=120, required=False, allow_blank=True)

    def validate_endpoint(self, value):
        if not push.allowed_endpoint(value):
            raise serializers.ValidationError("This browser's push service is not one the LMS sends to.")
        return value


class UnsubscribeSerializer(serializers.Serializer):
    endpoint = serializers.URLField(max_length=1000)


def _push_state(user) -> dict:
    return {
        "available": push.configured(),
        "public_key": settings.VAPID_PUBLIC_KEY or None,
        "devices": PushSubscription.objects.filter(user=user).count(),
    }


def _audit_entry(subscription) -> dict:
    """What the audit log keeps of a subscription: the device in words; the endpoint only as a fingerprint."""
    return {"device": subscription.device, "endpoint": masked(subscription.endpoint)}


@extend_schema(
    responses=PushStateSerializer, summary="Whether push notices can be turned on, and the key (item 4.04)"
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def push_state(request):
    return Response(_push_state(request.user))


@extend_schema(
    request=SubscribeSerializer,
    responses={201: PushStateSerializer, 400: ErrorSerializer, 409: ErrorSerializer},
    summary="Turn push notices on for this installed app (item 4.04)",
    description="Send the browser's PushSubscription. Which kinds of notification are pushed is chosen in "
    "the notification settings (push). Only the push services in PUSH_SERVICE_HOSTS are accepted.",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def push_subscribe(request):
    if not push.configured():
        return Response(
            {"code": "push_off", "detail": "This LMS does not send push notices yet."}, status=409
        )
    data = SubscribeSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    sent = data.validated_data
    with transaction.atomic():
        # One browser, one subscription: a browser now used by someone else is theirs from now on.
        existing = PushSubscription.objects.select_for_update().filter(endpoint=sent["endpoint"]).first()
        if existing is not None and existing.user_id != request.user.id:
            record(request, "delete", existing, before=_audit_entry(existing), entity_id=existing.pk)
            existing.delete()
            existing = None
        subscription = existing or PushSubscription(user=request.user, endpoint=sent["endpoint"])
        subscription.p256dh, subscription.auth = sent["keys"]["p256dh"], sent["keys"]["auth"]
        subscription.device = sent.get("device", "")[:120]
        subscription.failures = 0
        subscription.save()
        if existing is None:
            record(request, "create", subscription, after=_audit_entry(subscription))
    return Response(_push_state(request.user), status=201)


@extend_schema(
    request=UnsubscribeSerializer,
    responses={200: PushStateSerializer, 400: ErrorSerializer},
    summary="Turn push notices off for this installed app",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def push_unsubscribe(request):
    data = UnsubscribeSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    with transaction.atomic():
        for subscription in PushSubscription.objects.filter(
            user=request.user, endpoint=data.validated_data["endpoint"]
        ):
            record(
                request, "delete", subscription, before=_audit_entry(subscription), entity_id=subscription.pk
            )
            subscription.delete()
    return Response(_push_state(request.user))


urlpatterns = [
    path("push/", push_state, name="notification-push"),
    path("push/subscribe/", push_subscribe, name="notification-push-subscribe"),
    path("push/unsubscribe/", push_unsubscribe, name="notification-push-unsubscribe"),
    path("", list_notifications, name="notification-list"),
    path("preferences/", preferences, name="notification-preferences"),
    path("read-all/", mark_all_read, name="notification-read-all"),
    path("<int:pk>/read/", mark_read, name="notification-read"),
]
