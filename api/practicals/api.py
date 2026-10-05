"""Practical and field assessment: tasks and checklists, observations, competency records, the logbook and
the student's portfolio (items 3.12 to 3.15, 5.15).

Every write settles the site first (item 1.15) and takes an Idempotency-Key for the phone's offline queue
(practicals.offline). Students see only their own records, and observations only once released.
"""

from django.db import transaction
from django.db.models import Max, Q
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from audit.services import record, snapshot
from core.serializers import ErrorSerializer
from courses.access import can_teach, person_of, site_role, taught_sites, visible_sites
from courses.api import TeachingViewSet
from courses.models import CourseSite, Membership
from iam.permissions import RolePermission
from iam.services import SITE_ADMIN_ROLES, has_role
from people.models import PersonRef
from practicals.access import assessed_sites, can_assess, named_sites
from practicals.models import (
    AssignmentCompetencyMap,
    CompetencyFramework,
    CompetencyResult,
    LogbookEntry,
    LogbookPhoto,
    Observation,
    ObservationPhoto,
    ObservationResult,
    PracticalAssessor,
    PracticalCriterion,
    PracticalTask,
    SiteFramework,
)
from practicals.offline import IDEMPOTENCY_HEADER, IdempotentWrites, idempotent
from practicals.serializers import (
    AssignmentMapSerializer,
    CompetencyResultSerializer,
    FrameworkImportSerializer,
    FrameworkSerializer,
    LogbookEntrySerializer,
    LogbookReviewSerializer,
    ObservationSerializer,
    ObservationUpdateSerializer,
    ObservationWriteSerializer,
    PhotosSerializer,
    PracticalAssessorSerializer,
    PracticalCriterionSerializer,
    PracticalTaskSerializer,
    SiteFrameworkSerializer,
    store_photos,
)
from practicals.services import (
    competency_sheet,
    hours_by_unit,
    missing_critical,
    portfolio,
    portfolio_html,
    site_students,
    site_units,
)

PARSERS = (JSONParser, MultiPartParser, FormParser)
WRITE_ERRORS = {400: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer, 409: ErrorSerializer}


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "conflict"


def refuse(detail: str, code: str):
    raise Conflict(detail, code=code)


def _notify(person, *, title: str, body: str, link: str, dedupe_key: str) -> None:
    if person is None or person.user is None:
        return
    from notifications.services import notify

    notify([person.user], title=title, body=body, link=link, dedupe_key=dedupe_key)


def staff_person(user):
    """The person a field record is made under; course administrators without a staff record cannot sign."""
    person = person_of(user)
    if person is None:
        raise PermissionDenied(
            "Field records are made under a member of staff's name; your account has none."
        )
    return person


# ---- Assessors, frameworks followed, tasks and criteria ------------------------------------------------


@extend_schema(tags=["practicals"])
class PracticalAssessorViewSet(IdempotentWrites, TeachingViewSet):
    """Field instructors and assessors named on a site by its teaching staff (item 3.12)."""

    serializer_class = PracticalAssessorSerializer

    def get_queryset(self):
        qs = PracticalAssessor.objects.filter(site__in=taught_sites(self.request.user)).select_related(
            "person"
        )
        site = self.request.query_params.get("site")
        return qs.filter(site_id=site) if site else qs

    def site_of(self, instance):
        return instance.site

    def site_from_data(self, data):
        return data["site"]


@extend_schema(tags=["competency"])
class SiteFrameworkViewSet(IdempotentWrites, TeachingViewSet):
    """The competency frameworks a site follows (decision D8): its units are recorded beside the marks."""

    serializer_class = SiteFrameworkSerializer
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        qs = SiteFramework.objects.filter(site__in=visible_sites(self.request.user)).select_related(
            "framework"
        )
        site = self.request.query_params.get("site")
        return qs.filter(site_id=site) if site else qs

    def site_of(self, instance):
        return instance.site

    def site_from_data(self, data):
        return data["site"]


def visible_tasks(user):
    """Published tasks on the sites the user can open or is named on, and every task where they teach."""
    return PracticalTask.objects.filter(
        Q(site__in=visible_sites(user), is_published=True)
        | Q(site__in=named_sites(user), is_published=True)
        | Q(site__in=taught_sites(user))
    )


StudentRow = inline_serializer(
    "PracticalTaskStudent",
    {
        "person_id": serializers.IntegerField(),
        "student_no": serializers.CharField(),
        "name": serializers.CharField(),
        "attempts": serializers.IntegerField(),
        "attempts_left": serializers.IntegerField(),
        "latest": serializers.DictField(allow_null=True),
    },
    many=True,
)


