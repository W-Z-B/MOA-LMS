"""Paper quizzes (item 3.24): for the teaching staff of the quiz's site only.

Make a paper from a quiz, print its question paper, answer sheet and marking key for each version, key the
answer sheets in on a grid or from a CSV file, and see what each student scored. Each keyed sheet is an
attempt at the quiz, so results, release, the gradebook and statistics treat it as any other attempt.
"""

from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import path
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from audit.services import record, snapshot
from core.serializers import ErrorSerializer
from courses.access import can_teach, visible_sites
from courses.models import Membership
from iam.permissions import RolePermission
from paperquizzes import pdf, services
from paperquizzes.models import PaperQuiz, PaperScript
from quizzes.models import Quiz


class NewPaperSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=160)
    sat_on = serializers.DateField(help_text="The day it is sat; the attempts are dated then")
    versions = serializers.IntegerField(min_value=1, max_value=2, default=2, help_text="1 (A) or 2 (A and B)")


class PaperSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    quiz = serializers.IntegerField()
    title = serializers.CharField()
    sat_on = serializers.DateField()
    versions = serializers.ListField(child=serializers.CharField(), help_text="Version labels, A then B")
    questions = serializers.IntegerField()
    keyed = serializers.IntegerField(help_text="Answer sheets keyed in so far")


class GridRowInSerializer(serializers.Serializer):
    student_no = serializers.CharField(allow_blank=True)
    version = serializers.CharField(allow_blank=True)
    answers = serializers.ListField(
        child=serializers.CharField(allow_blank=True), help_text="In printed order"
    )


class GridInSerializer(serializers.Serializer):
    rows = GridRowInSerializer(many=True)


class KeyedResultSerializer(serializers.Serializer):
    saved = serializers.IntegerField()
    errors = serializers.ListField(child=serializers.DictField(), help_text="[{student_no, detail}]")


class CsvSerializer(serializers.Serializer):
    file = serializers.FileField(help_text="CSV: student_no, version, q1, q2 ... in printed order")


def _paper_data(paper: PaperQuiz) -> dict:
    versions = list(paper.versions.all())
    return {
        "id": paper.id,
        "quiz": paper.quiz_id,
        "title": paper.title,
        "sat_on": paper.sat_on,
        "versions": [v.label for v in versions],
        "questions": len(versions[0].items) if versions else 0,
        "keyed": paper.scripts.count(),
    }


def _quiz(request, pk: int) -> Quiz:
    quiz = get_object_or_404(
        Quiz.objects.filter(site__in=visible_sites(request.user)).select_related("site"), pk=pk
    )
    if not can_teach(request.user, quiz.site):
        raise PermissionDenied("Paper quizzes are for the course's teaching staff.")
    return quiz


def _paper(request, pk: int) -> PaperQuiz:
    paper = get_object_or_404(
        PaperQuiz.objects.filter(quiz__site__in=visible_sites(request.user)).select_related("quiz__site"),
        pk=pk,
    )
    if not can_teach(request.user, paper.quiz.site):
        raise PermissionDenied("Paper quizzes are for the course's teaching staff.")
    return paper


def _refused(error: services.Refusal) -> Response:
    return Response({"code": error.code, "detail": error.detail}, status=error.status)


@extend_schema(
    methods=["GET"],
    responses={200: PaperSerializer(many=True), 403: ErrorSerializer, 404: ErrorSerializer},
    summary="The papers made from a quiz (teaching staff)",
)
@extend_schema(
    methods=["POST"],
    request=NewPaperSerializer,
    responses={201: PaperSerializer, 400: ErrorSerializer, 403: ErrorSerializer},
    summary="Make a paper from a quiz: its questions are drawn now, in version A and, shuffled, B",
    description="Refused with not_printable when a question cannot be answered on paper (cloze, file, image "
    "labelling): multiple choice, true or false, matching, ordering, short answer and numerical are keyed "
    "back as written; essays are keyed as the marks given.",
)
@api_view(["GET", "POST"])
@permission_classes([RolePermission])
def quiz_papers(request, pk: int):
    quiz = _quiz(request, pk)
    if request.method == "GET":
        return Response([_paper_data(p) for p in quiz.papers.prefetch_related("versions")])
    data = NewPaperSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    try:
        paper = services.make_paper(quiz, request=request, **data.validated_data)
    except services.Refusal as error:
        return _refused(error)
    return Response(_paper_data(paper), status=201)


