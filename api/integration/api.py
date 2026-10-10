"""Integration and reference endpoints of the LMS, and the record of integration runs (item 1.23)."""

from django.db.models import Q
from django.urls import path
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, viewsets
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from audit.models import AuditLog
from courses.models import CourseSite
from iam.models import Role
from iam.permissions import RolePermission
from insights.analytics import students_of
from insights.outcomes import course_code_of, site_outcomes, standings
from integration.auth import ServiceKeyAuthentication, scope
from integration.models import CampusRef, IntegrationRun


class ServiceSiteSerializer(serializers.Serializer):
    code = serializers.CharField()
    title = serializers.CharField()
    term_code = serializers.CharField()
    campus_code = serializers.CharField()
    kind = serializers.ChoiceField(choices=CourseSite.Kind.choices)
    is_published = serializers.BooleanField()


class ServiceSiteListSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    results = ServiceSiteSerializer(many=True)


class CampusSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()
    name = serializers.CharField()


@extend_schema(
    responses=ServiceSiteListSerializer,
    summary="Course sites, for sibling systems (scope sites:read)",
    tags=["integration"],
)
@api_view(["GET"])
@authentication_classes([ServiceKeyAuthentication])
@permission_classes([scope("sites:read")])
def sites(request):
    """Course sites for sibling systems (for example to link from the SRMS to the course site)."""
    rows = [
        {
            "code": s.code,
            "title": s.title,
            "term_code": s.term_code,
            "campus_code": s.campus_code,
            "kind": s.kind,
            "is_published": s.is_published,
        }
        for s in CourseSite.objects.all()
    ]
    AuditLog.objects.create(
        action="integration:sites.read",
        entity="integration.serviceclient",
        entity_id=request.auth.pk,
        after={"client": request.auth.name, "count": len(rows)},
    )
    return Response({"count": len(rows), "results": rows})


@extend_schema(responses=CampusSerializer(many=True), summary="Campuses, by the codes the HRMS owns")
@api_view(["GET"])
@permission_classes([RolePermission])
def campuses(request):
    return Response([{"id": c.id, "code": c.code, "name": c.name} for c in CampusRef.objects.all()])


class OutcomeSummaryRowSerializer(serializers.Serializer):
    campus_code = serializers.CharField(allow_blank=True)
    course_code = serializers.CharField(allow_blank=True)
    term_code = serializers.CharField(allow_blank=True)
    student_count = serializers.IntegerField()
    met_count = serializers.IntegerField()
    not_yet_count = serializers.IntegerField()
    no_evidence_count = serializers.IntegerField()


def _outcome_counts(site: CourseSite) -> dict:
    """One site's met / not-yet / no-evidence counts, from released marks (insights.outcomes.standings,
    the same view a student would see of their own standing)."""
    table = standings(site, students_of(site), released_only=True)
    met = not_yet = no_evidence = 0
    for student in table["students"]:
        for cell in student["outcomes"].values():
            if cell["standing"] == "met":
                met += 1
            elif cell["standing"] == "not_yet":
                not_yet += 1
            else:
                no_evidence += 1
    return {"met_count": met, "not_yet_count": not_yet, "no_evidence_count": no_evidence}


@extend_schema(
    responses=OutcomeSummaryRowSerializer(many=True),
    summary="Course-outcome aggregates by campus and course (scope outcomes:read)",
    tags=["integration"],
)
@api_view(["GET"])
@authentication_classes([ServiceKeyAuthentication])
@permission_classes([scope("outcomes:read")])
def outcome_summary(request):
    """Aggregated standings only (item X-02 of the ecosystem gap analysis): no student name or number.
    One row per published site whose course has SRMS-sourced outcomes to stand on; a site with none is
    left out, not sent as zero."""
    rows = []
    sites = CourseSite.objects.filter(is_published=True, source=CourseSite.Source.SRMS).order_by("code")
    for site in sites:
        if not site_outcomes(site):
            continue
        counts = _outcome_counts(site)
        rows.append(
            {
                "campus_code": site.campus_code,
                "course_code": course_code_of(site),
                "term_code": site.term_code,
                "student_count": len(students_of(site)),
                **counts,
            }
        )
    AuditLog.objects.create(
        action="integration:outcome_summary.read",
        entity="integration.serviceclient",
        entity_id=request.auth.pk,
        after={"client": request.auth.name, "count": len(rows)},
    )
    return Response(OutcomeSummaryRowSerializer(rows, many=True).data)


integration_urls = [
    path("sites/", sites, name="integration-sites"),
    path("outcome-summary/", outcome_summary, name="integration-outcome-summary"),
]
reference_urls = [path("campuses/", campuses, name="reference-campuses")]


class RunErrorSerializer(serializers.Serializer):
    ref = serializers.CharField(
        help_text="The row: a completion's reference, a site code, an employee number"
    )
    code = serializers.CharField()
    detail = serializers.CharField()


class IntegrationRunSerializer(serializers.ModelSerializer):
    kind_name = serializers.CharField(source="get_kind_display", read_only=True)
    errors = RunErrorSerializer(many=True, read_only=True)

    class Meta:
        model = IntegrationRun
        fields = (
            "id",
            "kind",
            "kind_name",
            "trigger",
            "started_at",
            "finished_at",
            "ok",
            "failed",
            "errors",
            "stopped",
        )


class IntegrationRunViewSet(viewsets.ReadOnlyModelViewSet):
    """What each push to and pull from the HRMS and the SRMS did, newest first (item 1.23)."""

    queryset = IntegrationRun.objects.none()
    serializer_class = IntegrationRunSerializer
    permission_classes = [RolePermission]
    read_roles = (Role.ADMINISTRATOR, Role.COURSE_ADMIN, Role.AUDITOR)

    @extend_schema(
        parameters=[
            OpenApiParameter("kind", str, enum=[k for k, _ in IntegrationRun.Kind.choices]),
            OpenApiParameter("failed", bool, description="Only runs with a refused row or that stopped"),
        ],
        summary="Integration runs, newest first",
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(summary="One integration run, with each refused row")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    def get_queryset(self):
        qs = IntegrationRun.objects.all()
        params = self.request.query_params
        if params.get("kind"):
            qs = qs.filter(kind=params["kind"])
        if params.get("failed") in ("1", "true"):
            qs = qs.filter(Q(failed__gt=0) | ~Q(stopped=""))
        return qs


run_router = SimpleRouter()
run_router.register("integration-runs", IntegrationRunViewSet, basename="integration-run")
run_urls = run_router.urls