@extend_schema(tags=["practicals"])
class PracticalTaskViewSet(IdempotentWrites, TeachingViewSet):
    """Practical tasks with their observation checklists (item 3.12). Teaching staff set them up; teaching
    staff and named assessors observe; teaching staff release."""

    serializer_class = PracticalTaskSerializer

    def get_queryset(self):
        qs = (
            visible_tasks(self.request.user)
            .select_related("site")
            .prefetch_related("criteria__performance_criteria")
        )
        site = self.request.query_params.get("site")
        return qs.filter(site_id=site) if site else qs

    def site_of(self, instance):
        return instance.site

    def site_from_data(self, data):
        return data["site"]

    def _require_assessing(self, site):
        if not can_assess(self.request.user, site):
            raise PermissionDenied("Only the site's teaching staff and named assessors can do this.")

    @extend_schema(
        responses={200: StudentRow, 403: ErrorSerializer, 404: ErrorSerializer},
        summary="The class list for a task, with each student's attempts so far",
    )
    @action(detail=True, methods=["get"])
    def students(self, request, pk=None):
        task = self.get_object()
        self._require_assessing(task.site)
        rows = []
        for person in site_students(task.site):
            attempts = list(task.observations.filter(student=person).prefetch_related("results__criterion"))
            latest = attempts[-1] if attempts else None
            rows.append(
                {
                    "person_id": person.id,
                    "student_no": person.external_id,
                    "name": person.full_name,
                    "attempts": len(attempts),
                    "attempts_left": max(task.max_attempts - len(attempts), 0),
                    "latest": {
                        "id": latest.id,
                        "attempt": latest.attempt,
                        "is_released": latest.is_released,
                        "critical_passed": latest.critical_passed(),
                        "score": "{} of {}".format(*latest.score()),
                    }
                    if latest
                    else None,
                }
            )
        return Response(rows)

    @extend_schema(
        request={
            "multipart/form-data": ObservationWriteSerializer,
            "application/json": ObservationWriteSerializer,
        },
        responses={201: ObservationSerializer, **WRITE_ERRORS},
        parameters=[IDEMPOTENCY_HEADER],
        summary="Record an observation of one student against the whole checklist (a new attempt each time)",
    )
    @action(detail=True, methods=["post"], url_path="observations", parser_classes=PARSERS)
    @idempotent
    def observe(self, request, pk=None):
        task = self.get_object()  # a task the caller cannot see reads as unknown (404)
        self._require_assessing(task.site)
        assessor = staff_person(request.user)
        if not task.is_published:
            refuse("Publish the task before observing it.", "not_open")
        data = ObservationWriteSerializer(data=request.data, context={"task": task})
        data.is_valid(raise_exception=True)
        v = data.validated_data
        with transaction.atomic():
            PracticalTask.objects.select_for_update().get(pk=task.pk)  # one attempt number at a time
            done = task.observations.filter(student=v["student"]).aggregate(n=Max("attempt"))["n"] or 0
            if done >= task.max_attempts:
                refuse(
                    f"This student has had all {task.max_attempts} attempts at this task.", "no_attempts_left"
                )
            observation = Observation.objects.create(
                task=task,
                student=v["student"],
                attempt=done + 1,
                assessor=assessor,
                observed_at=v["observed_at"],
                latitude=v.get("latitude"),
                longitude=v.get("longitude"),
                location_text=v.get("location_text", ""),
                comments=v.get("comments", ""),
                created_by=request.user,
                updated_by=request.user,
            )
            ObservationResult.objects.bulk_create(
                ObservationResult(observation=observation, **r) for r in v["results"]
            )
            store_photos(ObservationPhoto, "observation", observation, v.get("photos", []), request.user)
            record(request, "observe", observation, after=_observation_state(observation))
        return Response(ObservationSerializer(observation).data, status=201)

    @extend_schema(
        request=None,
        responses={
            200: inline_serializer("Released", {"released": serializers.IntegerField()}),
            **WRITE_ERRORS,
        },
        parameters=[IDEMPOTENCY_HEADER],
        summary="Release every observation of the task not yet released to its student",
    )
    @action(detail=True, methods=["post"])
    @idempotent
    def release(self, request, pk=None):
        task = self.get_object()
        self._require_teaching(task.site)
        with transaction.atomic():
            waiting = list(
                task.observations.filter(is_released=False).select_related("student__user", "task__site")
            )
            for observation in waiting:
                _release(request, observation)
        return Response({"released": len(waiting)})


