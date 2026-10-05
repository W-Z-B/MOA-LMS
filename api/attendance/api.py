"""Class sessions and attendance (items 4.14 and 4.15, decision D6 / ADR 0008).

- Teaching staff put class sessions on a site: a time, a place or an https meeting link, the recording link
  afterwards. Members see the sessions of the whole class and of their own groups (and on the calendar).
- The lecturer takes the register on a phone, for many students at once, offline if need be: every write
  takes an Idempotency-Key and the phone's time (practicals.offline). When two records for one student
  meet, the one made later by the time the person acted wins, so a register sent from the queue an hour
  late never overwrites a student's check-in made after it.
- Students check in by scanning the code shown in the room (attendance.codes): it changes every few seconds
  and is refused 60 seconds after it was made; one check-in per student per session.
- Totals per student; for a course whose programme makes attendance a condition, a course administrator
  turns on sending to the SRMS and teaching staff send the totals (integration.srms.push_attendance).
"""

from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import serializers
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import APIException, NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from attendance import codes, services
from attendance.models import AttendancePolicy, AttendanceRecord, ClassSession
from audit.services import record, record_event, snapshot
from core.serializers import ErrorSerializer
from courses.access import TaughtRecord, can_teach, person_of, site_role, visible_sites
from courses.api import TeachingViewSet, require_teaching
from courses.models import CourseSite, Membership, SiteGroup
from iam.permissions import RolePermission
from iam.services import SITE_ADMIN_ROLES, has_role
from people.models import PersonRef
from practicals.offline import IDEMPOTENCY_HEADER, IdempotentWrites, check_client_time, idempotent

CHECK_IN_OPENS_BEFORE = timedelta(minutes=15)


class Refused(APIException):
    status_code = 409
    default_code = "refused"


class ClassSessionSerializer(serializers.ModelSerializer):
    site = TaughtRecord(CourseSite)
    group = TaughtRecord(
        SiteGroup,
        "site",
        required=False,
        allow_null=True,
        help_text="For one group only; empty for the whole class",
    )
    site_code = serializers.CharField(source="site.code", read_only=True)
    my_status = serializers.SerializerMethodField(help_text="A student's own attendance, if recorded")

    class Meta:
        model = ClassSession
        fields = (
            "id",
            "site",
            "site_code",
            "group",
            "title",
            "starts_at",
            "ends_at",
            "location",
            "meeting_url",
            "recording_url",
            "takes_attendance",
            "my_status",
        )

    def validate(self, attrs):
        site = attrs.get("site") or self.instance.site
        if self.instance is not None and "site" in attrs and attrs["site"].pk != self.instance.site_id:
            raise serializers.ValidationError({"site": ["A session stays on its course."]})
        group = attrs.get("group")
        if group is not None and group.site_id != site.id:
            raise serializers.ValidationError({"group": ["Choose a group of the same course."]})
        starts = attrs.get("starts_at", getattr(self.instance, "starts_at", None))
        ends = attrs.get("ends_at", getattr(self.instance, "ends_at", None))
        if starts and ends and ends <= starts:
            raise serializers.ValidationError({"ends_at": ["The class must end after it starts."]})
        return attrs

    def get_my_status(self, obj) -> str | None:
        request = self.context.get("request")
        person = person_of(request.user) if request else None
        if person is None:
            return None
        return (
            AttendanceRecord.objects.filter(session=obj, student=person)
            .values_list("status", flat=True)
            .first()
        )


class RegisterEntrySerializer(serializers.Serializer):
    student = serializers.IntegerField(help_text="Person id")
    status = serializers.ChoiceField(choices=AttendanceRecord.Status.choices)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True)


class RegisterWriteSerializer(serializers.Serializer):
    records = RegisterEntrySerializer(many=True, allow_empty=False)
    client_recorded_at = serializers.DateTimeField(
        required=False, allow_null=True, help_text="When the register was taken on the phone"
    )


class RegisterRowSerializer(serializers.Serializer):
    person_id = serializers.IntegerField()
    student_no = serializers.CharField()
    name = serializers.CharField()
    status = serializers.CharField(allow_null=True, help_text="Null when not recorded")
    how = serializers.CharField(allow_null=True)
    acted_at = serializers.DateTimeField(allow_null=True)
    note = serializers.CharField()


class RegisterSavedSerializer(serializers.Serializer):
    saved = serializers.IntegerField()
    kept = serializers.ListField(
        child=serializers.IntegerField(),
        help_text="Students whose record was made later than this register and so was kept",
    )
    register = RegisterRowSerializer(many=True)


class ClosedSerializer(serializers.Serializer):
    marked_absent = serializers.IntegerField()


