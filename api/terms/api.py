"""The term calendar for course administrators (item 7.12).

Course administrators and administrators keep the calendar: a term's code, its teaching dates, the date its
sites close to new work and the grace after it. Terms the SRMS supplies keep its code and teaching dates;
the close date and grace stay the LMS's to set. The auditor reads everything. Every change is audited, and
every download of a site's archive.
"""

from django.db.models import Count
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from audit.services import record
from core.serializers import ErrorSerializer
from core.views import AuditedModelViewSet
from courses.models import CourseSite
from iam.models import Role
from iam.permissions import role_required
from terms import lifecycle
from terms.models import SiteArchive, Term

KEEPERS = (Role.ADMINISTRATOR, Role.COURSE_ADMIN)
READERS = KEEPERS + (Role.AUDITOR,)
SRMS_DATES = "This term comes from the SRMS: its name and dates of teaching are set there."


class TermSerializer(serializers.ModelSerializer):
    phase = serializers.SerializerMethodField(
        help_text="upcoming, teaching, ended (still taking work), grace, closed or archived"
    )
    grace_days_applied = serializers.SerializerMethodField(help_text="The grace in force, own or default")
    locks_at = serializers.SerializerMethodField(help_text="When the sites become read-only")
    archive_due_on = serializers.SerializerMethodField(help_text="When the sites are archived")
    site_count = serializers.SerializerMethodField(help_text="Course sites with this term code")
    source_name = serializers.CharField(source="get_source_display", read_only=True)

    class Meta:
        model = Term
        fields = (
            "id",
            "code",
            "name",
            "starts_on",
            "ends_on",
            "closes_on",
            "grace_days",
            "grace_days_applied",
            "source",
            "source_name",
            "phase",
            "locks_at",
            "archive_due_on",
            "closed_at",
            "archived_at",
            "site_count",
        )
        read_only_fields = ("source", "closed_at", "archived_at")

    def get_phase(self, term) -> str:
        return lifecycle.term_phase(term)

    def get_grace_days_applied(self, term) -> int:
        return lifecycle.grace_days(term)

    def get_locks_at(self, term) -> str:
        return lifecycle.locks_at(term).isoformat()

    def get_archive_due_on(self, term) -> str:
        months = self.context.get("archive_months")
        return lifecycle.archive_due_on(term, months).isoformat()

    def get_site_count(self, term) -> int:
        counts = self.context.get("site_counts")
        if counts is None:
            return CourseSite.objects.filter(term_code=term.code).count()
        return counts.get(term.code, 0)

    def validate_code(self, value):
        value = value.strip()
        if self.instance is not None and value != self.instance.code:
            if self.instance.source == Term.Source.SRMS:
                raise serializers.ValidationError("This term comes from the SRMS: its code is changed there.")
            if CourseSite.objects.filter(term_code=self.instance.code).exists():
                raise serializers.ValidationError("Sites already use this code; it cannot be changed.")
        return value

    def validate(self, attrs):
        term = self.instance
        if term is not None and term.archived_at is not None:
            raise serializers.ValidationError("This term is archived: its dates can no longer change.")
        if term is not None and term.source == Term.Source.SRMS:
            for field in ("name", "starts_on", "ends_on"):
                if field in attrs and attrs[field] != getattr(term, field):
                    raise serializers.ValidationError({field: SRMS_DATES})
        starts = attrs.get("starts_on", getattr(term, "starts_on", None))
        ends = attrs.get("ends_on", getattr(term, "ends_on", None))
        closes = attrs.get("closes_on", getattr(term, "closes_on", None))
        if starts and ends and ends < starts:
            raise serializers.ValidationError({"ends_on": "Teaching cannot end before it starts."})
        if ends and closes and closes < ends:
            raise serializers.ValidationError(
                {"closes_on": "Sites cannot close before teaching ends; choose the end of teaching or later."}
            )
        return attrs


class TermSiteSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()
    title = serializers.CharField()
    phase = serializers.CharField(help_text="open, grace, closed or archived")
    archive = serializers.IntegerField(allow_null=True, help_text="The archive's id, for its download")
    archive_size = serializers.IntegerField(allow_null=True)
    archive_made_at = serializers.DateTimeField(allow_null=True)


class MissingTermSerializer(serializers.Serializer):
    term_code = serializers.CharField()
    sites = serializers.IntegerField()


@extend_schema_view(
    list=extend_schema(summary="The term calendar (item 7.12)"),
    create=extend_schema(summary="Add a term to the calendar"),
    retrieve=extend_schema(summary="One term"),
    partial_update=extend_schema(summary="Change a term's dates; an SRMS term only its close date and grace"),
    destroy=extend_schema(
        summary="Remove a term no site uses and that has not closed",
        responses={204: None, 409: ErrorSerializer},
    ),
)
class TermViewSet(AuditedModelViewSet):
    serializer_class = TermSerializer
    read_roles = READERS
    write_roles = KEEPERS
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return Term.objects.all()

    def get_serializer_context(self):
        counts = CourseSite.objects.order_by().values("term_code").annotate(n=Count("id"))
        return {
            **super().get_serializer_context(),
            "archive_months": lifecycle.archive_months(),
            "site_counts": {row["term_code"]: row["n"] for row in counts},
        }

    def destroy(self, request, *args, **kwargs):
        term = self.get_object()
        if term.closed_at is not None or CourseSite.objects.filter(term_code=term.code).exists():
            return Response(
                {"code": "in_use", "detail": "Sites belong to this term, or it has closed: it is kept."},
                status=409,
            )
        return super().destroy(request, *args, **kwargs)

    @extend_schema(
        responses={200: TermSiteSerializer(many=True)},
        summary="The term's course sites, with each one's phase and archive",
    )
    @action(detail=True, methods=["get"])
    def sites(self, request, pk=None):
        term = self.get_object()
        phase = lifecycle.term_phase(term)
        site_phase = phase if phase in (lifecycle.GRACE, lifecycle.CLOSED) else lifecycle.OPEN
        rows = []
        for site in CourseSite.objects.filter(term_code=term.code).select_related("archive").order_by("code"):
            archive = getattr(site, "archive", None)
            rows.append(
                {
                    "id": site.pk,
                    "code": site.code,
                    "title": site.title,
                    "phase": lifecycle.ARCHIVED if archive else site_phase,
                    "archive": archive.pk if archive else None,
                    "archive_size": archive.size if archive else None,
                    "archive_made_at": archive.made_at if archive else None,
                }
            )
        return Response(TermSiteSerializer(rows, many=True).data)

    @extend_schema(
        responses={200: MissingTermSerializer(many=True)},
        summary="Term codes that sites use but the calendar does not hold: such sites never close",
    )
    @action(detail=False, methods=["get"])
    def missing(self, request):
        known = Term.objects.values("code")
        rows = (
            CourseSite.objects.exclude(term_code="")
            .exclude(term_code__in=known)
            .order_by("term_code")
            .values("term_code")
            .annotate(sites=Count("id"))
        )
        return Response(MissingTermSerializer(list(rows), many=True).data)


@extend_schema(
    responses={(200, "application/zip"): OpenApiTypes.BINARY, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="Download the read-only archive of a course site (item 7.12)",
)
@api_view(["GET"])
@permission_classes([role_required(*READERS)])
def download_archive(request, pk: int):
    archive = get_object_or_404(SiteArchive.objects.select_related("site"), pk=pk)
    record(
        request,
        "download",
        archive.site,
        after={"archive": archive.pk, "sha256": archive.sha256, "at": timezone.now().isoformat()},
    )
    return FileResponse(
        archive.file.open("rb"), as_attachment=True, filename=archive.file.name.rsplit("/", 1)[-1]
    )


router = SimpleRouter()
router.register("terms", TermViewSet, basename="term")
