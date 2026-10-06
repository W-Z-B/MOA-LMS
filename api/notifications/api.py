"""Own notifications: list (unread first), mark one or all as read."""

from django.urls import path
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.serializers import ErrorSerializer
from notifications.models import Notification, NotificationPreference


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
    push = serializers.BooleanField(help_text="Phone push; kept now, sent once push notices arrive")


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


urlpatterns = [
    path("", list_notifications, name="notification-list"),
    path("preferences/", preferences, name="notification-preferences"),
    path("read-all/", mark_all_read, name="notification-read-all"),
    path("<int:pk>/read/", mark_read, name="notification-read"),
]