@extend_schema(tags=["practicals"])
class PracticalCriterionViewSet(IdempotentWrites, TeachingViewSet):
    """The criteria of a checklist, in order. Once a criterion has been marked only its competency mapping
    may change: add a new criterion rather than rewrite one students were marked against."""

    serializer_class = PracticalCriterionSerializer

    def get_queryset(self):
        qs = PracticalCriterion.objects.filter(task__site__in=assessed_sites(self.request.user))
        task = self.request.query_params.get("task")
        return qs.filter(task_id=task) if task else qs

    def site_of(self, instance):
        return instance.task.site

    def site_from_data(self, data):
        return data["task"].site

    def perform_update(self, serializer):
        instance = serializer.instance
        changed = [
            k
            for k, v in serializer.validated_data.items()
            if k != "performance_criteria" and getattr(instance, k) != v
        ]
        if changed and instance.results.exists():
            refuse(
                "Students have been marked against this criterion; only its competency mapping can change. "
                "Add a new criterion instead.",
                "in_use",
            )
        super().perform_update(serializer)
        if "performance_criteria" in serializer.validated_data:
            record(self.request, "map", instance, after={"performance_criteria": _pc_ids(instance)})

    def perform_create(self, serializer):
        super().perform_create(serializer)
        if serializer.validated_data.get("performance_criteria"):
            record(
                self.request,
                "map",
                serializer.instance,
                after={"performance_criteria": _pc_ids(serializer.instance)},
            )


def _pc_ids(criterion) -> list[int]:
    return sorted(criterion.performance_criteria.values_list("id", flat=True))


# ---- Observations --------------------------------------------------------------------------------------


def visible_observations(user):
    """A student's own released observations, and every observation on the sites the user assesses."""
    person = person_of(user)
    mine = Q(student=person, is_released=True) if person is not None else Q(pk__in=[])
    return Observation.objects.filter(mine | Q(task__site__in=assessed_sites(user)))


def _observation_state(observation) -> dict:
    state = snapshot(observation)
    state["results"] = [
        {"criterion": r.criterion_id, "passed": r.passed, "score": r.score, "comment": r.comment}
        for r in observation.results.all()
    ]
    state["photos"] = [p.file.name for p in observation.photos.all()]
    return state


def _release(request, observation) -> None:
    observation.is_released = True
    observation.released_at = timezone.now()
    observation.released_by = request.user
    observation.updated_by = request.user
    observation.save(update_fields=["is_released", "released_at", "released_by", "updated_by", "updated_at"])
    record(
        request,
        "release",
        observation,
        after={"attempt": observation.attempt, "student": observation.student_id},
    )
    site = observation.task.site
    _notify(
        observation.student,
        title=f"Practical observed: {observation.task.title}",
        body=f"{site.code}: attempt {observation.attempt} is ready to read.",
        link=f"/sites/{site.id}",
        dedupe_key=f"observation:{observation.id}:released",
    )


