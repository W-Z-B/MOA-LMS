"""Insight endpoints: course analytics (6.01), progress (6.02), learning outcomes (3.11), early alerts (6.05)
and the reports that leave a course (6.03, 6.04, 6.06).

Inside a site, teaching staff and course administrators read the analytics, everyone's progress, the
outcomes and the alerts; a student reads only their own progress, from released marks, and never an alert.
The reports are read by the roles named in insights.reports, for the rows their grants cover.
"""

from datetime import date

from django.db import IntegrityError, transaction
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from assessments.models import Assignment
from audit.services import record, record_event, snapshot
from core.serializers import ErrorSerializer
from courses.access import TEACHING, person_of, site_role, taught_sites, visible_sites
from courses.models import CourseSite, Membership
from iam.permissions import RolePermission
from iam.services import SITE_ADMIN_ROLES, has_role
from insights import analytics, outcomes, reports
from insights.alerts import DEFAULTS
from insights.models import Alert, AlertRule, Outcome, OutcomeLink
from messaging.models import Conversation
from quizzes.models import Question
from rubrics.models import RubricCriterion

# ---------------------------------------------------------------------------------------------------------
# Shapes, for the API documentation


class ItemUseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    module = serializers.CharField()
    kind = serializers.CharField()
    is_published = serializers.BooleanField()
    opened = serializers.IntegerField(help_text="Students who have opened, downloaded or completed it")
    opened_percent = serializers.CharField(allow_null=True)
    downloads = serializers.IntegerField(allow_null=True, help_text="Downloads by students; files only")


class AssignmentUseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    due_at = serializers.DateTimeField()
    handed_in = serializers.IntegerField()
    handed_in_percent = serializers.CharField(allow_null=True)
    late = serializers.IntegerField()
    missing = serializers.IntegerField(help_text="Students past their due date with nothing handed in")
    marked = serializers.IntegerField()
    released = serializers.IntegerField()
    average_percent = serializers.CharField(allow_null=True)
    lowest_percent = serializers.CharField(allow_null=True)
    highest_percent = serializers.CharField(allow_null=True)


class QuizUseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    closes_at = serializers.DateTimeField(allow_null=True)
    is_practice = serializers.BooleanField()
    students_attempted = serializers.IntegerField()
    attempted_percent = serializers.CharField(allow_null=True)
    attempts = serializers.IntegerField()
    average_percent = serializers.CharField(allow_null=True)
    statistics = serializers.CharField(help_text="The web address of the quiz's question statistics")


class AnalyticsSerializer(serializers.Serializer):
    site = serializers.IntegerField()
    students = serializers.IntegerField()
    items = ItemUseSerializer(many=True)
    assignments = AssignmentUseSerializer(many=True)
    quizzes = QuizUseSerializer(many=True)
    not_recorded = serializers.CharField()


class ProgressRowSerializer(serializers.Serializer):
    person_id = serializers.IntegerField()
    student_no = serializers.CharField()
    name = serializers.CharField()
    items_total = serializers.IntegerField(help_text="Items the student can see")
    items_done = serializers.IntegerField()
    items_percent = serializers.CharField(allow_null=True)
    work_done = serializers.IntegerField(help_text="Work handed in, quizzes taken, practicals observed")
    work_missed = serializers.IntegerField(help_text="Past its due date with nothing handed in")
    work_to_come = serializers.IntegerField()
    work_marked = serializers.IntegerField()
    coursework_percent = serializers.CharField(allow_null=True)
    last_seen = serializers.DateTimeField(allow_null=True, help_text="Latest recorded activity on the site")
    last_signed_in = serializers.DateTimeField(allow_null=True)
    open_alerts = serializers.IntegerField(required=False, help_text="Teaching staff only")


class StandingSerializer(serializers.Serializer):
    standing = serializers.ChoiceField(choices=["met", "not_yet", "no_evidence"])
    percent = serializers.CharField(allow_null=True)
    evidence = serializers.ListField(child=serializers.DictField())


class OutcomeHeadSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()
    text = serializers.CharField()
    source = serializers.CharField()
    links = serializers.IntegerField()


class StudentStandingsSerializer(serializers.Serializer):
    person_id = serializers.IntegerField()
    student_no = serializers.CharField()
    name = serializers.CharField()
    outcomes = serializers.DictField(child=StandingSerializer(), help_text="By outcome id")


