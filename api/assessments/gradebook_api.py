"""Gradebook categories (2.28), the export (2.29), the working of the coursework total (2.30) and sending
coursework to the SRMS (2.31, 3.18)."""

import csv

from django.db import transaction
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from assessments.models import GradeCategory, SrmsTransfer
from assessments.services import coursework_working, gradebook, public_working
from audit.services import record, record_event
from core.serializers import ErrorSerializer
from courses.access import ADMIN, TaughtRecord, can_teach, person_of, site_role, visible_sites
from courses.api import TeachingViewSet
from courses.models import CourseSite, Membership
from iam.permissions import RolePermission
from people.models import PersonRef

# Spreadsheet programs run a cell that starts with one of these as a formula (as the audit export).
FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
STATE_WORDS = {
    "graded": "counted",
    "zero": "missing, counted as 0",
    "pending": "pending",
    "not_due": "not yet due",
    "dropped": "dropped",
}


class GradeCategorySerializer(serializers.ModelSerializer):
    site = TaughtRecord(CourseSite)

    class Meta:
        model = GradeCategory
        fields = ("id", "site", "name", "weight", "drop_lowest", "position")

    def validate(self, attrs):
        if self.instance is not None and "site" in attrs and attrs["site"] != self.instance.site:
            raise serializers.ValidationError({"site": ["A category cannot move to another site."]})
        site = attrs.get("site") or self.instance.site
        name = attrs.get("name")
        if (
            name
            and GradeCategory.objects.filter(site=site, name=name)
            .exclude(pk=getattr(self.instance, "pk", None))
            .exists()
        ):
            raise serializers.ValidationError({"name": ["The site already has a category of this name."]})
        return attrs


@extend_schema_view(
    list=extend_schema(
        parameters=[OpenApiParameter("site", OpenApiTypes.INT, description="Only this site")],
        summary="Gradebook categories with their weights and drop-lowest rule",
    )
)
class GradeCategoryViewSet(TeachingViewSet):
    """Categories weight the parts of the coursework (item 2.28). Place assignments, quizzes and practical
    tasks in them through their own category fields. With none, the total is worked as before."""

    serializer_class = GradeCategorySerializer
    queryset = GradeCategory.objects.none()

    def get_queryset(self):
        qs = GradeCategory.objects.filter(site__in=visible_sites(self.request.user)).select_related("site")
        site = self.request.query_params.get("site")
        return qs.filter(site_id=site) if site else qs

    def site_of(self, instance):
        return instance.site

    def site_from_data(self, data):
        return data["site"]


class WorkingItemSerializer(serializers.Serializer):
    kind = serializers.CharField(help_text="assignment, quiz, practical or forum")
    id = serializers.IntegerField()
    title = serializers.CharField()
    category = serializers.IntegerField(allow_null=True)
    weight = serializers.CharField()
    state = serializers.CharField(help_text="graded, zero, pending, not_due or dropped")
    percent = serializers.CharField(allow_null=True)
    max_mark = serializers.CharField(required=False, help_text="Assignments only, as are the fields below")
    due_at = serializers.DateTimeField(required=False, help_text="The student's own due date")
    extended = serializers.BooleanField(required=False)
    late = serializers.BooleanField(required=False)
    raw_mark = serializers.CharField(required=False, allow_null=True)
    penalty = serializers.CharField(required=False, allow_null=True)
    final_mark = serializers.CharField(required=False, allow_null=True)


class WorkingCategorySerializer(serializers.Serializer):
    id = serializers.IntegerField(allow_null=True, help_text="null for the items in no category")
    name = serializers.CharField()
    weight = serializers.CharField()
    drop_lowest = serializers.IntegerField()
    percent = serializers.CharField(allow_null=True)
    counted = serializers.BooleanField()


class WorkingSerializer(serializers.Serializer):
    student_no = serializers.CharField()
    name = serializers.CharField()
    coursework_percent = serializers.CharField(allow_null=True)
    uses_categories = serializers.BooleanField()
    categories = WorkingCategorySerializer(many=True)
    items = WorkingItemSerializer(many=True)


