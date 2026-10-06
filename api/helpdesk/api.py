"""Asking for help (item 7.17).

- Anyone signed in sends a help request from the page they are on: a subject, what they need, and the page's
  address, which the web app fills in. It reaches the course administrators (those of the person's campus,
  and those for every campus) as an "Action required" notification and in their To do. With no course
  administrator yet, it goes to the administrators, so a request never goes unread.
- Sending takes an Idempotency-Key (practicals.offline): a phone without signal keeps the request and sends
  it when the signal returns, and sending it twice changes nothing.
- A person sends at most HELP_REQUESTS_PER_HOUR in an hour, so a stuck button cannot flood the administrators.
- Course administrators and administrators see every request and answer it; the answer is sent to the person
  as a notification. Nobody answers their own request. Everyone else sees only their own requests.
- Every request and every answer is in the audit log.
"""

import re
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from audit.services import record, snapshot
from core.serializers import ErrorSerializer
from courses.access import person_of
from helpdesk.models import HelpRequest
from iam.models import Role
from iam.permissions import RolePermission
from iam.services import SITE_ADMIN_ROLES, has_role
from notifications.models import Notification
from notifications.services import notify, users_with_role
from practicals.offline import IDEMPOTENCY_HEADER, check_client_time, idempotent

# An address inside the web app: a path with an optional query, never another site.
PAGE = re.compile(r"^/[A-Za-z0-9/_\-.=&%?]*$")