class StandingsSerializer(serializers.Serializer):
    met_percent = serializers.IntegerField()
    outcomes = OutcomeHeadSerializer(many=True)
    students = StudentStandingsSerializer(many=True)


class StudentProgressSerializer(ProgressRowSerializer):
    work = serializers.ListField(child=serializers.DictField(), help_text="Each piece of work and its state")
    outcomes = StandingsSerializer()


class OutcomeLinkSerializer(serializers.ModelSerializer):
    kind = serializers.CharField(read_only=True)
    title = serializers.SerializerMethodField()

    class Meta:
        model = OutcomeLink
        fields = ("id", "outcome", "kind", "assignment", "question", "criterion", "title")
        read_only_fields = ("outcome",)

    def get_title(self, obj) -> str:
        if obj.assignment_id:
            return obj.assignment.title
        if obj.question_id:
            return f"Question: {obj.question.name}"
        return f"{obj.criterion.rubric.title}: {obj.criterion.title}"


class OutcomeSerializer(serializers.ModelSerializer):
    links = serializers.SerializerMethodField()

    class Meta:
        model = Outcome
        fields = ("id", "code", "text", "source", "position", "links")
        read_only_fields = ("source",)

    def get_links(self, obj) -> list[dict]:
        site = self.context["site"]
        rows = obj.links.filter(site=site).select_related("assignment", "question", "criterion__rubric")
        return OutcomeLinkSerializer(rows, many=True).data


class SiteOutcomesSerializer(serializers.Serializer):
    course_code = serializers.CharField(allow_blank=True)
    from_srms = serializers.BooleanField(help_text="The outcomes come from the SRMS course outline")
    may_add = serializers.BooleanField(help_text="The site may have its own outcomes: the SRMS has none")
    outcomes = OutcomeSerializer(many=True)


class LinkWriteSerializer(serializers.Serializer):
    assignment = serializers.IntegerField(required=False)
    question = serializers.IntegerField(required=False)
    criterion = serializers.IntegerField(required=False)

    def validate(self, attrs):
        if len([k for k in ("assignment", "question", "criterion") if attrs.get(k)]) != 1:
            raise serializers.ValidationError("Choose one assignment, one question or one rubric criterion.")
        return attrs


class AlertSerializer(serializers.ModelSerializer):
    student_no = serializers.CharField(source="student.external_id", read_only=True)
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    state_label = serializers.CharField(source="get_state_display", read_only=True)
    handled_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Alert
        fields = (
            "id",
            "site",
            "student",
            "student_no",
            "student_name",
            "kind",
            "kind_label",
            "summary",
            "evidence",
            "raised_at",
            "state",
            "state_label",
            "handled_by_name",
            "handled_at",
            "note",
            "conversation",
        )

    def get_handled_by_name(self, obj) -> str | None:
        user = obj.handled_by
        if user is None:
            return None
        person = getattr(user, "person", None)
        return person.full_name if person else user.get_username()


class AlertRuleSerializer(serializers.ModelSerializer):
    label = serializers.CharField(source="get_kind_display", read_only=True)
    description = serializers.CharField(source="describe", read_only=True)

    class Meta:
        model = AlertRule
        fields = ("id", "kind", "label", "description", "threshold", "window_days", "is_active")
        read_only_fields = ("kind",)

    def validate_threshold(self, value):
        if not 1 <= value <= 365:
            raise serializers.ValidationError("Give a number from 1 to 365.")
        return value

    def validate_window_days(self, value):
        if value > 365:
            raise serializers.ValidationError("Give at most 365 days.")
        return value


class ActSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=2000, help_text="What was done")
    conversation = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="The conversation in Messages in which the student was written to",
    )


class DismissSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=2000, help_text="Why nothing needs doing")


# ---------------------------------------------------------------------------------------------------------
# Who may read what on a site


def _site(request, pk) -> tuple[CourseSite, str | None]:
    site = get_object_or_404(visible_sites(request.user), pk=pk)
    return site, site_role(request.user, site)


def _teaching_site(request, pk) -> CourseSite:
    """A site the caller teaches on, or administers. Students and the auditor are refused."""
    site, role = _site(request, pk)
    if role not in TEACHING:
        raise PermissionDenied("Only the site's teaching staff can see this.")
    return site