class CheckInCodeSerializer(serializers.Serializer):
    code = serializers.CharField(help_text="Show it in the room, as a QR code and as text")
    valid_seconds = serializers.IntegerField()
    expires_at = serializers.DateTimeField()


class CheckInSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=40)


class CheckedInSerializer(serializers.Serializer):
    session = serializers.IntegerField()
    status = serializers.CharField()


def _moment(value: str, name: str):
    parsed = parse_datetime(value)
    if parsed is None:
        raise serializers.ValidationError({name: [f"“{value}” is not a date and time."]})
    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)


def _register(session: ClassSession) -> list[dict]:
    records = {r.student_id: r for r in session.records.all()}
    rows = []
    for membership in services.expected(session).order_by("person__last_name", "person__first_name"):
        person, rec = membership.person, records.get(membership.person_id)
        rows.append(
            {
                "person_id": person.id,
                "student_no": person.external_id,
                "name": person.full_name,
                "status": rec.status if rec else None,
                "how": rec.how if rec else None,
                "acted_at": rec.acted_at if rec else None,
                "note": rec.note if rec else "",
            }
        )
    return RegisterRowSerializer(rows, many=True).data


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter("site", OpenApiTypes.INT, description="Only this site"),
            OpenApiParameter("from", OpenApiTypes.DATETIME, description="Only sessions ending after this"),
            OpenApiParameter("to", OpenApiTypes.DATETIME, description="Only sessions starting before this"),
        ],
        summary="Class sessions I can see",
    )
)
class ClassSessionViewSet(IdempotentWrites, TeachingViewSet):
    """Class sessions with their meeting link and recording. Teaching staff manage them."""

    serializer_class = ClassSessionSerializer

    def get_queryset(self):
        sites = visible_sites(self.request.user)
        params = self.request.query_params
        if params.get("site"):
            sites = sites.filter(pk=params["site"])
        if self.action != "list":  # one session: settled by session_visible on the object itself
            return ClassSession.objects.filter(site__in=visible_sites(self.request.user)).select_related(
                "site"
            )
        qs = services.sessions_for(self.request.user, sites).select_related("site")
        if params.get("from"):
            qs = qs.filter(ends_at__gte=_moment(params["from"], "from"))
        if params.get("to"):
            qs = qs.filter(starts_at__lte=_moment(params["to"], "to"))
        return qs.order_by("starts_at", "id")

    def get_object(self):
        session = super().get_object()
        if not services.session_visible(self.request.user, session):
            raise NotFound()
        return session

    def site_of(self, instance):
        return instance.site

    def site_from_data(self, data):
        return data["site"]

    def get_serializer_class(self):
        return {"check_in": CheckInSerializer}.get(self.action, ClassSessionSerializer)

    def _taught(self) -> ClassSession:
        session = self.get_object()
        require_teaching(self.request.user, session.site)
        return session

    @extend_schema(
        methods=["GET"],
        responses={200: RegisterRowSerializer(many=True), 403: ErrorSerializer, 404: ErrorSerializer},
        summary="The register: every student expected, with what is recorded (teaching staff and auditors)",
    )
    @extend_schema(
        methods=["POST"],
        request=RegisterWriteSerializer,
        parameters=[IDEMPOTENCY_HEADER],
        responses={
            200: RegisterSavedSerializer,
            400: OpenApiTypes.OBJECT,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
        summary="Take the register for many students at once, from a phone and offline if need be",
    )
    @action(detail=True, methods=["get", "post"])
    def register(self, request, pk=None):
        if request.method == "GET":
            session = self.get_object()
            if site_role(request.user, session.site) not in ("auditor",) and not can_teach(
                request.user, session.site
            ):
                raise PermissionDenied("Only teaching staff see the register.")
            return Response(_register(session))
        return self._take_register(request)

    @idempotent
    def _take_register(self, request):
        session = self._taught()
        data = RegisterWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        client_time = check_client_time(data.validated_data.get("client_recorded_at"))
        acted = client_time or timezone.now()
        expected = {m.person_id for m in services.expected(session)}
        entries = data.validated_data["records"]
        unknown = [e["student"] for e in entries if e["student"] not in expected]
        if unknown:
            raise serializers.ValidationError(
                {"records": [f"Not expected at this class: person {', '.join(map(str, unknown))}."]}
            )
        saved, kept = 0, []
        with transaction.atomic():
            existing = {r.student_id: r for r in session.records.select_for_update()}
            for entry in entries:
                current = existing.get(entry["student"])
                if current is not None and current.acted_at > acted:
                    kept.append(entry["student"])
                    continue
                values = {
                    "status": entry["status"],
                    "how": AttendanceRecord.How.REGISTER,
                    "acted_at": acted,
                    "client_recorded_at": client_time,
                    "note": entry.get("note", ""),
                    "recorded_by": request.user,
                    "updated_by": request.user,
                }
                if current is None:
                    rec = AttendanceRecord.objects.create(
                        session=session, student_id=entry["student"], created_by=request.user, **values
                    )
                    record(request, "create", rec, after=snapshot(rec))
                else:
                    before = snapshot(current)
                    for name, value in values.items():
                        setattr(current, name, value)
                    current.save()
                    record(request, "update", current, before=before, after=snapshot(current))
                saved += 1
        return Response({"saved": saved, "kept": kept, "register": _register(session)})

    @extend_schema(
        request=None,
        parameters=[IDEMPOTENCY_HEADER],
        responses={200: ClosedSerializer, 403: ErrorSerializer, 404: ErrorSerializer, 409: ErrorSerializer},
        summary="Close the register: every expected student with no record is marked absent",
    )
    @action(detail=True, methods=["post"], url_path="close-register")
    @idempotent
    def close_register(self, request, pk=None):
        session = self._taught()
        if session.starts_at > timezone.now():
            raise Refused("The class has not started yet.", code="not_started")
        marked = 0
        with transaction.atomic():
            done = set(session.records.values_list("student_id", flat=True))
            for membership in services.expected(session):
                if membership.person_id in done:
                    continue
                rec = AttendanceRecord.objects.create(
                    session=session,
                    student=membership.person,
                    status=AttendanceRecord.Status.ABSENT,
                    how=AttendanceRecord.How.CLOSED,
                    acted_at=timezone.now(),
                    recorded_by=request.user,
                    created_by=request.user,
                    updated_by=request.user,
                )
                record(request, "create", rec, after=snapshot(rec))
                marked += 1
        return Response({"marked_absent": marked})

    @extend_schema(
        responses={
            200: CheckInCodeSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
        summary="A fresh check-in code to show in the room; valid for ATTENDANCE_CODE_SECONDS (60). "
        "Ask for a new one every 20 seconds or so",
    )
    @action(detail=True, methods=["get"], url_path="check-in-code")
    def check_in_code(self, request, pk=None):
        session = self._taught()
        _check_in_open(session)
        code, seconds = codes.make(session.id)
        return Response(
            {
                "code": code,
                "valid_seconds": seconds,
                "expires_at": timezone.now() + timedelta(seconds=seconds),
            }
        )

    @extend_schema(
        request=CheckInSerializer,
        responses={
            201: CheckedInSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
        summary="Check in to a class with the code shown in the room (students). Once per class",
    )
    @action(detail=True, methods=["post"], url_path="check-in")
    def check_in(self, request, pk=None):
        session = self.get_object()
        person = person_of(request.user)
        if site_role(request.user, session.site) != Membership.SiteRole.STUDENT or person is None:
            raise PermissionDenied("Only students of the course check in.")
        if not services.expected(session).filter(person=person).exists():
            raise PermissionDenied("This class is for another group.")
        _check_in_open(session)
        data = CheckInSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        problem = codes.check(session.id, data.validated_data["code"])
        if problem == "expired":
            return Response(
                {
                    "code": "code_expired",
                    "detail": "That code has expired. Scan the code on the screen again.",
                },
                status=400,
            )
        if problem:
            return Response(
                {"code": "code_invalid", "detail": "That is not the code for this class. Scan it again."},
                status=400,
            )
        now = timezone.now()
        late_after = session.starts_at + timedelta(minutes=settings.ATTENDANCE_LATE_AFTER_MINUTES)
        status = AttendanceRecord.Status.PRESENT if now <= late_after else AttendanceRecord.Status.LATE
        try:
            with transaction.atomic():
                rec = AttendanceRecord.objects.create(
                    session=session,
                    student=person,
                    status=status,
                    how=AttendanceRecord.How.CHECK_IN,
                    acted_at=now,
                    recorded_by=request.user,
                    created_by=request.user,
                    updated_by=request.user,
                )
                record(request, "create", rec, after=snapshot(rec))
        except IntegrityError:
            raise Refused(
                "Your attendance at this class is already recorded.", code="already_recorded"
            ) from None
        return Response({"session": session.id, "status": status}, status=201)


def _check_in_open(session: ClassSession) -> None:
    now = timezone.now()
    if not session.takes_attendance:
        raise Refused("Attendance is not taken at this class.", code="no_attendance")
    if now < session.starts_at - CHECK_IN_OPENS_BEFORE or now > session.ends_at:
        raise Refused(
            "Check-in is open from 15 minutes before the class until it ends.", code="check_in_closed"
        )


# ---------------------------------------------------------------------------------------------------------
# Totals, the course's policy and sending to the SRMS


class TotalsRowSerializer(serializers.Serializer):
    person_id = serializers.IntegerField()
    student_no = serializers.CharField()
    name = serializers.CharField()
    sessions = serializers.IntegerField(help_text="Sessions held that take attendance")
    present = serializers.IntegerField()
    late = serializers.IntegerField()
    excused = serializers.IntegerField()
    absent = serializers.IntegerField()
    not_recorded = serializers.IntegerField()
    percent = serializers.CharField(allow_null=True, help_text="(present + late) / (present + late + absent)")


class PolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendancePolicy
        fields = ("send_to_srms", "minimum_percent", "last_sent_at")
        read_only_fields = ("last_sent_at",)


def _site(request, pk: int) -> CourseSite:
    return get_object_or_404(visible_sites(request.user), pk=pk)


@extend_schema(
    responses={200: TotalsRowSerializer(many=True), 404: ErrorSerializer},
    summary="Attendance totals: every student for teaching staff and auditors, my own for a student",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def site_totals(request, pk: int):
    site = _site(request, pk)
    role = site_role(request.user, site)
    if can_teach(request.user, site) or role == "auditor":
        return Response(services.totals(site))
    return Response(services.totals(site, only_person=person_of(request.user) or PersonRef(pk=0)))


@extend_schema(
    methods=["GET"],
    responses={200: PolicySerializer, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="Whether the course's attendance totals go to the SRMS (teaching staff, course administrators)",
)
@extend_schema(
    methods=["PUT"],
    request=PolicySerializer,
    responses={200: PolicySerializer, 400: OpenApiTypes.OBJECT, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="Set whether the programme makes attendance a condition, so totals go to the SRMS "
    "(course administrators)",
)
@api_view(["GET", "PUT"])
@permission_classes([RolePermission])
def site_policy(request, pk: int):
    site = _site(request, pk)
    if not (can_teach(request.user, site) or site_role(request.user, site) == "auditor"):
        raise PermissionDenied("Only teaching staff see the attendance policy.")
    policy = AttendancePolicy.objects.filter(site=site).first()
    if request.method == "GET":
        return Response(PolicySerializer(policy or AttendancePolicy(site=site)).data)
    if not has_role(request.user, *SITE_ADMIN_ROLES):
        raise PermissionDenied("The programme's rules are set by a course administrator.")
    data = PolicySerializer(policy, data=request.data)
    data.is_valid(raise_exception=True)
    with transaction.atomic():
        before = snapshot(policy) if policy else None
        stamps = {"updated_by": request.user} if policy else {"site": site, "created_by": request.user}
        policy = data.save(**stamps)
        record(request, "update" if before else "create", policy, before=before, after=snapshot(policy))
    return Response(PolicySerializer(policy).data)


class SentSerializer(serializers.Serializer):
    offering_code = serializers.CharField()
    skipped = serializers.CharField(required=False, help_text="Why nothing was sent")
    accepted = serializers.ListField(child=serializers.CharField(), required=False)
    locked = serializers.ListField(child=serializers.CharField(), required=False)
    unknown = serializers.ListField(child=serializers.CharField(), required=False)


@extend_schema(
    request=None,
    responses={200: SentSerializer, 403: ErrorSerializer, 404: ErrorSerializer, 502: ErrorSerializer},
    summary="Send the attendance totals to the SRMS now, for a course whose programme requires it",
)
@api_view(["POST"])
@permission_classes([RolePermission])
def send_to_srms(request, pk: int):
    from integration.client import IntegrationError
    from integration.srms import push_attendance

    site = _site(request, pk)
    require_teaching(request.user, site)
    try:
        answer = push_attendance(site)
    except IntegrationError as exc:
        record_event(request, "attendance_send_failed", "courses.coursesite", reason=str(exc))
        return Response(
            {
                "code": "srms_unavailable",
                "detail": "The SRMS could not take the totals now. Try again later.",
            },
            status=502,
        )
    if "skipped" not in answer:
        AttendancePolicy.objects.filter(site=site).update(last_sent_at=timezone.now())
    record_event(request, "attendance_sent", "courses.coursesite", after={"site": site.id, **answer})
    return Response(answer)


router = DefaultRouter()
router.register("class-sessions", ClassSessionViewSet, basename="class-session")
urlpatterns = [
    path("attendance/sites/<int:pk>/totals/", site_totals, name="attendance-totals"),
    path("attendance/sites/<int:pk>/policy/", site_policy, name="attendance-policy"),
    path("attendance/sites/<int:pk>/send-to-srms/", send_to_srms, name="attendance-send"),
    *router.urls,
]