@extend_schema(tags=["practicals"])
class ObservationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Observations: every attempt is kept. Corrections are allowed until release, never after."""

    serializer_class = ObservationSerializer
    permission_classes = [RolePermission]
    parser_classes = PARSERS
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = visible_observations(self.request.user).select_related("task__site", "student", "assessor")
        for name, field in (("task", "task_id"), ("site", "task__site_id"), ("student", "student_id")):
            value = self.request.query_params.get(name)
            if value:
                qs = qs.filter(**{field: value})
        return qs.prefetch_related("photos")

    def _editable(self, observation):
        if not can_assess(self.request.user, observation.task.site):
            raise PermissionDenied("Only the site's teaching staff and named assessors can do this.")
        if observation.is_released:
            refuse(
                "This observation has been released and cannot be changed. Record a new attempt instead.",
                "released",
            )

    @extend_schema(
        request=ObservationUpdateSerializer,
        responses={200: ObservationSerializer, **WRITE_ERRORS},
        parameters=[IDEMPOTENCY_HEADER],
        summary="Correct an observation before it is released",
    )
    @idempotent
    def partial_update(self, request, pk=None):
        observation = self.get_object()
        self._editable(observation)
        data = ObservationUpdateSerializer(data=request.data, context={"task": observation.task})
        data.is_valid(raise_exception=True)
        v = data.validated_data
        with transaction.atomic():
            before = _observation_state(observation)
            for field in ("comments", "location_text"):
                if field in v:
                    setattr(observation, field, v[field])
            observation.updated_by = request.user
            observation.save()
            if "results" in v:
                observation.results.all().delete()
                ObservationResult.objects.bulk_create(
                    ObservationResult(observation=observation, **r) for r in v["results"]
                )
            record(request, "update", observation, before=before, after=_observation_state(observation))
        return Response(ObservationSerializer(observation).data)

    @extend_schema(
        responses={204: None, **WRITE_ERRORS},
        parameters=[IDEMPOTENCY_HEADER],
        summary="Remove an observation recorded in error, before release (teaching staff)",
    )
    @idempotent
    def destroy(self, request, pk=None):
        observation = self.get_object()
        if not can_teach(request.user, observation.task.site):
            raise PermissionDenied("Only the site's teaching staff can remove an observation.")
        if observation.is_released:
            refuse("A released observation is kept.", "released")
        with transaction.atomic():
            before, entity_id = _observation_state(observation), observation.pk
            observation.delete()
            record(request, "delete", observation, before=before, entity_id=entity_id)
        return Response(status=204)

    @extend_schema(
        request=None,
        responses={200: ObservationSerializer, **WRITE_ERRORS},
        parameters=[IDEMPOTENCY_HEADER],
        summary="Release an observation to its student",
    )
    @action(detail=True, methods=["post"])
    @idempotent
    def release(self, request, pk=None):
        observation = self.get_object()
        if not can_teach(request.user, observation.task.site):
            raise PermissionDenied("Only the site's teaching staff can release observations.")
        if not observation.is_released:
            with transaction.atomic():
                _release(request, observation)
        return Response(ObservationSerializer(observation).data)

    @extend_schema(
        request={"multipart/form-data": PhotosSerializer},
        responses={201: ObservationSerializer, **WRITE_ERRORS},
        parameters=[IDEMPOTENCY_HEADER],
        summary="Add photographs to an observation before it is released",
    )
    @action(detail=True, methods=["post"])
    @idempotent
    def photos(self, request, pk=None):
        observation = self.get_object()
        self._editable(observation)
        data = PhotosSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            added = store_photos(
                ObservationPhoto, "observation", observation, data.validated_data["photos"], request.user
            )
            record(request, "add_evidence", observation, after={"photos": [p.file.name for p in added]})
        return Response(ObservationSerializer(observation).data, status=201)


def _download(request, photo):
    record(request, "download", photo)
    return FileResponse(
        photo.file.open("rb"),
        as_attachment=True,
        filename=photo.original_name or photo.file.name.rsplit("/", 1)[-1],
    )


@extend_schema(
    tags=["practicals"],
    responses={(200, "application/octet-stream"): OpenApiTypes.BINARY, 404: ErrorSerializer},
    summary="Download a photograph or scan kept with an observation",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def observation_photo(request, pk: int):
    photo = get_object_or_404(
        ObservationPhoto.objects.filter(observation__in=visible_observations(request.user)), pk=pk
    )
    return _download(request, photo)


# ---- Competency ---------------------------------------------------------------------------------------


@extend_schema(tags=["competency"])
class FrameworkViewSet(viewsets.ReadOnlyModelViewSet):
    """Competency frameworks: occupational standards with units, elements and performance criteria. Course
    administrators import them; everyone signed in can read them."""

    serializer_class = FrameworkSerializer
    permission_classes = [RolePermission]
    parser_classes = PARSERS
    queryset = CompetencyFramework.objects.all()

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "with_units": self.action != "list"}

    @extend_schema(
        request={
            "application/json": FrameworkImportSerializer,
            "multipart/form-data": FrameworkImportSerializer,
        },
        responses={201: FrameworkSerializer, **WRITE_ERRORS},
        parameters=[IDEMPOTENCY_HEADER],
        summary="Import a framework from JSON, or from a CSV of one row per performance criterion",
    )
    @action(detail=False, methods=["post"], url_path="import")
    @idempotent
    def import_framework(self, request):
        if not has_role(request.user, *SITE_ADMIN_ROLES):
            raise PermissionDenied("Only course administrators import competency frameworks.")
        data = FrameworkImportSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            framework = data.save(created_by=request.user, updated_by=request.user)
            units = framework.units.count()
            record(request, "import", framework, after={**snapshot(framework), "units": units})
        return Response(FrameworkSerializer(framework).data, status=201)


@extend_schema(tags=["competency"])
class AssignmentMapViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Assignments that give evidence towards a performance criterion."""

    serializer_class = AssignmentMapSerializer
    permission_classes = [RolePermission]

    def get_queryset(self):
        qs = AssignmentCompetencyMap.objects.filter(site__in=visible_sites(self.request.user))
        for name, field in (("site", "site_id"), ("assignment", "assignment_id")):
            value = self.request.query_params.get(name)
            if value:
                qs = qs.filter(**{field: value})
        return qs

    @extend_schema(
        request=AssignmentMapSerializer,
        responses={201: AssignmentMapSerializer, **WRITE_ERRORS},
        parameters=[IDEMPOTENCY_HEADER],
        summary="Map an assignment to a performance criterion",
    )
    @idempotent
    def create(self, request):
        from assessments.models import Assignment

        # The assignment's site is settled before anything else is looked at (item 1.15).
        raw = request.data.get("assignment")
        assignment = None
        if str(raw).isdigit():
            assignment = (
                Assignment.objects.filter(pk=int(raw), site__in=visible_sites(request.user))
                .select_related("site")
                .first()
            )
        if assignment is None:
            return Response({"assignment": [f'Invalid pk "{raw}" - object does not exist.']}, status=400)
        if not can_teach(request.user, assignment.site):
            raise PermissionDenied("Only the site's teaching staff can do this.")
        data = AssignmentMapSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        pc = data.validated_data["performance_criterion"]
        if not SiteFramework.objects.filter(
            site=assignment.site, framework_id=pc.element.unit.framework_id
        ).exists():
            return Response(
                {"performance_criterion": [f"{pc.code} is not in a framework this site follows."]}, status=400
            )
        with transaction.atomic():
            mapping, created = AssignmentCompetencyMap.objects.get_or_create(
                assignment_id=assignment.id,
                performance_criterion=pc,
                defaults={"site": assignment.site, "created_by": request.user, "updated_by": request.user},
            )
            if created:
                record(request, "map", mapping, after=snapshot(mapping))
        return Response(AssignmentMapSerializer(mapping).data, status=201)

    @extend_schema(
        responses={204: None, **WRITE_ERRORS},
        parameters=[IDEMPOTENCY_HEADER],
        summary="Remove an assignment's mapping",
    )
    @idempotent
    def destroy(self, request, pk=None):
        mapping = self.get_object()
        if not can_teach(request.user, mapping.site):
            raise PermissionDenied("Only the site's teaching staff can do this.")
        with transaction.atomic():
            before, entity_id = snapshot(mapping), mapping.pk
            mapping.delete()
            record(request, "delete", mapping, before=before, entity_id=entity_id)
        return Response(status=204)