def _open_alerts(site) -> dict[int, int]:
    rows = Alert.objects.filter(site=site, state__in=[Alert.State.OPEN, Alert.State.ACKNOWLEDGED])
    counts: dict[int, int] = {}
    for student_id in rows.values_list("student_id", flat=True):
        counts[student_id] = counts.get(student_id, 0) + 1
    return counts


# ---------------------------------------------------------------------------------------------------------
# Course analytics and progress (items 6.01, 6.02)


@extend_schema(
    responses={200: AnalyticsSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="Course analytics for teaching staff: items opened, work handed in, marks, quizzes (item 6.01)",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def site_analytics(request, pk: int):
    site = _teaching_site(request, pk)
    return Response(analytics.course_analytics(site))


@extend_schema(
    responses={200: ProgressRowSerializer(many=True), 403: ErrorSerializer, 404: ErrorSerializer},
    summary="Every student's progress on the site, for teaching staff (item 6.02)",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def site_progress(request, pk: int):
    site = _teaching_site(request, pk)
    rows = analytics.class_progress(site)
    alerts = _open_alerts(site)
    for row in rows:
        row["open_alerts"] = alerts.get(row["person_id"], 0)
    return Response(rows)


def _student_progress(site, person, *, released_only: bool) -> dict:
    data = analytics.progress_of(site, person, released_only=released_only)
    table = outcomes.standings(site, [person], released_only=released_only)
    data["outcomes"] = {
        "met_percent": table["met_percent"],
        "outcomes": table["outcomes"],
        "students": table["students"],
    }
    return data


@extend_schema(
    responses={200: StudentProgressSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="One student's progress, work and outcome standings, for teaching staff (item 6.02)",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def student_progress(request, pk: int, person_id: int):
    site = _teaching_site(request, pk)
    membership = get_object_or_404(
        Membership.objects.select_related("person"),
        site=site,
        person_id=person_id,
        role=Membership.SiteRole.STUDENT,
    )
    return Response(_student_progress(site, membership.person, released_only=False))


@extend_schema(
    responses={200: StudentProgressSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="My progress on the site, from released marks (item 6.02)",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def my_progress(request, pk: int):
    site, role = _site(request, pk)
    if role != Membership.SiteRole.STUDENT:
        raise PermissionDenied("My progress is for the site's students.")
    return Response(_student_progress(site, person_of(request.user), released_only=True))


# ---------------------------------------------------------------------------------------------------------
# Learning outcomes (item 3.11)


def _outcomes_payload(site) -> dict:
    listed = outcomes.site_outcomes(site)
    return {
        "course_code": outcomes.course_code_of(site),
        "from_srms": bool(listed) and listed[0].source == Outcome.Source.SRMS,
        "may_add": outcomes.may_add_local(site),
        "outcomes": OutcomeSerializer(listed, many=True, context={"site": site}).data,
    }


class LocalOutcomeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Outcome
        fields = ("code", "text", "position")


@extend_schema(
    methods=["GET"],
    responses={200: SiteOutcomesSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="The site's learning outcomes and the evidence linked to each (item 3.11)",
)
@extend_schema(
    methods=["POST"],
    request=LocalOutcomeSerializer,
    responses={
        201: SiteOutcomesSerializer,
        400: OpenApiTypes.OBJECT,
        403: ErrorSerializer,
        409: ErrorSerializer,
    },
    summary="Add an outcome of the site's own, while the SRMS has none for the course",
)
@api_view(["GET", "POST"])
@permission_classes([RolePermission])
def site_outcomes(request, pk: int):
    site = _teaching_site(request, pk)
    if request.method == "GET":
        return Response(_outcomes_payload(site))
    if not outcomes.may_add_local(site):
        return Response(
            {
                "code": "outcomes_from_srms",
                "detail": "This course's outcomes come from the SRMS course outline; "
                "ask the Registry to change them.",
            },
            status=409,
        )
    data = LocalOutcomeSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    if Outcome.objects.filter(
        source=Outcome.Source.LOCAL, site=site, code=data.validated_data["code"]
    ).exists():
        raise serializers.ValidationError({"code": ["The site already has an outcome with this code."]})
    with transaction.atomic():
        outcome = Outcome.objects.create(
            source=Outcome.Source.LOCAL,
            site=site,
            created_by=request.user,
            updated_by=request.user,
            **data.validated_data,
        )
        record(request, "create", outcome, after=snapshot(outcome))
    return Response(_outcomes_payload(site), status=201)


def _local_outcome(request, outcome_id) -> Outcome:
    outcome = get_object_or_404(
        Outcome.objects.filter(source=Outcome.Source.LOCAL, site__in=visible_sites(request.user)),
        pk=outcome_id,
    )
    if site_role(request.user, outcome.site) not in TEACHING:
        raise PermissionDenied("Only the site's teaching staff can change its outcomes.")
    return outcome


@extend_schema(
    methods=["PATCH"],
    request=LocalOutcomeSerializer,
    responses={200: OutcomeSerializer, 400: OpenApiTypes.OBJECT, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="Change an outcome of the site's own (SRMS outcomes change in the SRMS)",
)
@extend_schema(
    methods=["DELETE"],
    request=None,
    responses={204: None, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="Remove an outcome of the site's own, with its links",
)
@api_view(["PATCH", "DELETE"])
@permission_classes([RolePermission])
def local_outcome(request, outcome_id: int):
    outcome = _local_outcome(request, outcome_id)
    before = snapshot(outcome)
    if request.method == "DELETE":
        with transaction.atomic():
            record(request, "delete", outcome, before=before)
            outcome.delete()
        return Response(status=204)
    data = LocalOutcomeSerializer(outcome, data=request.data, partial=True)
    data.is_valid(raise_exception=True)
    with transaction.atomic():
        try:
            with transaction.atomic():
                outcome = data.save(updated_by=request.user)
        except IntegrityError as error:
            raise serializers.ValidationError(
                {"code": ["The site already has an outcome with this code."]}
            ) from error
        record(request, "update", outcome, before=before, after=snapshot(outcome))
    return Response(OutcomeSerializer(outcome, context={"site": outcome.site}).data)


def _target(site, request, data: dict) -> dict:
    """The evidence named, which must belong to the site: refused as not there otherwise."""
    if data.get("assignment"):
        assignment = Assignment.objects.filter(site=site, pk=data["assignment"]).first()
        if assignment is None:
            raise serializers.ValidationError({"assignment": ["Choose an assignment of this site."]})
        return {"assignment": assignment}
    if data.get("question"):
        from quizzes.services import can_use_bank

        question = Question.objects.filter(pk=data["question"]).select_related("bank").first()
        if question is None or not can_use_bank(request.user, question.bank):
            raise serializers.ValidationError({"question": ["Choose a question from a bank this site uses."]})
        return {"question": question}
    criterion = RubricCriterion.objects.filter(pk=data["criterion"]).select_related("rubric").first()
    used = criterion is not None and (
        criterion.rubric.site_id == site.id
        or Assignment.objects.filter(site=site, rubric=criterion.rubric).exists()
    )
    if not used:
        raise serializers.ValidationError({"criterion": ["Choose a criterion of a rubric this site uses."]})
    return {"criterion": criterion}


@extend_schema(
    request=LinkWriteSerializer,
    responses={
        201: OutcomeLinkSerializer,
        400: OpenApiTypes.OBJECT,
        403: ErrorSerializer,
        404: ErrorSerializer,
        409: ErrorSerializer,
    },
    summary="Link an assignment, a quiz question or a rubric criterion on the site to an outcome",
)
@api_view(["POST"])
@permission_classes([RolePermission])
def outcome_links(request, pk: int, outcome_id: int):
    site = _teaching_site(request, pk)
    outcome = next((o for o in outcomes.site_outcomes(site) if o.id == outcome_id), None)
    if outcome is None:
        return Response({"code": "not_found", "detail": "This site has no such outcome."}, status=404)
    data = LinkWriteSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    target = _target(site, request, data.validated_data)
    if OutcomeLink.objects.filter(site=site, outcome=outcome, **target).exists():
        return Response(
            {"code": "already_linked", "detail": "This is already linked to the outcome."}, status=409
        )
    with transaction.atomic():
        link = OutcomeLink.objects.create(
            site=site, outcome=outcome, created_by=request.user, updated_by=request.user, **target
        )
        record(request, "create", link, after=snapshot(link))
    return Response(OutcomeLinkSerializer(link).data, status=201)


@extend_schema(
    request=None,
    responses={204: None, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="Remove a link between an outcome and its evidence",
)
@api_view(["DELETE"])
@permission_classes([RolePermission])
def outcome_link(request, link_id: int):
    link = get_object_or_404(OutcomeLink.objects.filter(site__in=visible_sites(request.user)), pk=link_id)
    if site_role(request.user, link.site) not in TEACHING:
        raise PermissionDenied("Only the site's teaching staff can change its outcomes.")
    with transaction.atomic():
        record(request, "delete", link, before=snapshot(link))
        link.delete()
    return Response(status=204)


@extend_schema(
    responses={200: StandingsSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="Each student's standing on each outcome, for teaching staff (item 3.11)",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def outcome_standings(request, pk: int):
    site = _teaching_site(request, pk)
    return Response(outcomes.standings(site, analytics.students_of(site)))


# ---------------------------------------------------------------------------------------------------------
# Early alerts (item 6.05)


@extend_schema(
    parameters=[
        OpenApiParameter("state", OpenApiTypes.STR, description="open (new and seen, the default) or all")
    ],
    responses={200: AlertSerializer(many=True), 403: ErrorSerializer, 404: ErrorSerializer},
    summary="Early alerts on the site with their evidence, for teaching staff (item 6.05)",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def site_alerts(request, pk: int):
    site = _teaching_site(request, pk)
    rows = Alert.objects.filter(site=site).select_related("student", "handled_by__person")
    if request.query_params.get("state", "open") != "all":
        rows = rows.filter(state__in=[Alert.State.OPEN, Alert.State.ACKNOWLEDGED])
    return Response(AlertSerializer(rows, many=True).data)


def _alert(request, alert_id) -> Alert:
    alert = get_object_or_404(
        Alert.objects.filter(site__in=taught_sites(request.user)).select_related("site", "student"),
        pk=alert_id,
    )
    if site_role(request.user, alert.site) not in TEACHING:  # pragma: no cover - taught_sites says the same
        raise PermissionDenied("Only the site's teaching staff handle its alerts.")
    return alert


def _handle(request, alert: Alert, state: str, note: str, action: str, conversation=None) -> Response:
    if not alert.is_open:
        return Response(
            {
                "code": "already_handled",
                "detail": f"This alert was already {alert.get_state_display().lower()}.",
            },
            status=409,
        )
    with transaction.atomic():
        before = snapshot(alert)
        alert.state, alert.note = state, note
        alert.handled_by, alert.handled_at = request.user, timezone.now()
        if conversation is not None:
            alert.conversation = conversation
        alert.save(update_fields=["state", "note", "handled_by", "handled_at", "conversation", "updated_at"])
        record(request, action, alert, before=before, after=snapshot(alert), reason=note)
    return Response(AlertSerializer(alert).data)


HANDLED = {
    200: AlertSerializer,
    400: OpenApiTypes.OBJECT,
    403: ErrorSerializer,
    404: ErrorSerializer,
    409: ErrorSerializer,
}


@extend_schema(request=None, responses=HANDLED, summary="Say the alert has been seen; it stays open")
@api_view(["POST"])
@permission_classes([RolePermission])
def acknowledge_alert(request, alert_id: int):
    alert = _alert(request, alert_id)
    if alert.state != Alert.State.OPEN:
        return Response(
            {"code": "already_handled", "detail": "This alert has already been seen."}, status=409
        )
    return _handle(request, alert, Alert.State.ACKNOWLEDGED, "", "alert_acknowledged")


@extend_schema(
    request=ActSerializer,
    responses=HANDLED,
    summary="Record what was done about the alert, such as a message to the student in Messages",
)
@api_view(["POST"])
@permission_classes([RolePermission])
def act_on_alert(request, alert_id: int):
    alert = _alert(request, alert_id)
    data = ActSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    conversation = None
    if data.validated_data.get("conversation"):
        conversation = Conversation.objects.filter(
            pk=data.validated_data["conversation"],
            site=alert.site,
            participants__user=request.user,
        ).first()
        if conversation is None or not conversation.participants.filter(user=alert.student.user_id).exists():
            raise serializers.ValidationError(
                {"conversation": ["Choose a conversation on this course between you and the student."]}
            )
    return _handle(
        request, alert, Alert.State.ACTED, data.validated_data["note"], "alert_acted", conversation
    )


@extend_schema(request=DismissSerializer, responses=HANDLED, summary="Dismiss the alert, with the reason")
@api_view(["POST"])
@permission_classes([RolePermission])
def dismiss_alert(request, alert_id: int):
    alert = _alert(request, alert_id)
    data = DismissSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    return _handle(request, alert, Alert.State.DISMISSED, data.validated_data["reason"], "alert_dismissed")


def _ensure_rules() -> None:
    for kind, (threshold, window) in DEFAULTS.items():
        AlertRule.objects.get_or_create(kind=kind, defaults={"threshold": threshold, "window_days": window})


def _may_read_rules(user) -> bool:
    return has_role(user, *SITE_ADMIN_ROLES) or taught_sites(user).exists()


@extend_schema(
    responses={200: AlertRuleSerializer(many=True), 403: ErrorSerializer},
    summary="The early-alert rules and their thresholds, for teaching staff and course administrators",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def alert_rules(request):
    if not _may_read_rules(request.user):
        raise PermissionDenied("The alert rules are for teaching staff and course administrators.")
    _ensure_rules()
    return Response(AlertRuleSerializer(AlertRule.objects.all(), many=True).data)


@extend_schema(
    request=AlertRuleSerializer,
    responses={
        200: AlertRuleSerializer,
        400: OpenApiTypes.OBJECT,
        403: ErrorSerializer,
        404: ErrorSerializer,
    },
    summary="Change a rule's threshold, window or whether it is used (course administrators)",
)
@api_view(["PATCH"])
@permission_classes([RolePermission])
def alert_rule(request, rule_id: int):
    if not has_role(request.user, *SITE_ADMIN_ROLES):
        raise PermissionDenied("Only course administrators change the alert rules.")
    rule = get_object_or_404(AlertRule, pk=rule_id)
    before = snapshot(rule)
    data = AlertRuleSerializer(rule, data=request.data, partial=True)
    data.is_valid(raise_exception=True)
    with transaction.atomic():
        rule = data.save(updated_by=request.user)
        record(request, "update", rule, before=before, after=snapshot(rule))
    return Response(AlertRuleSerializer(rule).data)


# ---------------------------------------------------------------------------------------------------------
# Reports that leave a course (items 6.03, 6.04, 6.06)


class CourseReportSerializer(serializers.Serializer):
    min_group = serializers.IntegerField(help_text="Groups smaller than this are hidden (item 6.06)")
    marking_days = serializers.IntegerField(help_text="Work is to be marked within this many days")
    total = serializers.DictField()
    groups = serializers.ListField(child=serializers.DictField(), help_text="By campus and programme")
    sites = serializers.ListField(child=serializers.DictField())
    choices = serializers.DictField(help_text="Campuses, programmes and terms the reader may filter by")


class StaffReportSerializer(serializers.Serializer):
    min_group = serializers.IntegerField()
    since = serializers.DateField(allow_null=True)
    total = serializers.DictField()
    units = serializers.ListField(child=serializers.DictField())
    courses = serializers.ListField(child=serializers.DictField())


COURSE_FILTERS = [
    OpenApiParameter("campus", OpenApiTypes.STR),
    OpenApiParameter(
        "programme", OpenApiTypes.STR, description=f'A programme code, or "{reports.NOT_KNOWN}"'
    ),
    OpenApiParameter("term", OpenApiTypes.STR),
]
STAFF_FILTERS = [
    OpenApiParameter("campus", OpenApiTypes.STR),
    OpenApiParameter("since", OpenApiTypes.DATE, description="Completions on or after this day"),
]
CSV = {(200, "text/csv"): OpenApiResponse(OpenApiTypes.STR), 403: ErrorSerializer}


def _scope(request, readers):
    scope = reports.scope_of(request.user, readers)
    if scope.empty:
        raise PermissionDenied(
            "This report is for the roles it was made for, within their units or campuses."
        )
    return scope


def _course_filters(request) -> dict:
    return {key: request.query_params.get(key, "") for key in ("campus", "programme", "term")}


def _choices(scope) -> dict:
    sites = reports.scoped_sites(scope)
    programmes = sorted(
        {code for codes in sites.values_list("profile__programme_codes", flat=True) for code in (codes or [])}
    )
    return {
        "campuses": sorted(set(sites.exclude(campus_code="").values_list("campus_code", flat=True))),
        "programmes": [*programmes, reports.NOT_KNOWN],
        "terms": sorted(set(sites.exclude(term_code="").values_list("term_code", flat=True)), reverse=True),
    }


def _csv_response(lines, name: str) -> StreamingHttpResponse:
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
    response = StreamingHttpResponse(lines, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="gsa-lms-{name}-{stamp}.csv"'
    response["X-Content-Type-Options"] = "nosniff"
    return response


@extend_schema(
    parameters=COURSE_FILTERS,
    responses={200: CourseReportSerializer, 403: ErrorSerializer},
    summary="Courses: content, marking turnaround and coursework sent to the SRMS, by campus and programme "
    "(item 6.03)",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def course_report(request):
    scope = _scope(request, reports.COURSE_READERS)
    filters = _course_filters(request)
    data = reports.course_report(scope, **filters)
    data["choices"] = _choices(scope)
    record_event(request, "report_viewed", "courses.coursesite", after={"report": "courses", **filters})
    return Response(data)


@extend_schema(
    parameters=COURSE_FILTERS,
    responses=CSV,
    summary="The courses report as a CSV file for a spreadsheet (the export is audited)",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def course_report_export(request):
    scope = _scope(request, reports.COURSE_READERS)
    filters = _course_filters(request)
    data = reports.course_report(scope, **filters)
    record_event(
        request,
        "report_exported",
        "courses.coursesite",
        after={"report": "courses", "rows": len(data["sites"]), **filters},
    )
    return _csv_response(reports.course_csv(data), "courses")


def _staff_filters(request) -> dict:
    since = request.query_params.get("since") or None
    if since:
        try:
            since = date.fromisoformat(since)
        except ValueError as error:
            raise serializers.ValidationError({"since": ["Give a date as YYYY-MM-DD."]}) from error
    return {"campus": request.query_params.get("campus", ""), "since": since}


@extend_schema(
    parameters=STAFF_FILTERS,
    responses={200: StaffReportSerializer, 400: OpenApiTypes.OBJECT, 403: ErrorSerializer},
    summary="Staff development: completions by unit and required training overdue (item 6.04)",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def staff_report(request):
    scope = _scope(request, reports.STAFF_READERS)
    filters = _staff_filters(request)
    data = reports.staff_report(scope, **filters)
    after = {"report": "staff_development", "campus": filters["campus"], "since": str(filters["since"] or "")}
    record_event(request, "report_viewed", "staffdev.trainingassignment", after=after)
    return Response(data)


@extend_schema(
    parameters=STAFF_FILTERS,
    responses=CSV,
    summary="The staff development report as a CSV file for a spreadsheet (the export is audited)",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def staff_report_export(request):
    scope = _scope(request, reports.STAFF_READERS)
    filters = _staff_filters(request)
    data = reports.staff_report(scope, **filters)
    after = {"report": "staff_development", "campus": filters["campus"], "rows": len(data["units"])}
    record_event(request, "report_exported", "staffdev.trainingassignment", after=after)
    return _csv_response(reports.staff_csv(data), "staff-development")


urlpatterns = [
    path("sites/<int:pk>/insights/", site_analytics, name="site-insights"),
    path("sites/<int:pk>/progress/", site_progress, name="site-progress"),
    path("sites/<int:pk>/progress/<int:person_id>/", student_progress, name="site-student-progress"),
    path("sites/<int:pk>/my-progress/", my_progress, name="site-my-progress"),
    path("sites/<int:pk>/outcomes/", site_outcomes, name="site-outcomes"),
    path("sites/<int:pk>/outcomes/<int:outcome_id>/links/", outcome_links, name="site-outcome-links"),
    path("sites/<int:pk>/outcome-standings/", outcome_standings, name="site-outcome-standings"),
    path("sites/<int:pk>/alerts/", site_alerts, name="site-alerts"),
    path("outcomes/<int:outcome_id>/", local_outcome, name="outcome-detail"),
    path("outcome-links/<int:link_id>/", outcome_link, name="outcome-link-detail"),
    path("alerts/<int:alert_id>/acknowledge/", acknowledge_alert, name="alert-acknowledge"),
    path("alerts/<int:alert_id>/act/", act_on_alert, name="alert-act"),
    path("alerts/<int:alert_id>/dismiss/", dismiss_alert, name="alert-dismiss"),
    path("alert-rules/", alert_rules, name="alert-rules"),
    path("alert-rules/<int:rule_id>/", alert_rule, name="alert-rule"),
    path("reports/courses/", course_report, name="report-courses"),
    path("reports/courses/export/", course_report_export, name="report-courses-export"),
    path("reports/staff-development/", staff_report, name="report-staff"),
    path("reports/staff-development/export/", staff_report_export, name="report-staff-export"),
]