@extend_schema(
    methods=["GET"],
    responses={200: OpenApiTypes.OBJECT, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="A paper's versions, each question as printed with how its answer is keyed and its key",
)
@extend_schema(
    methods=["DELETE"],
    responses={204: None, 403: ErrorSerializer, 409: ErrorSerializer},
    summary="Delete a paper that has no answer sheets keyed in",
)
@api_view(["GET", "DELETE"])
@permission_classes([RolePermission])
def paper_detail(request, pk: int):
    paper = _paper(request, pk)
    if request.method == "DELETE":
        if paper.scripts.exists():
            return _refused(services.Refusal("keyed", "Answer sheets have been keyed in; the paper stays."))
        with transaction.atomic():
            before = snapshot(paper)
            paper.delete()
            record(request, "delete", paper, before=before, entity_id=before["id"])
        return Response(status=204)
    return Response(
        {
            **_paper_data(paper),
            "detail": [{"label": v.label, "questions": services.printed(v)} for v in paper.versions.all()],
        }
    )


PARTS = {"questions": pdf.question_paper, "answer-sheet": pdf.answer_sheet, "key": pdf.marking_key}


@extend_schema(
    parameters=[
        OpenApiParameter("version", str, description="A or B", required=True),
        OpenApiParameter("part", str, enum=list(PARTS), description="questions, answer-sheet or key"),
    ],
    responses={(200, "application/pdf"): OpenApiTypes.BINARY, 400: ErrorSerializer, 404: ErrorSerializer},
    summary="Print a version: its question paper, answer sheet or marking key, as a PDF",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def paper_pdf(request, pk: int):
    paper = _paper(request, pk)
    version = paper.versions.filter(label=(request.query_params.get("version") or "A").upper()).first()
    part = request.query_params.get("part") or "questions"
    if version is None or part not in PARTS:
        return Response(
            {"code": "bad_request", "detail": "Choose version A or B, and a part to print."}, status=400
        )
    content = pdf.render(PARTS[part](paper, version.label, services.printed(version)))
    record(request, "paper_printed", paper, after={"version": version.label, "part": part})
    response = HttpResponse(content, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="paper-{paper.id}-{version.label}-{part}.pdf"'
    return response


def _grid(paper: PaperQuiz) -> dict:
    scripts = {
        s.student_id: s for s in PaperScript.objects.filter(paper=paper).select_related("version", "attempt")
    }
    students = Membership.objects.filter(
        site=paper.quiz.site, role=Membership.SiteRole.STUDENT, is_active=True
    ).select_related("person")
    rows = []
    for membership in sorted(students, key=lambda m: m.person.external_id):
        person, script = membership.person, scripts.get(membership.person_id)
        attempt = script.attempt if script else None
        rows.append(
            {
                "student_no": person.external_id,
                "name": person.full_name,
                "version": script.version.label if script else "",
                "answers": script.cells if script else [],
                "attempt": attempt.id if attempt else None,
                "score": str(attempt.score) if attempt and attempt.score is not None else None,
                "max_score": str(attempt.max_score) if attempt else None,
                "needs_marking": bool(attempt and attempt.needs_grading),
            }
        )
    return {
        **_paper_data(paper),
        "columns": {
            v.label: [
                {"number": q["number"], "qtype": q["qtype"], "hint": q["hint"]} for q in services.printed(v)
            ]
            for v in paper.versions.all()
        },
        "rows": rows,
    }


@extend_schema(
    methods=["GET"],
    responses={200: OpenApiTypes.OBJECT, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="The keying grid: every student of the course, what was keyed and the score",
)
@extend_schema(
    methods=["POST"],
    request=GridInSerializer,
    responses={200: KeyedResultSerializer, 400: ErrorSerializer, 403: ErrorSerializer},
    summary="Key answer sheets in: each row becomes, or replaces, the student's attempt for this paper",
    description="Rows are saved one by one; a row with a mistake comes back in errors, the rest are saved. "
    "Blank rows are skipped. Letters for options (A, B ...), T or F, the words or number written, and for an "
    "essay the marks given or ? to mark it later.",
)
@api_view(["GET", "POST"])
@permission_classes([RolePermission])
def paper_grid(request, pk: int):
    paper = _paper(request, pk)
    if request.method == "POST":
        data = GridInSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(services.key_rows(paper, data.validated_data["rows"], request=request))
    return Response(_grid(paper))


@extend_schema(
    request={"multipart/form-data": CsvSerializer},
    responses={200: KeyedResultSerializer, 400: ErrorSerializer, 403: ErrorSerializer},
    summary="Key answer sheets in from a CSV file: student_no, version, then one column for each question",
)
@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@permission_classes([RolePermission])
def paper_upload(request, pk: int):
    paper = _paper(request, pk)
    data = CsvSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    try:
        rows = services.rows_from_csv(data.validated_data["file"].read(services.MAX_CSV_BYTES + 1))
    except services.Refusal as error:
        return _refused(error)
    return Response(services.key_rows(paper, rows, request=request))


urlpatterns = [
    path("quizzes/<int:pk>/papers/", quiz_papers, name="quiz-papers"),
    path("quiz-papers/<int:pk>/", paper_detail, name="quiz-paper"),
    path("quiz-papers/<int:pk>/pdf/", paper_pdf, name="quiz-paper-pdf"),
    path("quiz-papers/<int:pk>/grid/", paper_grid, name="quiz-paper-grid"),
    path("quiz-papers/<int:pk>/upload/", paper_upload, name="quiz-paper-upload"),
]
