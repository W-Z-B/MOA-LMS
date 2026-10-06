"""The calendar (item 2.32): my events for a period, and a private feed for a phone's calendar.

The feed is an address with a secret in it. Whoever has the address can read the calendar, so it says only
what is on the calendar (titles, times, places, meeting links), never marks or messages; it needs no
session and no authenticator code, because a phone calendar cannot sign in. Its owner can rotate the secret
(the old address stops working at once) or turn the feed off. Each address, and each network address, may
read it only so often (FeedThrottle).
"""

import hashlib
import secrets
from datetime import timedelta

from django.http import HttpResponse
from django.urls import path
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from audit.services import record_event
from calendars import services
from calendars.models import CalendarFeed
from core.serializers import ErrorSerializer
from iam.permissions import RolePermission

DEFAULT_BEFORE = timedelta(days=7)
DEFAULT_AFTER = timedelta(days=60)
LONGEST = timedelta(days=400)
FEED_BEFORE = timedelta(days=30)
FEED_AFTER = timedelta(days=180)


class EventSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(
        choices=["assignment_due", "quiz_closes", "practical_closes", "class_session", "release"]
    )
    id = serializers.IntegerField(help_text="The id of the assignment, quiz, task, session, module or item")
    site = serializers.IntegerField()
    site_code = serializers.CharField()
    title = serializers.CharField()
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField(allow_null=True)
    location = serializers.CharField()
    meeting_url = serializers.CharField()
    link = serializers.CharField(help_text="Where it is in the web app")


def _when(value: str | None, default):
    if not value:
        return default
    parsed = parse_datetime(value)
    if parsed is None:
        raise serializers.ValidationError({"detail": f"“{value}” is not a date and time."})
    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)


@extend_schema(
    parameters=[
        OpenApiParameter("from", OpenApiTypes.DATETIME, description="Start; a week ago when empty"),
        OpenApiParameter("to", OpenApiTypes.DATETIME, description="End; 60 days ahead when empty"),
    ],
    responses={200: EventSerializer(many=True), 400: OpenApiTypes.OBJECT},
    summary="My calendar: due dates, class sessions and release dates I can see, at most 400 days at once",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def calendar(request):
    now = timezone.now()
    start = _when(request.query_params.get("from"), now - DEFAULT_BEFORE)
    end = _when(request.query_params.get("to"), now + DEFAULT_AFTER)
    if end <= start or end - start > LONGEST:
        return Response(
            {"code": "bad_period", "detail": "Choose an end after the start, at most 400 days later."},
            status=400,
        )
    return Response([e.as_dict() for e in services.events(request.user, start, end)])


class FeedSerializer(serializers.Serializer):
    url = serializers.CharField(
        allow_null=True, help_text="Add this address to a phone calendar; keep it private"
    )
    created_at = serializers.DateTimeField(allow_null=True)
    last_used_at = serializers.DateTimeField(allow_null=True)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _feed_body(request, feed: CalendarFeed | None) -> dict:
    if feed is None:
        return {"url": None, "created_at": None, "last_used_at": None}
    url = request.build_absolute_uri(f"/api/v1/calendar/feed/{feed.token}.ics")
    return {"url": url, "created_at": feed.created_at, "last_used_at": feed.last_used_at}


@extend_schema(
    methods=["GET"], responses=FeedSerializer, summary="My private calendar feed address, if I have one"
)
@extend_schema(
    methods=["POST"],
    request=None,
    responses={201: FeedSerializer},
    summary="Make my private feed address, or make a new one: the old address stops working at once",
)
@extend_schema(methods=["DELETE"], request=None, responses={204: None}, summary="Turn my calendar feed off")
@api_view(["GET", "POST", "DELETE"])
@permission_classes([RolePermission])
def feed_settings(request):
    feed = CalendarFeed.objects.filter(user=request.user).first()
    if request.method == "GET":
        return Response(_feed_body(request, feed))
    if request.method == "DELETE":
        if feed is not None:
            feed.delete()
            record_event(request, "calendar_feed_off", "calendars.calendarfeed")
        return Response(status=204)
    token = secrets.token_urlsafe(32)
    if feed is None:
        feed = CalendarFeed(user=request.user)
    feed.token, feed.token_hash, feed.last_used_at = token, _hash(token), None
    feed.created_at = timezone.now()
    feed.save()
    record_event(request, "calendar_feed_made", "calendars.calendarfeed")
    return Response(_feed_body(request, feed), status=201)


class FeedThrottle(SimpleRateThrottle):
    """At most 30 reads an hour for one feed address: phone calendars refresh every few hours."""

    rate = "30/hour"
    scope = "calendar_feed"

    def get_cache_key(self, request, view):
        return f"throttle_calendar_feed_{_hash(view.kwargs.get('token', ''))[:32]}"


class FeedAddressThrottle(SimpleRateThrottle):
    """At most 120 reads an hour from one network address, whatever the feed: guessing addresses is slow."""

    rate = "120/hour"
    scope = "calendar_feed_address"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


@extend_schema(
    auth=[],
    responses={
        (200, "text/calendar"): OpenApiResponse(OpenApiTypes.STR, description="The calendar as iCalendar"),
        404: ErrorSerializer,
        429: ErrorSerializer,
    },
    summary="A person's calendar as an iCalendar feed, for phone calendars. No sign-in: the secret address "
    "is the key. Read-only and rate-limited",
)
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([FeedAddressThrottle, FeedThrottle])
def feed(request, token: str):
    found = CalendarFeed.objects.select_related("user").filter(token_hash=_hash(token)).first()
    if found is None or not found.user.is_active:
        return Response({"code": "not_found", "detail": "No such calendar feed."}, status=404)
    CalendarFeed.objects.filter(pk=found.pk).update(last_used_at=timezone.now())
    now = timezone.now()
    items = services.events(found.user, now - FEED_BEFORE, now + FEED_AFTER)
    origin = request.build_absolute_uri("/").rstrip("/")
    response = HttpResponse(services.ical(items, origin), content_type="text/calendar; charset=utf-8")
    response["Cache-Control"] = "private, max-age=900"
    return response


urlpatterns = [
    path("calendar/", calendar, name="calendar"),
    path("calendar/feed/", feed_settings, name="calendar-feed-settings"),
    path("calendar/feed/<str:token>.ics", feed, name="calendar-feed"),
]