def _result_state(result) -> dict:
    state = snapshot(result)
    state["evidence_observations"] = sorted(result.evidence_observations.values_list("id", flat=True))
    return state


@extend_schema(tags=["competency"])
class CompetencyResultViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Competency results: one per student and unit on a site, confirmed by an assessor. Recording again
    replaces the result; the audit log keeps what it was."""

    serializer_class = CompetencyResultSerializer
    permission_classes = [RolePermission]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        person = person_of(user)
        mine = Q(student=person) if person is not None else Q(pk__in=[])
        qs = CompetencyResult.objects.filter(mine | Q(site__in=assessed_sites(user)))
        for name, field in (("site", "site_id"), ("student", "student_id"), ("unit", "unit_id")):
            value = self.request.query_params.get(name)
            if value:
                qs = qs.filter(**{field: value})
        return qs.select_related("student", "unit", "assessor").prefetch_related("evidence_observations")

    @extend_schema(
        request=CompetencyResultSerializer,
        responses={200: CompetencyResultSerializer, 201: CompetencyResultSerializer, **WRITE_ERRORS},
        parameters=[IDEMPOTENCY_HEADER],
        summary="Confirm a student's result on a unit of competence (competent needs every critical "
        "criterion passed in a released observation, and evidence)",
    )
    @idempotent
    def create(self, request):
        data = CompetencyResultSerializer(data=request.data, context={"request": request})
        data.is_valid(raise_exception=True)  # the site is settled first: AssessedSite
        v = data.validated_data
        assessor = staff_person(request.user)
        site, student, unit = v["site"], v["student"], v["unit"]
        if v["status"] == CompetencyResult.Status.COMPETENT:
            missing = missing_critical(site, student, unit)
            if missing:
                listed = "; ".join(f"{c.task.title}: {c.text}" for c in missing)
                refuse(
                    f"Not every critical criterion for {unit.code} has been passed in a released "
                    "observation. "
                    f"Still to pass: {listed}.",
                    "criteria_not_met",
                )
            if not v.get("evidence_observations") and not v.get("evidence_submission_ids"):
                return Response(
                    {"evidence_observations": ["Give the observations or submissions that show competence."]},
                    status=400,
                )
        with transaction.atomic():
            result = (
                CompetencyResult.objects.select_for_update()
                .filter(site=site, student=student, unit=unit)
                .first()
            )
            created = result is None
            before = None if created else _result_state(result)
            if created:
                result = CompetencyResult(site=site, student=student, unit=unit, created_by=request.user)
            result.status = v["status"]
            result.assessor = assessor
            result.decided_on = v["decided_on"]
            result.comments = v.get("comments", "")
            result.client_recorded_at = v.get("client_recorded_at")
            result.evidence_submission_ids = v.get("evidence_submission_ids", [])
            result.updated_by = request.user
            result.save()
            result.evidence_observations.set(v.get("evidence_observations", []))
            record(request, "competency_result", result, before=before, after=_result_state(result))
        _notify(
            student,
            title=f"Competency recorded: {unit.code}",
            body=f"{site.code}: {result.get_status_display()} in {unit.title}.",
            link=f"/sites/{site.id}",
            dedupe_key=f"competency:{result.id}:{result.updated_at.timestamp()}",
        )
        return Response(CompetencyResultSerializer(result).data, status=201 if created else 200)


SheetSerializer = inline_serializer(
    "CompetencySheet",
    {
        "site": serializers.CharField(),
        "units": serializers.ListField(child=serializers.DictField()),
        "rows": serializers.ListField(child=serializers.DictField()),
    },
)


def _site_for_reading(user, pk: int) -> CourseSite:
    sites = CourseSite.objects.filter(
        Q(pk__in=visible_sites(user).values("pk")) | Q(pk__in=named_sites(user).values("pk"))
    )
    return get_object_or_404(sites, pk=pk)


@extend_schema(
    tags=["competency"],
    parameters=[OpenApiParameter("student", int, description="One student's LMS person id (staff only)")],
    responses={200: SheetSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="Each student's standing per unit of competence: the computed suggestion and the result recorded",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def competency_record(request, pk: int):
    site = _site_for_reading(request.user, pk)
    units = [
        {
            "id": u.id,
            "code": u.code,
            "title": u.title,
            "framework": f"{u.framework.code} v{u.framework.version}",
        }
        for u in site_units(site)
    ]
    if can_assess(request.user, site):
        students = site_students(site)
        wanted = request.query_params.get("student")
        if wanted:
            students = [s for s in students if str(s.id) == wanted]
        return Response({"site": site.code, "units": units, "rows": competency_sheet(site, students)})
    if site_role(request.user, site) == Membership.SiteRole.STUDENT:
        rows = competency_sheet(site, [person_of(request.user)])
        for cell in rows[0]["units"]:  # a student sees the result, not the working towards it
            for key in ("suggested", "critical_criteria", "missing_critical"):
                cell.pop(key)
        return Response({"site": site.code, "units": units, "rows": rows})
    raise PermissionDenied("Only the site's assessors and its students can see competency records.")


# ---- Logbook ------------------------------------------------------------------------------------------


def visible_entries(user):
    person = person_of(user)
    mine = Q(student=person) if person is not None else Q(pk__in=[])
    return LogbookEntry.objects.filter(mine | Q(site__in=taught_sites(user)))


@extend_schema(tags=["logbook"])
class LogbookViewSet(IdempotentWrites, viewsets.ModelViewSet):
    """The student's practical logbook (item 3.14). Students write their own entries; the site's teaching
    staff sign them off or return them with a comment. A signed entry is locked."""

    serializer_class = LogbookEntrySerializer
    permission_classes = [RolePermission]
    parser_classes = PARSERS
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = visible_entries(self.request.user).select_related("site", "student", "supervisor")
        for name, field in (("site", "site_id"), ("student", "student_id"), ("status", "status")):
            value = self.request.query_params.get(name)
            if value:
                qs = qs.filter(**{field: value})
        return qs.prefetch_related("photos")

    def get_object(self):
        entry = super().get_object()
        if self.action in ("update", "partial_update", "destroy", "photos"):
            if entry.student_id != getattr(person_of(self.request.user), "id", None):
                raise PermissionDenied(
                    "Only the student can change their own entry; return it with a comment instead."
                )
            if entry.status == LogbookEntry.Status.SIGNED:
                refuse("This entry has been signed off and is locked.", "locked")
        return entry

    def perform_create(self, serializer):
        photos = serializer.validated_data.pop("photos", [])
        with transaction.atomic():
            entry = serializer.save(
                student=person_of(self.request.user),
                created_by=self.request.user,
                updated_by=self.request.user,
            )
            store_photos(LogbookPhoto, "entry", entry, photos, self.request.user)
            record(self.request, "create", entry, after=snapshot(entry))

    def perform_update(self, serializer):
        serializer.validated_data.pop("photos", None)
        site = serializer.validated_data.pop("site", None)
        if site is not None and site != serializer.instance.site:
            raise PermissionDenied("An entry stays on the course it was written for.")
        with transaction.atomic():
            before = snapshot(serializer.instance)
            entry = serializer.save(status=LogbookEntry.Status.PENDING, updated_by=self.request.user)
            record(self.request, "update", entry, before=before, after=snapshot(entry))

    def perform_destroy(self, instance):
        with transaction.atomic():
            before, entity_id = snapshot(instance), instance.pk
            instance.delete()
            record(self.request, "delete", instance, before=before, entity_id=entity_id)

    @extend_schema(
        request=LogbookReviewSerializer,
        responses={200: LogbookEntrySerializer, **WRITE_ERRORS},
        parameters=[IDEMPOTENCY_HEADER],
        summary="Sign an entry off (it is then locked), or return it to the student with a comment",
    )
    @action(detail=True, methods=["post"])
    @idempotent
    def review(self, request, pk=None):
        entry = self.get_object()
        if not can_teach(request.user, entry.site):
            raise PermissionDenied("Only the site's teaching staff sign logbook entries.")
        if entry.status == LogbookEntry.Status.SIGNED:
            refuse("This entry has been signed off already and is locked.", "locked")
        supervisor = staff_person(request.user)
        data = LogbookReviewSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        signing = data.validated_data["decision"] == "sign"
        with transaction.atomic():
            before = snapshot(entry)
            entry.status = LogbookEntry.Status.SIGNED if signing else LogbookEntry.Status.RETURNED
            entry.supervisor = supervisor
            entry.reviewed_at = timezone.now()
            entry.review_comment = data.validated_data.get("comment", "")
            entry.updated_by = request.user
            entry.save()
            after = snapshot(entry)
            after["client_recorded_at"] = data.validated_data.get("client_recorded_at")
            record(request, "sign" if signing else "return", entry, before=before, after=after)
        _notify(
            entry.student,
            title=f"Logbook {'signed off' if signing else 'returned'}: {entry.work_date:%d/%m/%Y}",
            body=entry.review_comment[:500] or entry.task,
            link=f"/sites/{entry.site_id}",
            dedupe_key=f"logbook:{entry.id}:{entry.status}:{entry.reviewed_at.timestamp()}",
        )
        return Response(LogbookEntrySerializer(entry).data)

    @extend_schema(
        request={"multipart/form-data": PhotosSerializer},
        responses={201: LogbookEntrySerializer, **WRITE_ERRORS},
        parameters=[IDEMPOTENCY_HEADER],
        summary="Add photographs to an entry not yet signed off",
    )
    @action(detail=True, methods=["post"])
    @idempotent
    def photos(self, request, pk=None):
        entry = self.get_object()
        data = PhotosSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            added = store_photos(LogbookPhoto, "entry", entry, data.validated_data["photos"], request.user)
            record(request, "add_evidence", entry, after={"photos": [p.file.name for p in added]})
        return Response(LogbookEntrySerializer(entry).data, status=201)


@extend_schema(
    tags=["logbook"],
    responses={(200, "application/octet-stream"): OpenApiTypes.BINARY, 404: ErrorSerializer},
    summary="Download a photograph kept with a logbook entry",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def logbook_photo(request, pk: int):
    photo = get_object_or_404(LogbookPhoto.objects.filter(entry__in=visible_entries(request.user)), pk=pk)
    return _download(request, photo)


HoursRow = inline_serializer(
    "LogbookHours",
    {
        "unit_type": serializers.CharField(),
        "label": serializers.CharField(),
        "signed_hours": serializers.CharField(),
        "waiting_hours": serializers.CharField(),
    },
    many=True,
)


@extend_schema(
    tags=["logbook"],
    parameters=[OpenApiParameter("student", int, description="One student's LMS person id (staff only)")],
    responses={
        200: inline_serializer(
            "LogbookTotals",
            {
                "site": serializers.CharField(),
                "rows": inline_serializer(
                    "LogbookTotalsRow",
                    {
                        "person_id": serializers.IntegerField(),
                        "student_no": serializers.CharField(),
                        "name": serializers.CharField(),
                        "hours": HoursRow,
                    },
                    many=True,
                ),
            },
        ),
        403: ErrorSerializer,
        404: ErrorSerializer,
    },
    summary="Hours of logbook work by kind of place: signed off, and still waiting",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def logbook_totals(request, pk: int):
    site = get_object_or_404(visible_sites(request.user), pk=pk)
    entries = LogbookEntry.objects.filter(site=site)
    if can_teach(request.user, site):
        students = site_students(site)
        wanted = request.query_params.get("student")
        if wanted:
            students = [s for s in students if str(s.id) == wanted]
    elif site_role(request.user, site) == Membership.SiteRole.STUDENT:
        students = [person_of(request.user)]
    else:
        raise PermissionDenied("Only the site's teaching staff and its students can see logbook totals.")
    rows = [
        {
            "person_id": s.id,
            "student_no": s.external_id,
            "name": s.full_name,
            "hours": hours_by_unit(entries.filter(student=s)),
        }
        for s in students
    ]
    return Response({"site": site.code, "rows": rows})


# ---- Portfolio ----------------------------------------------------------------------------------------


@extend_schema(
    tags=["logbook"],
    parameters=[
        OpenApiParameter("site", int, description="One site only; otherwise every site"),
        OpenApiParameter("student", int, description="A student's LMS person id, for teaching staff"),
        OpenApiParameter("as", str, enum=["json", "html"], description="html for a page to print or keep"),
    ],
    responses={
        (200, "application/json"): OpenApiTypes.OBJECT,
        (200, "text/html"): OpenApiTypes.STR,
        403: ErrorSerializer,
        404: ErrorSerializer,
    },
    summary="A student's practical portfolio: signed logbook entries, released observations and "
    "competency results",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def portfolio_export(request):
    user = request.user
    site_id = request.query_params.get("site")
    wanted = request.query_params.get("student")
    if wanted:
        sites = taught_sites(user)
        if site_id:
            sites = sites.filter(pk=site_id)
        student = get_object_or_404(
            PersonRef.objects.filter(
                memberships__site__in=sites,
                memberships__role=Membership.SiteRole.STUDENT,
            ).distinct(),
            pk=wanted,
        )
    else:
        student = person_of(user)
        if student is None:
            raise PermissionDenied("Only students have a practical portfolio.")
        sites = CourseSite.objects.all()
        if site_id:
            sites = sites.filter(pk=site_id)
    # Every course the person was a student on, including past ones: the portfolio is kept after the course
    # ends and after graduation (item 5.15), so a membership no longer active still counts.
    sites = sites.filter(
        memberships__person=student, memberships__role=Membership.SiteRole.STUDENT
    ).distinct()
    data = portfolio(student, list(sites.order_by("term_code", "code")))
    html = request.query_params.get("as") == "html"
    record(
        request,
        "export",
        student,
        after={"portfolio": [s["site"]["code"] for s in data["sites"]], "as": "html" if html else "json"},
    )
    if html:
        response = HttpResponse(portfolio_html(data), content_type="text/html; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="portfolio-{student.external_id}.html"'
        return response
    return Response(data)


router = DefaultRouter()
router.register("practical-assessors", PracticalAssessorViewSet, basename="practical-assessor")
router.register("practical-tasks", PracticalTaskViewSet, basename="practical-task")
router.register("practical-criteria", PracticalCriterionViewSet, basename="practical-criterion")
router.register("observations", ObservationViewSet, basename="observation")
router.register("competency-frameworks", FrameworkViewSet, basename="competency-framework")
router.register("site-frameworks", SiteFrameworkViewSet, basename="site-framework")
router.register("competency-maps", AssignmentMapViewSet, basename="competency-map")
router.register("competency-results", CompetencyResultViewSet, basename="competency-result")
router.register("logbook", LogbookViewSet, basename="logbook")
urlpatterns = [
    path("observation-photos/<int:pk>/download/", observation_photo, name="observation-photo"),
    path("logbook-photos/<int:pk>/download/", logbook_photo, name="logbook-photo"),
    path("sites/<int:pk>/competency/", competency_record, name="site-competency"),
    path("sites/<int:pk>/logbook-totals/", logbook_totals, name="site-logbook-totals"),
    path("portfolio/", portfolio_export, name="portfolio"),
    *router.urls,
]
