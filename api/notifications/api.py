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
from notifications.models import Notification


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


urlpatterns = [
    path("", list_notifications, name="notification-list"),
    path("read-all/", mark_all_read, name="notification-read-all"),
    path("<int:pk>/read/", mark_read, name="notification-read"),
]
