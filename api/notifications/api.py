"""Own notifications: list (unread first), mark one or all as read."""

from django.urls import path
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from notifications.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ("id", "kind", "title", "body", "link", "created_at", "read_at")


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_notifications(request):
    qs = Notification.objects.filter(recipient=request.user)
    if request.query_params.get("unread") == "1":
        qs = qs.filter(read_at__isnull=True)
    rows = qs.order_by("read_at", "-created_at")[:100]
    unread = Notification.objects.filter(recipient=request.user, read_at__isnull=True).count()
    return Response({"unread": unread, "results": NotificationSerializer(rows, many=True).data})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mark_read(request, pk: int):
    updated = Notification.objects.filter(recipient=request.user, pk=pk, read_at__isnull=True).update(
        read_at=timezone.now()
    )
    if not updated and not Notification.objects.filter(recipient=request.user, pk=pk).exists():
        return Response({"code": "not_found", "detail": "No such notification."}, status=404)
    return Response({"id": pk, "read": True})


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