@extend_schema(
    parameters=[
        OpenApiParameter("person", OpenApiTypes.INT, description="Teaching staff: the student (person id)")
    ],
    responses={200: WorkingSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="How a coursework total was worked out: which items counted, which are pending, which counted "
    "as zero, penalties and categories",
    description="A student sees their own, from released marks only; teaching staff see any student's.",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def working(request, pk: int):
    site = get_object_or_404(visible_sites(request.user), pk=pk)
    role = site_role(request.user, site)
    if role == Membership.SiteRole.STUDENT:
        person, released_only = person_of(request.user), True
    elif can_teach(request.user, site) or role == "auditor":
        person_id = request.query_params.get("person")
        person = get_object_or_404(
            PersonRef.objects.filter(
                memberships__site=site, memberships__role=Membership.SiteRole.STUDENT
            ).distinct(),
            pk=person_id if str(person_id or "").isdigit() else 0,
        )
        released_only = False
    else:
        raise PermissionDenied("You are not a member of this course.")
    data = public_working(site, person, released_only=released_only)
    return Response(
        WorkingSerializer({"student_no": person.external_id, "name": person.full_name, **data}).data
    )


def _cell(value) -> str:
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(FORMULA_START) else text


class _Echo:
    def write(self, value):
        return value


def _working_text(items) -> str:
    parts = []
    for item in items:
        state = STATE_WORDS[item["state"]]
        result = f" {item['percent']}%" if item["percent"] is not None and item["state"] != "zero" else ""
        penalty = f", late penalty {item['penalty']}" if item.get("penalty") not in (None, "0.00") else ""
        parts.append(f"{item['title']}: {state}{result}{penalty}")
    return "; ".join(parts)


@extend_schema(
    responses={
        (200, "text/csv"): OpenApiResponse(OpenApiTypes.STR),
        403: ErrorSerializer,
        404: ErrorSerializer,
    },
    summary="The gradebook as a spreadsheet (CSV): every mark, each category, the total and its working",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def export(request, pk: int):
    site = get_object_or_404(visible_sites(request.user), pk=pk)
    if not can_teach(request.user, site) and site_role(request.user, site) != "auditor":
        raise PermissionDenied("Only the site's teaching staff can export the gradebook.")
    book = gradebook(site)
    categories = book["categories"]
    members = {
        m.person.external_id: m.person
        for m in Membership.objects.filter(
            site=site, role=Membership.SiteRole.STUDENT, is_active=True
        ).select_related("person")
    }
    header = ["Student number", "Name"]
    header += [f"{a['title']} (out of {a['max_mark']})" for a in book["assignments"]]
    header += [f"{q['title']} (%)" for q in book["quizzes"]]
    practicals = list(site.practical_tasks.filter(is_published=True, weight__gt=0))
    header += [f"{t.title} (%)" for t in practicals]
    header += [f"{c['name']} (%)" for c in categories]
    header += ["Coursework (%)", "Working"]
    record_event(
        request,
        "gradebook_exported",
        "courses.coursesite",
        after={"site": site.code, "rows": len(book["rows"])},
    )

    def lines():
        writer = csv.writer(_Echo())
        yield "﻿" + writer.writerow([_cell(c) for c in header])
        for row in book["rows"]:
            person = members.get(row["student_no"])
            work = coursework_working(site, person)
            by_key = {(i["kind"], i["id"]): i for i in work["items"]}
            cells = [row["student_no"], row["name"]]
            for a in book["assignments"]:
                item = by_key.get(("assignment", a["id"]))
                cell = row["marks"][str(a["id"])]
                cells.append(cell["mark"] if cell["mark"] is not None else STATE_WORDS.get(item["state"], ""))
            for q in book["quizzes"]:
                cells.append(row["quizzes"][str(q["id"])]["percent"] or "")
            for t in practicals:
                item = by_key.get(("practical", t.id))
                cells.append(
                    item["percent"] if item and item["percent"] is not None else STATE_WORDS[item["state"]]
                )
            cells += [row["categories"].get(str(c["id"])) or "" for c in categories]
            cells += [row["coursework_percent"] or "", _working_text(work["items"])]
            yield writer.writerow([_cell(c) for c in cells])

    response = StreamingHttpResponse(lines(), content_type="text/csv; charset=utf-8")
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
    response["Content-Disposition"] = f'attachment; filename="{site.code}-gradebook-{stamp}.csv"'
    return response


class CourseworkTransferSerializer(serializers.Serializer):
    student_no = serializers.CharField()
    percent = serializers.CharField()
    outcome = serializers.CharField(help_text="accepted, locked (already locked in the SRMS) or unknown")


class CourseworkSentSerializer(serializers.Serializer):
    site = serializers.CharField()
    sent_at = serializers.DateTimeField()
    accepted = serializers.ListField(child=serializers.CharField())
    locked = serializers.ListField(child=serializers.CharField())
    unknown = serializers.ListField(child=serializers.CharField())
    students = CourseworkTransferSerializer(many=True)


@extend_schema(
    request=None,
    responses={
        200: CourseworkSentSerializer,
        403: ErrorSerializer,
        404: ErrorSerializer,
        409: ErrorSerializer,
        502: ErrorSerializer,
    },
    summary="Send this site's coursework totals to the SRMS now; shows what was accepted and what was locked",
    description="Once the SRMS holds a student's coursework, that student's marks on the site are locked in "
    "the LMS (item 3.18): a later change is refused with code locked_in_srms.",
)
@api_view(["POST"])
@permission_classes([RolePermission])
def send_coursework(request, pk: int):
    from integration.client import IntegrationError
    from integration.srms import push_marks

    site = get_object_or_404(visible_sites(request.user), pk=pk)
    if site_role(request.user, site) not in (ADMIN, Membership.SiteRole.LECTURER):
        raise PermissionDenied("Only the site's lecturer sends coursework to the SRMS.")
    if site.source != CourseSite.Source.SRMS:
        return Response(
            {"code": "not_srms", "detail": "This site is not an SRMS course offering."}, status=409
        )
    try:
        result = push_marks(site)
    except IntegrationError as error:
        return Response(
            {"code": "srms_unavailable", "detail": f"The SRMS could not take the coursework now: {error}"},
            status=502,
        )
    now = timezone.now()
    outcome_of = {no: SrmsTransfer.Outcome.ACCEPTED for no in result.get("accepted", [])}
    outcome_of.update({no: SrmsTransfer.Outcome.LOCKED for no in result.get("locked", [])})
    people = {
        p.external_id: p
        for p in PersonRef.objects.filter(
            kind=PersonRef.Kind.STUDENT, external_id__in=[m["student_no"] for m in result["sent"]]
        )
    }
    rows = []
    with transaction.atomic():
        for sent in result["sent"]:
            person = people.get(sent["student_no"])
            outcome = outcome_of.get(sent["student_no"], SrmsTransfer.Outcome.UNKNOWN)
            if person is not None:
                SrmsTransfer.objects.create(
                    site=site,
                    student=person,
                    percent=sent["mark"],
                    outcome=outcome,
                    sent_at=now,
                    sent_by=request.user,
                )
            rows.append({"student_no": sent["student_no"], "percent": sent["mark"], "outcome": outcome})
        record(
            request,
            "coursework_sent",
            site,
            after={
                "sent": len(rows),
                "accepted": result.get("accepted", []),
                "locked": result.get("locked", []),
                "unknown": result.get("unknown", []),
            },
        )
    return Response(
        CourseworkSentSerializer(
            {
                "site": site.code,
                "sent_at": now,
                "accepted": result.get("accepted", []),
                "locked": result.get("locked", []),
                "unknown": result.get("unknown", []),
                "students": rows,
            }
        ).data
    )


urlpatterns = [
    path("sites/<int:pk>/gradebook/export/", export, name="site-gradebook-export"),
    path("sites/<int:pk>/coursework/working/", working, name="site-coursework-working"),
    path("sites/<int:pk>/coursework/send/", send_coursework, name="site-coursework-send"),
]
