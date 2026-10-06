"""Staff development endpoints (Phase 5): the catalogue and joining it (5.02), progress and completion (5.03),
learning paths (5.04) and required training (5.05).

Members of staff browse the catalogue and join courses; course administrators set what the catalogue says,
the completion rules, the paths and the requirements. Students do not see the staff-development catalogue.
"""

from datetime import date

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from approvals.engine import WorkflowError
from audit.services import record, record_event, snapshot
from core.serializers import ErrorSerializer
from courses.access import person_of
from courses.models import Completion, CourseSite, Membership
from iam.models import Role
from iam.permissions import RolePermission
from iam.services import has_role
from people.models import PersonRef
from staffdev import completion, enrolment, paths, required
from staffdev.models import (
    CatalogueEntry,
    EnrolmentRequest,
    LearningPath,
    PathStep,
    RequiredTraining,
    TrainingAssignment,
)

MANAGERS = (Role.ADMINISTRATOR, Role.COURSE_ADMIN)
OVERSEERS = (*MANAGERS, Role.AUDITOR)


def _refused(code: str, detail: str, http: int = status.HTTP_409_CONFLICT) -> Response:
    return Response({"code": code, "detail": detail}, status=http)


def _staff_or_manager(user) -> PersonRef | None:
    """The member of staff using the catalogue; a manager or auditor may look without being on the staff."""
    person = person_of(user)
    if person is not None and person.kind == PersonRef.Kind.STAFF:
        return person
    if has_role(user, *OVERSEERS):
        return None
    raise PermissionDenied("The staff-development catalogue is for members of staff.")


# ---------------------------------------------------------------------------------------------------------
# Catalogue (item 5.02) and completion (item 5.03)


class CatalogueEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = CatalogueEntry
        fields = (
            "summary",
            "audience",
            "length_hours",
            "self_enrol",
            "capacity",
            "rule_all_items",
            "rule_quizzes_passed",
            "rule_assignment_percent",
            "validity_months",
            "issue_certificate",
            "certificate_template",
        )


class CatalogueCourseSerializer(serializers.Serializer):
    """A course in the catalogue, with where the reader stands on it."""

    site = serializers.IntegerField(source="site.id")
    code = serializers.CharField(source="site.code")
    title = serializers.CharField(source="site.title")
    description = serializers.CharField(source="site.description")
    summary = serializers.CharField()
    audience = serializers.CharField()
    length_hours = serializers.DecimalField(max_digits=5, decimal_places=1, allow_null=True)
    self_enrol = serializers.ChoiceField(choices=CatalogueEntry.Enrol.choices)
    capacity = serializers.IntegerField(allow_null=True)
    places_left = serializers.SerializerMethodField(help_text="Null when there is no limit")
    my_status = serializers.SerializerMethodField(
        help_text="none, requested, enrolled, completed or renewal_due; null for someone not on the staff"
    )
    completed_on = serializers.SerializerMethodField()
    expires_on = serializers.SerializerMethodField()

    def _person(self):
        return self.context.get("person")

    def _completion(self, entry):
        person = self._person()
        if person is None:
            return None
        cache = self.context.setdefault("_done", {})
        if entry.site_id not in cache:
            cache[entry.site_id] = Completion.objects.filter(site=entry.site, person=person).first()
        return cache[entry.site_id]

    def get_places_left(self, entry) -> int | None:
        return enrolment.places_left(entry)

    def get_my_status(self, entry) -> str | None:
        person = self._person()
        if person is None:
            return None
        done = self._completion(entry)
        if done is not None:
            return "renewal_due" if completion.renewal_open(done) else "completed"
        if Membership.objects.filter(site=entry.site, person=person, is_active=True).exists():
            return "enrolled"
        waiting = EnrolmentRequest.State.SUBMITTED
        if EnrolmentRequest.objects.filter(site=entry.site, person=person, state=waiting).exists():
            return "requested"
        return "none"

    def get_completed_on(self, entry) -> date | None:
        done = self._completion(entry)
        return done.completed_on if done else None

    def get_expires_on(self, entry) -> date | None:
        done = self._completion(entry)
        return done.expires_on if done else None


class CatalogueJoinSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="", max_length=1000)


class CatalogueJoinedSerializer(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=["enrolled", "requested"])
    request = serializers.IntegerField(allow_null=True, help_text="The enrolment request, when one was made")


class CompletionRuleSerializer(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()
    met = serializers.BooleanField()
    done = serializers.IntegerField()
    total = serializers.IntegerField()


class CompletionProgressSerializer(serializers.Serializer):
    complete = serializers.BooleanField(help_text="Every rule is met")
    rules = CompletionRuleSerializer(many=True)
    completed_on = serializers.DateField(allow_null=True)
    expires_on = serializers.DateField(allow_null=True)


class RecordCompletionSerializer(serializers.Serializer):
    person = serializers.PrimaryKeyRelatedField(queryset=PersonRef.objects.filter(is_active=True))
    completed_on = serializers.DateField(required=False, help_text="Today when not given")

    def validate_completed_on(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError("A completion cannot be in the future.")
        return value


class CompletionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Completion
        fields = ("id", "site", "person", "completed_on", "expires_on", "how", "certificate", "reported_at")


@extend_schema(parameters=[OpenApiParameter("q", str, description="Words in the title, code or summary")])
class CatalogueViewSet(viewsets.ReadOnlyModelViewSet):
    """The staff-development catalogue: published staff-development sites with a catalogue entry."""

    serializer_class = CatalogueCourseSerializer
    permission_classes = [RolePermission]
    queryset = CatalogueEntry.objects.none()
    lookup_field = "site"

    def get_queryset(self):
        qs = CatalogueEntry.objects.select_related("site").filter(
            site__kind=CourseSite.Kind.STAFF_DEVELOPMENT
        )
        if not has_role(self.request.user, *OVERSEERS):
            qs = qs.filter(site__is_published=True)
        text = (self.request.query_params.get("q") or "").strip()
        if text:
            qs = qs.filter(
                Q(site__title__icontains=text) | Q(site__code__icontains=text) | Q(summary__icontains=text)
            )
        return qs.order_by("site__title")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["person"] = _staff_or_manager(self.request.user)
        return context

    @extend_schema(summary="Browse the staff-development catalogue (members of staff)")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(summary="One course in the catalogue, with where I stand on it")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    def _entry(self, site) -> CatalogueEntry:
        return get_object_or_404(self.get_queryset(), site=site)

    @extend_schema(
        request=CatalogueJoinSerializer,
        responses={
            201: CatalogueJoinedSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
        summary="Join a course: at once where it is open, or ask for approval where it needs it",
    )
    @action(detail=True, methods=["post"])
    def join(self, request, site=None):
        entry = self._entry(site)
        person = person_of(request.user)
        if person is None:
            return _refused("not_staff", "Staff-development courses are for members of staff.", 403)
        data = CatalogueJoinSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            result = enrolment.join(request, entry, person, reason=data.validated_data["reason"])
        except enrolment.Refused as exc:
            return _refused(exc.code, exc.detail, exc.status)
        made = result["request"]
        return Response(
            {"outcome": result["outcome"], "request": made.pk if made else None},
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        parameters=[OpenApiParameter("person", int, description="For course administrators: someone else")],
        responses={200: CompletionProgressSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
        summary="How far through the course's completion rules I am (item 5.03)",
    )
    @action(detail=True, methods=["get"])
    def progress(self, request, site=None):
        entry = self._entry(site)
        person = person_of(request.user)
        other = request.query_params.get("person")
        if other:
            if not has_role(request.user, *OVERSEERS):
                raise PermissionDenied("Only course administrators look at someone else's progress.")
            person = get_object_or_404(PersonRef, pk=other)
        if person is None:
            return _refused("no_person", "Your account is not linked to a person record.", 404)
        done = Completion.objects.filter(site=entry.site, person=person).first()
        since = completion._since(done) if done is not None and completion.renewal_open(done) else None
        measured = completion.progress(entry, person, since=since)
        return Response(
            {
                "complete": measured.complete,
                "rules": [vars(rule) for rule in measured.rules],
                "completed_on": done.completed_on if done else None,
                "expires_on": done.expires_on if done else None,
            }
        )

    @extend_schema(
        request=CatalogueEntrySerializer,
        responses={200: CatalogueEntrySerializer, 400: ErrorSerializer, 403: ErrorSerializer},
        summary="Set what the catalogue says about a staff-development site, and its completion rules",
    )
    @action(detail=True, methods=["put"])
    def entry(self, request, site=None):
        if not has_role(request.user, *MANAGERS):
            raise PermissionDenied("Only course administrators change the catalogue.")
        site = get_object_or_404(CourseSite, pk=site)
        # Open short courses (item 5.07) keep their summary, places and completion rules here too.
        if site.kind not in (CourseSite.Kind.STAFF_DEVELOPMENT, CourseSite.Kind.OPEN):
            return _refused(
                "not_staff_development", "Only staff-development and open sites go in the catalogue.", 400
            )
        current = CatalogueEntry.objects.filter(site=site).first()
        data = CatalogueEntrySerializer(current, data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            before = snapshot(current) if current else None
            saved = data.save(site=site)
            record(request, "update" if before else "create", saved, before=before, after=snapshot(saved))
        return Response(CatalogueEntrySerializer(saved).data)

    @extend_schema(
        request=RecordCompletionSerializer,
        responses={201: CompletionSerializer, 400: ErrorSerializer, 403: ErrorSerializer},
        summary="Record that someone completed the course (course administrators); issues the certificate",
    )
    @action(detail=True, methods=["post"], url_path="record-completion")
    def record_completion(self, request, site=None):
        if not has_role(request.user, *MANAGERS):
            raise PermissionDenied("Only course administrators record a completion.")
        entry = self._entry(site)
        data = RecordCompletionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        done = completion.record_completion(
            entry,
            data.validated_data["person"],
            request=request,
            how=Completion.How.RECORDED,
            on=data.validated_data.get("completed_on"),
        )
        return Response(CompletionSerializer(done).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------------------------------------
# Enrolment requests (item 5.02, approvals engine)


class EnrolmentRequestSerializer(serializers.ModelSerializer):
    person_name = serializers.CharField(source="person.full_name", read_only=True)
    site_title = serializers.CharField(source="site.title", read_only=True)
    approver_name = serializers.SerializerMethodField(help_text="Null: the course administrators decide")
    allowed_actions = serializers.SerializerMethodField(help_text="What I may do with it now")

    class Meta:
        model = EnrolmentRequest
        fields = (
            "id",
            "site",
            "site_title",
            "person",
            "person_name",
            "approver",
            "approver_name",
            "state",
            "reason",
            "decision_comment",
            "waiting_since",
            "created_at",
            "allowed_actions",
        )
        read_only_fields = fields

    def get_approver_name(self, obj) -> str | None:
        return obj.approver.full_name if obj.approver else None

    def get_allowed_actions(self, obj) -> list[str]:
        return enrolment.WORKFLOW.allowed_actions(obj, self.context["request"].user)


class EnrolmentDecisionSerializer(serializers.Serializer):
    comment = serializers.CharField(required=False, allow_blank=True, default="", max_length=2000)


@extend_schema(
    parameters=[
        OpenApiParameter("state", str, enum=[s for s, _ in EnrolmentRequest.State.choices]),
        OpenApiParameter("mine", bool, description="Only my own requests"),
    ]
)
class EnrolmentRequestViewSet(viewsets.ReadOnlyModelViewSet):
    """My requests to join, and those I decide (as supervisor, stand-in or course administrator)."""

    serializer_class = EnrolmentRequestSerializer
    permission_classes = [RolePermission]
    queryset = EnrolmentRequest.objects.none()

    def get_queryset(self):
        from approvals.delegation import delegator_ids

        user = self.request.user
        person = person_of(user)
        qs = EnrolmentRequest.objects.select_related("site", "person", "approver")
        if has_role(user, *OVERSEERS):
            visible = Q()
        else:
            visible = Q(pk__in=[])
            if person is not None:
                visible = Q(person=person) | Q(approver=person) | Q(approver_id__in=delegator_ids(person))
        qs = qs.filter(visible)
        params = self.request.query_params
        if params.get("mine") in ("1", "true") and person is not None:
            qs = qs.filter(person=person)
        if params.get("state"):
            qs = qs.filter(state=params["state"])
        return qs

    def _decide(self, request, pk, action_name):
        instance = self.get_object()
        data = EnrolmentDecisionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            enrolment.WORKFLOW.apply(
                instance, action_name, request=request, comment=data.validated_data["comment"]
            )
        except WorkflowError as exc:
            http = status.HTTP_403_FORBIDDEN if exc.code == "forbidden_actor" else status.HTTP_409_CONFLICT
            if exc.code == "comment_required":
                http = status.HTTP_400_BAD_REQUEST
            return _refused(exc.code, exc.detail, http)
        return Response(self.get_serializer(instance).data)

    @extend_schema(
        request=EnrolmentDecisionSerializer,
        responses={200: EnrolmentRequestSerializer, 403: ErrorSerializer, 409: ErrorSerializer},
        summary="Approve a request to join: the person is put on the course",
    )
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._decide(request, pk, "approve")

    @extend_schema(
        request=EnrolmentDecisionSerializer,
        responses={
            200: EnrolmentRequestSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            409: ErrorSerializer,
        },
        summary="Turn down a request to join, saying why",
    )
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._decide(request, pk, "reject")

    @extend_schema(
        request=EnrolmentDecisionSerializer,
        responses={200: EnrolmentRequestSerializer, 403: ErrorSerializer, 409: ErrorSerializer},
        summary="Withdraw my own request to join",
    )
    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        return self._decide(request, pk, "withdraw")


# ---------------------------------------------------------------------------------------------------------
# Learning paths (item 5.04)


class PathStepSerializer(serializers.ModelSerializer):
    title = serializers.CharField(source="site.title", read_only=True)

    class Meta:
        model = PathStep
        fields = ("position", "site", "title")


class LearningPathSerializer(serializers.ModelSerializer):
    sites = serializers.PrimaryKeyRelatedField(
        many=True,
        write_only=True,
        queryset=CourseSite.objects.filter(kind=CourseSite.Kind.STAFF_DEVELOPMENT),
        help_text="The path's courses, in order: staff-development site ids",
    )
    steps = PathStepSerializer(many=True, read_only=True)

    class Meta:
        model = LearningPath
        fields = ("id", "code", "title", "description", "audience", "is_published", "sites", "steps")

    def validate_sites(self, value):
        if not value:
            raise serializers.ValidationError("A path has at least one course.")
        if len({s.pk for s in value}) != len(value):
            raise serializers.ValidationError("A course appears on a path only once.")
        return value

    def _steps(self, path, sites):
        path.steps.all().delete()
        PathStep.objects.bulk_create(
            PathStep(path=path, site=site, position=i) for i, site in enumerate(sites, start=1)
        )

    def create(self, validated_data):
        sites = validated_data.pop("sites")
        path = LearningPath.objects.create(**validated_data)
        self._steps(path, sites)
        return path

    def update(self, instance, validated_data):
        sites = validated_data.pop("sites", None)
        instance = super().update(instance, validated_data)
        if sites is not None:
            self._steps(instance, sites)
        return instance


class PathStepProgressSerializer(serializers.Serializer):
    position = serializers.IntegerField()
    site = serializers.IntegerField()
    title = serializers.CharField()
    state = serializers.ChoiceField(choices=["done", "open", "locked"])
    enrolled = serializers.BooleanField()


class PathProgressSerializer(serializers.Serializer):
    joined = serializers.BooleanField()
    done = serializers.IntegerField()
    total = serializers.IntegerField()
    complete = serializers.BooleanField()
    steps = PathStepProgressSerializer(many=True)


class LearningPathViewSet(mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.ReadOnlyModelViewSet):
    """Learning paths: members of staff see the published ones; course administrators make them."""

    serializer_class = LearningPathSerializer
    permission_classes = [RolePermission]
    queryset = LearningPath.objects.none()
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = LearningPath.objects.prefetch_related("steps__site")
        if not has_role(self.request.user, *OVERSEERS):
            _staff_or_manager(self.request.user)
            qs = qs.filter(is_published=True)
        return qs

    def _managing(self):
        if not has_role(self.request.user, *MANAGERS):
            raise PermissionDenied("Only course administrators make and change learning paths.")

    @transaction.atomic
    def perform_create(self, serializer):
        self._managing()
        path = serializer.save()
        record(self.request, "create", path, after=snapshot(path))

    @transaction.atomic
    def perform_update(self, serializer):
        self._managing()
        before = snapshot(serializer.instance)
        path = serializer.save()
        record(self.request, "update", path, before=before, after=snapshot(path))

    def _progress(self, path, person) -> dict:
        measured = paths.progress(path, person)
        joined = path.enrolments.filter(person=person).exists()
        return {"joined": joined, **measured}

    @extend_schema(
        request=None,
        responses={200: PathProgressSerializer, 403: ErrorSerializer},
        summary="Join a path: I am put forward for its first course I have not completed",
    )
    @action(detail=True, methods=["post"])
    def join(self, request, pk=None):
        path = self.get_object()
        person = person_of(request.user)
        if person is None or person.kind != PersonRef.Kind.STAFF:
            return _refused("not_staff", "Learning paths are for members of staff.", 403)
        paths.join_path(request, path, person)
        return Response(self._progress(path, person))

    @extend_schema(
        responses={200: PathProgressSerializer, 404: ErrorSerializer},
        summary="How far along the path I am; the next course opens when the one before it is complete",
    )
    @action(detail=True, methods=["get"])
    def progress(self, request, pk=None):
        path = self.get_object()
        person = person_of(request.user)
        if person is None:
            return _refused("no_person", "Your account is not linked to a person record.", 404)
        return Response(self._progress(path, person))


# ---------------------------------------------------------------------------------------------------------
# Required training (item 5.05)


def kept_in_hrms(requirement: RequiredTraining) -> bool:
    """A requirement read from the HRMS is changed there while the LMS reads its list (decision D13)."""
    return settings.HRMS_TRAINING_REQUIREMENTS_SYNC and requirement.source == RequiredTraining.Source.HRMS


class RequiredTrainingSerializer(serializers.ModelSerializer):
    site_title = serializers.CharField(source="site.title", read_only=True)
    applies_to = serializers.CharField(source="describe", read_only=True)
    assigned = serializers.IntegerField(source="assignments.count", read_only=True)
    editable = serializers.SerializerMethodField(
        help_text="Whether course administrators may change it here: not when the HRMS keeps it (D13)"
    )

    class Meta:
        model = RequiredTraining
        read_only_fields = ("source",)
        fields = (
            "id",
            "site",
            "site_title",
            "campus_code",
            "unit_code",
            "post_title",
            "applies_to",
            "due_days",
            "renewal_months",
            "is_active",
            "notes",
            "assigned",
            "source",
            "editable",
        )

    def get_editable(self, obj) -> bool:
        return not kept_in_hrms(obj)

    def validate_site(self, site):
        if site.kind != CourseSite.Kind.STAFF_DEVELOPMENT:
            raise serializers.ValidationError("Required training is a staff-development course.")
        return site


class TrainingAssignmentSerializer(serializers.ModelSerializer):
    site = serializers.IntegerField(source="requirement.site_id", read_only=True)
    site_title = serializers.CharField(source="requirement.site.title", read_only=True)
    person_name = serializers.CharField(source="person.full_name", read_only=True)
    employee_no = serializers.CharField(source="person.external_id", read_only=True)
    campus_code = serializers.CharField(source="person.campus_code", read_only=True)
    state = serializers.SerializerMethodField(help_text="done, due or overdue")

    class Meta:
        model = TrainingAssignment
        fields = (
            "id",
            "site",
            "site_title",
            "person",
            "person_name",
            "employee_no",
            "campus_code",
            "assigned_on",
            "due_on",
            "completed_on",
            "state",
        )

    def get_state(self, obj) -> str:
        if obj.completed_on:
            return "done"
        return "overdue" if obj.due_on < timezone.localdate() else "due"


class AssignedSerializer(serializers.Serializer):
    assigned = serializers.IntegerField()


class RequiredTrainingViewSet(
    mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.ReadOnlyModelViewSet
):
    """Required training. Course administrators keep their own; those read from the HRMS are read-only while
    HRMS_TRAINING_REQUIREMENTS_SYNC is on (decision D13)."""

    serializer_class = RequiredTrainingSerializer
    permission_classes = [RolePermission]
    queryset = RequiredTraining.objects.none()
    http_method_names = ["get", "post", "patch", "head", "options"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        # Every member of staff sees their own; the rest is for course administrators and the auditor.
        if self.action == "mine":
            return
        allowed = OVERSEERS if request.method in ("GET", "HEAD", "OPTIONS") else MANAGERS
        if not has_role(request.user, *allowed):
            self.permission_denied(request, message="You do not hold a role that permits this action.")

    def get_queryset(self):
        return RequiredTraining.objects.select_related("site")

    @extend_schema(responses={200: RequiredTrainingSerializer, 409: ErrorSerializer})
    def partial_update(self, request, *args, **kwargs):
        if kept_in_hrms(self.get_object()):
            return _refused(
                "kept_in_hrms",
                "This requirement is kept in the HRMS. Change it there: the LMS reads it each night.",
            )
        return super().partial_update(request, *args, **kwargs)

    @transaction.atomic
    def perform_create(self, serializer):
        requirement = serializer.save()
        record(self.request, "create", requirement, after=snapshot(requirement))
        required.assign(requirement, request=self.request)

    @transaction.atomic
    def perform_update(self, serializer):
        before = snapshot(serializer.instance)
        requirement = serializer.save()
        record(self.request, "update", requirement, before=before, after=snapshot(requirement))
        required.assign(requirement, request=self.request)

    @extend_schema(
        parameters=[OpenApiParameter("campus_code", str)],
        responses=TrainingAssignmentSerializer(many=True),
        summary="Who is overdue with required training",
    )
    @action(detail=False, methods=["get"])
    def overdue(self, request):
        rows = required.overdue(campus_code=request.query_params.get("campus_code", ""))
        record_event(request, "report_viewed", "staffdev.trainingassignment", after={"report": "overdue"})
        page = self.paginate_queryset(rows)
        return self.get_paginated_response(TrainingAssignmentSerializer(page, many=True).data)

    @extend_schema(
        responses=TrainingAssignmentSerializer(many=True), summary="My required training and when it is due"
    )
    @action(detail=False, methods=["get"])
    def mine(self, request):
        person = person_of(request.user)
        rows = TrainingAssignment.objects.none()
        if person is not None:
            rows = TrainingAssignment.objects.filter(person=person).select_related(
                "requirement__site", "person"
            )
        return Response(TrainingAssignmentSerializer(rows, many=True).data)

    @extend_schema(
        request=None,
        responses={200: AssignedSerializer, 403: ErrorSerializer},
        summary="Assign the course now to everyone the requirement covers who has not been assigned it",
    )
    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        requirement = self.get_object()
        return Response({"assigned": required.assign(requirement, request=request)})


router = SimpleRouter()
router.register("catalogue", CatalogueViewSet, basename="sd-catalogue")
router.register("requests", EnrolmentRequestViewSet, basename="sd-request")
router.register("paths", LearningPathViewSet, basename="sd-path")
router.register("required", RequiredTrainingViewSet, basename="sd-required")
urlpatterns = router.urls