class TooManyRequests(APIException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_code = "too_many_help_requests"


class AlreadyAnswered(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "already_answered"


def name_of(user) -> str | None:
    if user is None:
        return None
    person = person_of(user)
    return person.full_name if person is not None else (user.get_full_name() or user.get_username())


def answerers(asker):
    """Who a request goes to: the course administrators of the person's campus and of every campus; the
    administrators when there are none."""
    person = person_of(asker)
    campus = person.campus_code if person is not None and person.campus_code else None
    for code in (Role.COURSE_ADMIN, Role.ADMINISTRATOR):
        people = users_with_role(code, campus_code=campus).exclude(pk=asker.pk)
        if people.exists():
            return people
    return users_with_role(Role.ADMINISTRATOR).none()


class HelpRequestSerializer(serializers.ModelSerializer):
    asked_by_name = serializers.SerializerMethodField()
    answered_by_name = serializers.SerializerMethodField()
    mine = serializers.SerializerMethodField(help_text="True when the reader sent it")

    class Meta:
        model = HelpRequest
        fields = [
            "id",
            "subject",
            "message",
            "page",
            "status",
            "asked_by_name",
            "created_at",
            "client_sent_at",
            "answer",
            "answered_by_name",
            "answered_at",
            "mine",
        ]
        read_only_fields = fields

    def get_asked_by_name(self, obj) -> str | None:
        return name_of(obj.asked_by)

    def get_answered_by_name(self, obj) -> str | None:
        return name_of(obj.answered_by)

    def get_mine(self, obj) -> bool:
        return obj.asked_by_id == self.context["request"].user.pk


class AskSerializer(serializers.Serializer):
    subject = serializers.CharField(max_length=160)
    message = serializers.CharField(max_length=4000)
    page = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    client_sent_at = serializers.DateTimeField(
        required=False, allow_null=True, help_text="When it was written on the phone"
    )

    def validate_subject(self, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise serializers.ValidationError("Say in a few words what you need help with.")
        return value

    def validate_message(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("Say what you were trying to do and what happened.")
        return value.strip()

    def validate_page(self, value: str) -> str:
        value = value.strip()
        if value and not PAGE.match(value):
            raise serializers.ValidationError("The page must be an address inside the LMS, such as /sites/4.")
        return value


class AnswerSerializer(serializers.Serializer):
    answer = serializers.CharField(max_length=4000)

    def validate_answer(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("Write the answer to send.")
        return value.strip()


class HelpRequestViewSet(viewsets.GenericViewSet):
    """Help requests: one's own, or, for course administrators and administrators, everyone's."""

    permission_classes = [RolePermission]
    serializer_class = HelpRequestSerializer
    queryset = HelpRequest.objects.none()

    def get_queryset(self):
        qs = HelpRequest.objects.select_related("asked_by__person", "answered_by__person")
        if has_role(self.request.user, *SITE_ADMIN_ROLES):
            return qs
        return qs.filter(asked_by=self.request.user)

    @extend_schema(
        parameters=[
            OpenApiParameter("status", OpenApiTypes.STR, enum=["open", "answered"], description="Only these"),
            OpenApiParameter("mine", OpenApiTypes.BOOL, description="Only the requests I sent"),
        ],
        responses=HelpRequestSerializer(many=True),
        summary="Help requests: my own, or every request for those who answer them, the newest first",
    )
    def list(self, request):
        qs = self.get_queryset()
        if request.query_params.get("status") in HelpRequest.Status.values:
            qs = qs.filter(status=request.query_params["status"])
        if request.query_params.get("mine") in ("1", "true"):
            qs = qs.filter(asked_by=request.user)
        return Response(HelpRequestSerializer(qs[:200], many=True, context={"request": request}).data)

    @extend_schema(responses={200: HelpRequestSerializer, 404: ErrorSerializer}, summary="One help request")
    def retrieve(self, request, pk=None):
        item = get_object_or_404(self.get_queryset(), pk=pk)
        return Response(HelpRequestSerializer(item, context={"request": request}).data)

    @extend_schema(
        request=AskSerializer,
        parameters=[IDEMPOTENCY_HEADER],
        responses={
            201: HelpRequestSerializer,
            400: OpenApiTypes.OBJECT,
            409: ErrorSerializer,
            429: ErrorSerializer,
        },
        summary="Ask for help from the page I am on; the course administrators are told",
    )
    @idempotent
    def create(self, request):
        data = AskSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        client_sent_at = check_client_time(v.get("client_sent_at"))
        since = timezone.now() - timedelta(hours=1)
        sent = HelpRequest.objects.filter(asked_by=request.user, created_at__gte=since).count()
        if sent >= settings.HELP_REQUESTS_PER_HOUR:
            raise TooManyRequests(
                f"You have sent {sent} help requests in the last hour. The course administrators have them; "
                "wait for an answer, or try again later."
            )
        with transaction.atomic():
            item = HelpRequest.objects.create(
                asked_by=request.user,
                subject=v["subject"],
                message=v["message"],
                page=v["page"],
                client_sent_at=client_sent_at,
                created_by=request.user,
                updated_by=request.user,
            )
            record(request, "create", item, after=snapshot(item))
            asker = name_of(request.user)
            where = f" (from {item.page})" if item.page else ""
            notify(
                answerers(request.user),
                title=f"Help request from {asker}: {item.subject}"[:160],
                body=f"{item.message}{where}",
                link=f"/help/requests/{item.pk}",
                kind=Notification.Kind.APPROVAL,
                dedupe_key=f"help:{item.pk}",
            )
        return Response(HelpRequestSerializer(item, context={"request": request}).data, status=201)

    @extend_schema(
        request=AnswerSerializer,
        responses={
            200: HelpRequestSerializer,
            400: OpenApiTypes.OBJECT,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
        summary="Answer a help request; the person who asked is sent the answer",
    )
    @action(detail=True, methods=["post"])
    def answer(self, request, pk=None):
        if not has_role(request.user, *SITE_ADMIN_ROLES):
            raise PermissionDenied("Course administrators and administrators answer help requests.")
        data = AnswerSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            item = get_object_or_404(self.get_queryset().select_for_update(of=("self",)), pk=pk)
            if item.asked_by_id == request.user.pk:
                raise PermissionDenied("Someone else answers your own help request.")
            if item.status == HelpRequest.Status.ANSWERED:
                raise AlreadyAnswered(f"{name_of(item.answered_by)} has already answered this request.")
            before = snapshot(item)
            item.status = HelpRequest.Status.ANSWERED
            item.answer = data.validated_data["answer"]
            item.answered_by = request.user
            item.answered_at = timezone.now()
            item.updated_by = request.user
            item.save()
            record(request, "answered", item, before=before, after=snapshot(item))
            notify(
                [item.asked_by],
                title=f"Your help request is answered: {item.subject}"[:160],
                body=item.answer,
                link="/help/requests",
                dedupe_key=f"help-answer:{item.pk}",
            )
        return Response(HelpRequestSerializer(item, context={"request": request}).data)


router = DefaultRouter()
router.register("help-requests", HelpRequestViewSet, basename="help-request")
urlpatterns = router.urls
