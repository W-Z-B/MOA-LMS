"""Quizzes and question banks API (feature 10; items 3.01 to 3.08, parts of 3.21 and 3.23).

Teaching staff of a site manage its banks and quizzes and see every attempt. Students see published quizzes
on the sites they belong to and only their own attempts; right answers, marks and feedback reach them only
when the quiz's review options and the lecturer's release allow. Refusals use the {code, detail} shape.
"""

import re
from decimal import Decimal

from django.db import transaction
from django.db.models import ProtectedError
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from audit.services import record, snapshot
from core import uploads
from courses import richtext
from courses.access import TaughtRecord, can_teach, person_of, site_role, visible_sites
from courses.api import TeachingViewSet
from courses.models import CourseSite, Membership
from iam.permissions import RolePermission
from quizzes import formats, marking, schemas, services
from quizzes.models import (
    Attempt,
    AttemptAnswer,
    Question,
    QuestionBank,
    QuestionCategory,
    QuestionVersion,
    Quiz,
    QuizOverride,
    QuizSlot,
)
from quizzes.services import Refusal

Problem = inline_serializer(
    "QuizProblem", {"code": serializers.CharField(), "detail": serializers.CharField()}
)


def refusal(error: Refusal) -> Response:
    return Response({"code": error.code, "detail": error.detail}, status=error.status)


def _filename(field) -> str | None:
    return field.name.rsplit("/", 1)[-1] if field else None


# ---------------------------------------------------------------------------------------------------------
# Banks and categories


class QuestionBankSerializer(serializers.ModelSerializer):
    owner_label = serializers.CharField(read_only=True)
    can_manage = serializers.SerializerMethodField()

    class Meta:
        model = QuestionBank
        fields = ("id", "name", "site", "department_code", "description", "owner_label", "can_manage")

    def get_can_manage(self, obj) -> bool:
        return services.can_manage_bank(self.context["request"].user, obj)

    def validate(self, attrs):
        site = attrs.get("site", getattr(self.instance, "site", None))
        department = attrs.get("department_code", getattr(self.instance, "department_code", ""))
        if bool(site) == bool(department):
            raise serializers.ValidationError("A bank belongs to a course site or to a department, not both.")
        if self.instance is not None and (
            site != self.instance.site or department != self.instance.department_code
        ):
            raise serializers.ValidationError("A bank's owner cannot change.")
        return attrs


class BankGuardMixin:
    """Create, change and delete only where the user may manage the bank. Every change is audited."""

    permission_classes = [RolePermission]

    def bank_of(self, instance) -> QuestionBank:
        raise NotImplementedError

    def _require_manage(self, bank):
        if not services.can_manage_bank(self.request.user, bank):
            raise PermissionDenied("Only the bank's owners can change it.")

    def perform_create(self, serializer):
        self._require_manage(self.bank_of(serializer.validated_data))
        with transaction.atomic():
            instance = serializer.save(created_by=self.request.user, updated_by=self.request.user)
            record(self.request, "create", instance, after=snapshot(instance))

    def perform_update(self, serializer):
        self._require_manage(self.bank_of(serializer.instance))
        with transaction.atomic():
            before = snapshot(serializer.instance)
            instance = serializer.save(updated_by=self.request.user)
            record(self.request, "update", instance, before=before, after=snapshot(instance))

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self._require_manage(self.bank_of(instance))
        try:
            with transaction.atomic():
                before, entity_id = snapshot(instance), instance.pk
                instance.delete()
                record(request, "delete", instance, before=before, entity_id=entity_id)
        except ProtectedError:
            return Response(
                {
                    "code": "in_use",
                    "detail": "Quizzes or attempts still use these questions. Archive them instead.",
                },
                status=409,
            )
        return Response(status=204)


class QuestionBankViewSet(BankGuardMixin, viewsets.ModelViewSet):
    """Question banks the user can use: their sites' banks and the department banks shared with staff."""

    serializer_class = QuestionBankSerializer
    queryset = QuestionBank.objects.none()  # for the schema; get_queryset scopes every request
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = services.usable_banks(self.request.user)
        site = self.request.query_params.get("site")
        return qs.filter(site_id=site) if site else qs

    def bank_of(self, instance):
        return instance if isinstance(instance, QuestionBank) else QuestionBank(**instance)


class QuestionCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionCategory
        fields = ("id", "bank", "parent", "name", "position")

    def validate(self, attrs):
        bank = attrs.get("bank", getattr(self.instance, "bank", None))
        parent = attrs.get("parent", getattr(self.instance, "parent", None))
        if self.instance is not None and "bank" in attrs and attrs["bank"] != self.instance.bank:
            raise serializers.ValidationError("A category cannot move to another bank.")
        if parent is not None:
            if parent.bank_id != bank.id:
                raise serializers.ValidationError({"parent": "The parent category is in another bank."})
            if self.instance is not None and parent.id in self.instance.descendant_ids():
                raise serializers.ValidationError({"parent": "A category cannot sit inside itself."})
        return attrs


class QuestionCategoryViewSet(BankGuardMixin, viewsets.ModelViewSet):
    serializer_class = QuestionCategorySerializer
    queryset = QuestionCategory.objects.none()  # for the schema; get_queryset scopes every request
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = QuestionCategory.objects.filter(bank__in=services.usable_banks(self.request.user))
        bank = self.request.query_params.get("bank")
        return qs.filter(bank_id=bank) if bank else qs

    def bank_of(self, instance):
        return instance["bank"] if isinstance(instance, dict) else instance.bank


# ---------------------------------------------------------------------------------------------------------
# Questions and versions


class QuestionVersionSerializer(serializers.ModelSerializer):
    in_use = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    text_html = serializers.SerializerMethodField()

    class Meta:
        model = QuestionVersion
        fields = (
            "id",
            "number",
            "text",
            "text_html",
            "data",
            "default_mark",
            "general_feedback",
            "image_url",
            "created_at",
            "in_use",
        )

    def get_in_use(self, obj) -> bool:
        return services.version_in_use(obj)

    def get_image_url(self, obj) -> str | None:
        return f"/api/v1/question-versions/{obj.id}/image/" if obj.image else None

    def get_text_html(self, obj) -> str:
        """The text as cleaned HTML, for showing; "text" is the text as written, for editing."""
        return rich(obj.text)


class QuestionSerializer(serializers.ModelSerializer):
    """A question with its latest version flattened in. Changing the wording or settings of a version that
    an attempt has used makes a new version."""

    text = serializers.CharField(write_only=True, required=False)
    data = serializers.JSONField(write_only=True, required=False)
    default_mark = serializers.DecimalField(
        max_digits=6, decimal_places=2, min_value=Decimal("0.01"), write_only=True, required=False
    )
    general_feedback = serializers.CharField(write_only=True, required=False, allow_blank=True)
    latest = QuestionVersionSerializer(read_only=True)
    versions_count = serializers.SerializerMethodField()
    new_version = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = (
            "id",
            "bank",
            "category",
            "qtype",
            "name",
            "tags",
            "is_archived",
            "text",
            "data",
            "default_mark",
            "general_feedback",
            "latest",
            "versions_count",
            "new_version",
        )

    def get_versions_count(self, obj) -> int:
        return obj.versions.count()

    def get_new_version(self, obj) -> bool:
        return bool(getattr(obj, "_new_version", False))

    def validate(self, attrs):
        instance = self.instance
        if instance is not None:
            if "qtype" in attrs and attrs["qtype"] != instance.qtype:
                raise serializers.ValidationError(
                    {"qtype": "A question's type cannot change; make a new question."}
                )
            if "bank" in attrs and attrs["bank"] != instance.bank:
                raise serializers.ValidationError({"bank": "A question cannot move to another bank."})
        bank = attrs.get("bank", getattr(instance, "bank", None))
        category = attrs.get("category", getattr(instance, "category", None))
        if category is not None and category.bank_id != bank.id:
            raise serializers.ValidationError({"category": "The category is in another bank."})
        qtype = attrs.get("qtype", getattr(instance, "qtype", None))
        current = instance.latest if instance is not None else None
        if instance is None and not attrs.get("text"):
            raise serializers.ValidationError({"text": "Write the question."})
        if instance is None or "text" in attrs or "data" in attrs:
            text = attrs.get("text", current.text if current else "")
            data = attrs.get("data", current.data if current else {})
            try:
                attrs["data"] = schemas.validate_question(qtype, text, data)
            except schemas.QuestionDataError as error:
                raise serializers.ValidationError({"data": error.messages}) from error
        tags = attrs.get("tags")
        if tags is not None:
            attrs["tags"] = sorted({t.strip().lower() for t in tags if t.strip()})[:20]
        return attrs

    _CONTENT = ("text", "data", "default_mark", "general_feedback")

    def create(self, validated):
        content = {k: validated.pop(k) for k in self._CONTENT if k in validated}
        user = self.context["request"].user
        question = Question.objects.create(**validated)
        services.save_question_version(question, user, **content)
        return question

    def update(self, instance, validated):
        content = {k: validated.pop(k) for k in self._CONTENT if k in validated}
        for key, value in validated.items():
            setattr(instance, key, value)
        instance.save()
        if content:
            _, instance._new_version = services.save_question_version(
                instance, self.context["request"].user, **content
            )
        return instance


class ImportSerializer(serializers.Serializer):
    bank = serializers.PrimaryKeyRelatedField(queryset=QuestionBank.objects.all())
    category = serializers.PrimaryKeyRelatedField(queryset=QuestionCategory.objects.all(), required=False)
    format = serializers.ChoiceField(choices=formats.FORMATS)
    file = serializers.FileField(required=False)
    content = serializers.CharField(required=False, trim_whitespace=False)

    def validate(self, attrs):
        if bool(attrs.get("file")) == bool(attrs.get("content")):
            raise serializers.ValidationError("Send either a file or the text content.")
        if attrs.get("category") and attrs["category"].bank_id != attrs["bank"].id:
            raise serializers.ValidationError({"category": "The category is in another bank."})
        return attrs


ImportReport = inline_serializer(
    "QuestionImportReport",
    {
        "imported": serializers.ListField(child=serializers.DictField()),
        "skipped": serializers.ListField(child=serializers.DictField()),
        "warnings": serializers.ListField(child=serializers.CharField()),
    },
)
ExportResult = inline_serializer(
    "QuestionExport",
    {
        "format": serializers.CharField(),
        "filename": serializers.CharField(),
        "content": serializers.CharField(),
        "exported": serializers.IntegerField(),
        "skipped": serializers.ListField(child=serializers.DictField()),
    },
)


class QuestionViewSet(BankGuardMixin, viewsets.ModelViewSet):
    serializer_class = QuestionSerializer
    queryset = Question.objects.none()  # for the schema; get_queryset scopes every request
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def get_queryset(self):
        qs = Question.objects.filter(bank__in=services.usable_banks(self.request.user)).prefetch_related(
            "versions"
        )
        params = self.request.query_params
        for name, lookup in (("bank", "bank_id"), ("category", "category_id"), ("qtype", "qtype")):
            if params.get(name):
                qs = qs.filter(**{lookup: params[name]})
        if params.get("tag"):
            qs = qs.filter(tags__contains=[params["tag"].lower()])
        if params.get("archived") not in ("1", "true"):
            qs = qs.filter(is_archived=False)
        return qs

    def bank_of(self, instance):
        return instance["bank"] if isinstance(instance, dict) else instance.bank

    def perform_update(self, serializer):
        self._require_manage(serializer.instance.bank)
        with transaction.atomic():
            before = {**snapshot(serializer.instance), "version": serializer.instance.latest.number}
            question = serializer.save(updated_by=self.request.user)
            question._latest = None
            record(
                self.request,
                "update",
                question,
                before=before,
                after={**snapshot(question), "version": question.latest.number},
            )

    def destroy(self, request, *args, **kwargs):
        question = self.get_object()
        self._require_manage(question.bank)
        if question.slots.exists() or AttemptAnswer.objects.filter(version__question=question).exists():
            return Response(
                {"code": "in_use", "detail": "A quiz or an attempt uses this question. Archive it instead."},
                status=409,
            )
        return super().destroy(request, *args, **kwargs)

    @extend_schema(responses=QuestionVersionSerializer(many=True))
    @action(detail=True, methods=["get"])
    def versions(self, request, pk=None):
        """Every version of the question, oldest first."""
        question = self.get_object()
        return Response(QuestionVersionSerializer(question.versions.all(), many=True).data)

    @extend_schema(
        request=inline_serializer("QuestionImageUpload", {"image": serializers.ImageField()}),
        responses={200: QuestionSerializer, 400: Problem},
    )
    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def image(self, request, pk=None):
        """Attach the image for a diagram question (PNG, JPG or WEBP; at most 5 MB). The file's contents
        must match its name (core.uploads)."""
        question = self.get_object()
        self._require_manage(question.bank)
        upload = request.FILES.get("image")
        if upload is None:
            return Response({"code": "no_file", "detail": "Choose an image to upload."}, status=400)
        try:
            uploads.validate_upload(upload, services.IMAGE_POLICY)
        except serializers.ValidationError as error:
            return Response({"code": "file_rejected", "detail": " ".join(map(str, error.detail))}, status=400)
        with transaction.atomic():
            version, new = services.save_question_version(question, request.user, image=upload)
            question._new_version = new
            record(
                request, "update", question, after={"image": version.image.name, "version": version.number}
            )
        return Response(QuestionSerializer(question, context={"request": request}).data)

    @extend_schema(request=ImportSerializer, responses={200: ImportReport, 400: Problem})
    @action(detail=False, methods=["post"], url_path="import", parser_classes=[JSONParser, MultiPartParser])
    def import_questions(self, request):
        """Import questions from Moodle XML, GIFT or QTI 2.1 (an item file or a content package zip).

        The report lists what was imported and what was skipped, with the reason. XML with a document type
        or entity declaration is refused for safety."""
        data = ImportSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        bank = data.validated_data["bank"]
        self._require_manage(bank)
        upload = data.validated_data.get("file")
        if upload is not None and upload.size > formats.MAX_IMPORT_BYTES:
            return Response({"code": "too_large", "detail": "The file is larger than 5 MB."}, status=400)
        content = upload.read() if upload is not None else data.validated_data["content"]
        try:
            parsed = formats.parse(data.validated_data["format"], content, getattr(upload, "name", ""))
        except formats.FormatError as error:
            return Response({"code": "unreadable", "detail": str(error)}, status=400)
        report = services.import_questions(
            bank, parsed, category=data.validated_data.get("category"), request=request
        )
        return Response(report)

    @extend_schema(
        parameters=[
            OpenApiParameter("bank", int, required=True),
            OpenApiParameter("category", int, required=False),
            OpenApiParameter("file_format", str, enum=list(formats.EXPORT_FORMATS), required=False),
        ],
        responses={200: ExportResult},
    )
    @action(detail=False, methods=["get"])
    def export(self, request):
        """Export a bank (or one category and those below it) as Moodle XML or GIFT text."""
        bank = get_object_or_404(
            services.usable_banks(request.user), pk=request.query_params.get("bank") or 0
        )
        category = None
        if request.query_params.get("category"):
            category = get_object_or_404(QuestionCategory, pk=request.query_params["category"], bank=bank)
        fmt = request.query_params.get("file_format", "moodle_xml")
        if fmt not in formats.EXPORT_FORMATS:
            return Response({"code": "format", "detail": "Export as moodle_xml or gift."}, status=400)
        items = services.export_items(bank, category)
        builder = formats.export_moodle_xml if fmt == "moodle_xml" else formats.export_gift
        content, skipped = builder(items)
        record(request, "export", bank, after={"format": fmt, "questions": len(items) - len(skipped)})
        return Response(
            {
                "format": fmt,
                "filename": f"questions-{bank.id}.{'xml' if fmt == 'moodle_xml' else 'gift.txt'}",
                "content": content,
                "exported": len(items) - len(skipped),
                "skipped": skipped,
            }
        )


class QuestionVersionViewSet(viewsets.GenericViewSet):
    permission_classes = [RolePermission]
    queryset = QuestionVersion.objects.select_related("question__bank__site")

    @extend_schema(responses={(200, "application/octet-stream"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def image(self, request, pk=None):
        """The image of a diagram question: for those who can use its bank, and for students whose
        attempt contains this version."""
        version = get_object_or_404(self.get_queryset(), pk=pk)
        person = person_of(request.user)
        allowed = services.can_use_bank(request.user, version.question.bank) or (
            person is not None
            and AttemptAnswer.objects.filter(version=version, attempt__student=person).exists()
        )
        if not allowed:
            raise PermissionDenied("You cannot open this image.")
        if not version.image:
            return Response({"code": "no_file", "detail": "This question has no image."}, status=404)
        return FileResponse(version.image.open("rb"), filename=_filename(version.image))


class AttemptSummarySerializer(serializers.ModelSerializer):
    student_no = serializers.CharField(source="student.external_id", read_only=True)
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    score = serializers.SerializerMethodField()
    percent = serializers.SerializerMethodField()

    class Meta:
        model = Attempt
        fields = (
            "id",
            "quiz",
            "student_no",
            "student_name",
            "number",
            "state",
            "started_at",
            "deadline",
            "submitted_at",
            "auto_submitted",
            "score",
            "max_score",
            "percent",
            "needs_grading",
            "is_released",
        )

    def _visible(self, obj) -> bool:
        request = self.context.get("request")
        return bool(request and can_teach(request.user, obj.quiz.site)) or services.student_sees_marks(obj)

    def get_score(self, obj) -> str | None:
        return (
            None
            if obj.score is None or not self._visible(obj)
            else str(obj.score.quantize(services.TWO_PLACES))
        )

    def get_percent(self, obj) -> str | None:
        percent = obj.percent
        return (
            None if percent is None or not self._visible(obj) else str(percent.quantize(services.TWO_PLACES))
        )


# ---------------------------------------------------------------------------------------------------------
# Quizzes, slots and overrides


class QuizSerializer(serializers.ModelSerializer):
    # The site is settled first: unknown when the caller cannot open it, refused when they do not teach on it
    # (courses.access.TaughtRecord, item 1.15), before any other field is looked at.
    site = TaughtRecord(CourseSite)
    max_mark = serializers.SerializerMethodField()
    my_status = serializers.SerializerMethodField()

    class Meta:
        model = Quiz
        fields = (
            "id",
            "site",
            "title",
            "description",
            "opens_at",
            "closes_at",
            "time_limit_minutes",
            "attempts_allowed",
            "grading_method",
            "pass_mark",
            "weight",
            "is_practice",
            "is_published",
            "shuffle_questions",
            "shuffle_answers",
            "questions_per_page",
            "navigation",
            "review_marks",
            "review_correct",
            "review_feedback",
            "auto_release",
            "feedback_bands",
            "max_mark",
            "my_status",
        )

    def get_max_mark(self, obj) -> str:
        return str(services.quiz_max_mark(obj))

    def get_my_status(self, obj) -> dict | None:
        """For a student: attempts used and allowed, the attempt in progress, and the grade once visible."""
        request = self.context.get("request")
        person = person_of(request.user) if request else None
        if person is None or site_role(request.user, obj.site) != Membership.SiteRole.STUDENT:
            return None
        settings_for = services.effective(obj, person)
        attempts = list(obj.attempts.filter(student=person).order_by("number"))
        current = next((a.id for a in attempts if a.state == Attempt.State.IN_PROGRESS), None)
        grade = services.quiz_grade(obj, person, released_only=True)
        return {
            "attempts_used": len(attempts),
            "attempts_allowed": settings_for.attempts_allowed,
            "closes_at": settings_for.closes_at,
            "time_limit_minutes": settings_for.time_limit_minutes,
            "in_progress_attempt": current,
            "grade_state": grade.state,
            "grade_percent": str((grade.fraction * 100).quantize(services.TWO_PLACES))
            if grade.fraction is not None
            else None,
        }

    def validate_feedback_bands(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Give a list of bands.")
        cleaned = []
        for band in value:
            try:
                low = float(band["min_percent"])
                text = str(band["feedback"])
            except (KeyError, TypeError, ValueError) as error:
                raise serializers.ValidationError("Each band needs min_percent and feedback.") from error
            if not 0 <= low <= 100:
                raise serializers.ValidationError("min_percent must be from 0 to 100.")
            cleaned.append({"min_percent": low, "feedback": text[:2000]})
        return sorted(cleaned, key=lambda b: -b["min_percent"])

    def validate(self, attrs):
        if attrs.get("is_practice", getattr(self.instance, "is_practice", False)):
            attrs["weight"], attrs["attempts_allowed"] = 0, 0  # practice never counts and is unlimited
        opens = attrs.get("opens_at", getattr(self.instance, "opens_at", None))
        closes = attrs.get("closes_at", getattr(self.instance, "closes_at", None))
        if opens and closes and closes <= opens:
            raise serializers.ValidationError({"closes_at": "The quiz must close after it opens."})
        if self.instance is not None and "site" in attrs and attrs["site"] != self.instance.site:
            raise serializers.ValidationError({"site": "A quiz cannot move to another site."})
        return attrs


class QuizViewSet(TeachingViewSet):
    serializer_class = QuizSerializer
    queryset = Quiz.objects.none()  # for the schema; get_queryset scopes every request

    def get_queryset(self):
        user = self.request.user
        qs = Quiz.objects.filter(site__in=visible_sites(user)).select_related("site")
        site = self.request.query_params.get("site")
        if site:
            qs = qs.filter(site_id=site)
        teaching_sites = [s.id for s in visible_sites(user) if can_teach(user, s)]
        return qs.filter(is_published=True) | qs.filter(site_id__in=teaching_sites)

    def site_of(self, instance):
        return instance.site

    def site_from_data(self, data):
        return data["site"]

    def perform_create(self, serializer):
        self._require_teaching(serializer.validated_data["site"])
        if serializer.validated_data.get("is_published"):
            raise serializers.ValidationError({"is_published": ["Add questions before publishing the quiz."]})
        super().perform_create(serializer)

    def perform_update(self, serializer):
        quiz = serializer.instance
        self._require_teaching(quiz.site)
        if serializer.validated_data.get("is_published") and not quiz.is_published:
            problems = services.quiz_problems(quiz)
            if problems:
                raise serializers.ValidationError({"is_published": problems})
        super().perform_update(serializer)

    def _student(self, quiz):
        person = person_of(self.request.user)
        if person is None or site_role(self.request.user, quiz.site) != Membership.SiteRole.STUDENT:
            raise PermissionDenied("Only students of this course can attempt the quiz.")
        return person

    @extend_schema(request=None, responses={200: OpenApiTypes.OBJECT, 201: OpenApiTypes.OBJECT, 409: Problem})
    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        """Start an attempt, or resume the one in progress (201 when new, 200 when resumed)."""
        quiz = self.get_object()
        person = self._student(quiz)
        try:
            attempt, resumed = services.start_attempt(quiz, person, request.user)
        except Refusal as error:
            return refusal(error)
        return Response(attempt_payload(attempt, request), status=200 if resumed else 201)

    @extend_schema(responses=AttemptSummarySerializer(many=True))
    @action(detail=True, methods=["get"])
    def attempts(self, request, pk=None):
        """Teaching staff: every attempt. Students: their own."""
        quiz = self.get_object()
        services.finish_expired_attempts([quiz])
        rows = quiz.attempts.select_related("student", "quiz")
        if not can_teach(request.user, quiz.site):
            person = person_of(request.user)
            rows = rows.filter(student=person) if person else rows.none()
        return Response(AttemptSummarySerializer(rows, many=True, context={"request": request}).data)

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    @action(detail=True, methods=["get"])
    def statistics(self, request, pk=None):
        """Facility and discrimination index per question, and how often each answer was chosen."""
        quiz = self.get_object()
        self._require_teaching(quiz.site)
        return Response(services.quiz_statistics(quiz))

    @extend_schema(
        request=None,
        responses=inline_serializer(
            "QuizReleaseResult",
            {"released": serializers.IntegerField(), "awaiting_marking": serializers.IntegerField()},
        ),
    )
    @action(detail=True, methods=["post"])
    def release(self, request, pk=None):
        """Release the results of every submitted attempt that is fully marked. Students are notified."""
        quiz = self.get_object()
        self._require_teaching(quiz.site)
        released = waiting = 0
        with transaction.atomic():
            for attempt in quiz.attempts.filter(state=Attempt.State.FINISHED, is_released=False):
                if services.release_attempt(attempt, request=request):
                    released += 1
                else:
                    waiting += 1
        return Response({"released": released, "awaiting_marking": waiting})

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"], url_path="marking-queue")
    def marking_queue(self, request, pk=None):
        """Answers waiting for a person to mark them (essays and file responses), oldest first."""
        quiz = self.get_object()
        self._require_teaching(quiz.site)
        services.finish_expired_attempts([quiz])
        answers = (
            AttemptAnswer.objects.filter(
                attempt__quiz=quiz,
                attempt__state=Attempt.State.FINISHED,
                needs_manual=True,
                awarded__isnull=True,
            )
            .select_related("attempt__student", "version__question")
            .order_by("attempt__submitted_at", "position")
        )
        return Response(
            [
                {
                    "attempt": a.attempt_id,
                    "position": a.position,
                    "student_no": a.attempt.student.external_id,
                    "student_name": a.attempt.student.full_name,
                    "question": a.version.question.name,
                    "qtype": a.version.question.qtype,
                    "max_mark": str(a.max_mark),
                    "submitted_at": a.attempt.submitted_at,
                }
                for a in answers
            ]
        )


class QuizSlotSerializer(serializers.ModelSerializer):
    # The quiz is settled first, as for the quiz itself (courses.access.TaughtRecord, item 1.15).
    quiz = TaughtRecord(Quiz, "site")

    class Meta:
        model = QuizSlot
        fields = (
            "id",
            "quiz",
            "position",
            "question",
            "category",
            "random_count",
            "include_subcategories",
            "tag",
            "mark",
        )

    def validate(self, attrs):
        quiz = attrs.get("quiz", getattr(self.instance, "quiz", None))
        question = attrs.get("question", getattr(self.instance, "question", None))
        category = attrs.get("category", getattr(self.instance, "category", None))
        if bool(question) == bool(category):
            raise serializers.ValidationError(
                "Choose a question, or a category to draw random questions from."
            )
        bank = question.bank if question else category.bank
        user = self.context["request"].user
        if bank.site_id not in (None, quiz.site_id) or not services.can_use_bank(user, bank):
            raise serializers.ValidationError(
                "Use questions from this site's banks or a shared department bank."
            )
        if question is not None and question.is_archived:
            raise serializers.ValidationError({"question": "This question is archived."})
        if question is not None and attrs.get("random_count", 1) != 1:
            attrs["random_count"] = 1
        if self.instance is not None and attrs.get("quiz", quiz) != self.instance.quiz:
            raise serializers.ValidationError({"quiz": "A slot cannot move to another quiz."})
        return attrs


class QuizSlotViewSet(TeachingViewSet):
    """The questions of a quiz. Fixed once anyone has attempted the quiz, so attempts stay comparable."""

    serializer_class = QuizSlotSerializer
    queryset = QuizSlot.objects.none()  # for the schema; get_queryset scopes every request

    def get_queryset(self):
        user = self.request.user
        teaching = [s.id for s in visible_sites(user) if can_teach(user, s)]
        qs = QuizSlot.objects.filter(quiz__site_id__in=teaching).select_related(
            "quiz", "question", "category"
        )
        quiz = self.request.query_params.get("quiz")
        return qs.filter(quiz_id=quiz) if quiz else qs

    def site_of(self, instance):
        return instance.quiz.site

    def site_from_data(self, data):
        return data["quiz"].site

    def _unlocked(self, quiz):
        if quiz.attempts.exists():
            raise _Locked()

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except _Locked:
            return _locked_response()

    def perform_create(self, serializer):
        self._unlocked(serializer.validated_data["quiz"])
        super().perform_create(serializer)

    def update(self, request, *args, **kwargs):
        try:
            return super().update(request, *args, **kwargs)
        except _Locked:
            return _locked_response()

    def perform_update(self, serializer):
        self._unlocked(serializer.instance.quiz)
        super().perform_update(serializer)

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except _Locked:
            return _locked_response()

    def perform_destroy(self, instance):
        self._unlocked(instance.quiz)
        super().perform_destroy(instance)


class _Locked(Exception):
    pass


def _locked_response():
    return Response(
        {
            "code": "has_attempts",
            "detail": "Students have attempted this quiz; its questions can no longer change.",
        },
        status=409,
    )


class QuizOverrideSerializer(serializers.ModelSerializer):
    # Named by id: a quiz on a site the caller cannot open reads as unknown, one they do not teach is refused,
    # before any other field is looked at (courses.access.TaughtRecord, item 1.15).
    quiz = TaughtRecord(Quiz, "site")
    student_no = serializers.CharField(source="student.external_id", read_only=True)
    student_name = serializers.CharField(source="student.full_name", read_only=True)

    class Meta:
        model = QuizOverride
        fields = (
            "id",
            "quiz",
            "student",
            "student_no",
            "student_name",
            "extra_minutes",
            "extra_attempts",
            "closes_at",
            "reason",
        )

    def validate(self, attrs):
        quiz = attrs.get("quiz", getattr(self.instance, "quiz", None))
        student = attrs.get("student", getattr(self.instance, "student", None))
        if self.instance is not None and (quiz != self.instance.quiz or student != self.instance.student):
            raise serializers.ValidationError("An override cannot move to another quiz or student.")
        if not Membership.objects.filter(
            site=quiz.site, person=student, is_active=True, role=Membership.SiteRole.STUDENT
        ).exists():
            raise serializers.ValidationError({"student": "This person is not a student of the course."})
        return attrs


class QuizOverrideViewSet(TeachingViewSet):
    """Per-student extra time, extra attempts or a later close date. Teaching staff only; audited."""

    serializer_class = QuizOverrideSerializer
    queryset = QuizOverride.objects.none()  # for the schema; get_queryset scopes every request

    def get_queryset(self):
        user = self.request.user
        teaching = [s.id for s in visible_sites(user) if can_teach(user, s)]
        qs = QuizOverride.objects.filter(quiz__site_id__in=teaching).select_related("quiz__site", "student")
        quiz = self.request.query_params.get("quiz")
        return qs.filter(quiz_id=quiz) if quiz else qs

    def site_of(self, instance):
        return instance.quiz.site

    def site_from_data(self, data):
        return data["quiz"].site


# ---------------------------------------------------------------------------------------------------------
# Attempts


def _q(value):
    return None if value is None else str(value.quantize(services.TWO_PLACES))


def rich(text: str) -> str:
    """Question text as safe HTML for the page. Moodle and QTI imports bring HTML: it is cleaned against the
    same allow-list as course pages (courses.richtext). Text typed without tags becomes paragraphs."""
    return clean(text) if HTML_TAG.search(text or "") else richtext.text_to_html(text)


def clean(html: str) -> str:
    """courses.richtext.clean, then the images: one whose address was not kept (an imported file that is not
    on the LMS) shows nothing and is dropped; one without alternative text is marked as decoration."""

    def image(match):
        attributes = match.group(1)
        if " src=" not in f" {attributes}":
            return ""
        return match.group(0) if " alt=" in f" {attributes}" else f'<img alt=""{attributes}>'

    return IMG_TAG.sub(image, richtext.clean(html))


HTML_TAG = re.compile(r"<[a-zA-Z/!]")
IMG_TAG = re.compile(r"<img((?:\s[^>]*?)?)\s*/?>")

# The parts of a question's settings that are shown to people as text: cleaned like the question itself.
_SHOWN = {
    schemas.MULTICHOICE: [("choices", ("text", "feedback"))],
    schemas.ORDERING: [("items", ("text",))],
    # A student sees prompts; teaching staff see the pairs themselves.
    schemas.MATCHING: [("prompts", ("text",)), ("pairs", ("prompt",))],
}


def shown_data(qtype: str, data: dict) -> dict:
    """A copy of the settings sent for display, with every piece of imported HTML in it cleaned."""
    shown = dict(data)
    for key, fields in _SHOWN.get(qtype, []):
        if isinstance(shown.get(key), list):
            shown[key] = [
                {**row, **{f: clean(row[f]) for f in fields if isinstance(row.get(f), str)}}
                for row in shown[key]
            ]
    return shown


def attempt_payload(attempt: Attempt, request, now=None) -> dict:
    """An attempt as its viewer may see it. Students never get fractions, right answers, zone labels or
    feedback before the quiz's review options (and, for marks, the release) allow."""
    now = now or timezone.now()
    quiz = attempt.quiz
    teacher = can_teach(request.user, quiz.site)
    finished = attempt.state == Attempt.State.FINISHED
    show_marks = teacher or services.student_sees_marks(attempt, now)
    show_correct = teacher or (
        attempt.is_released and services.review_allows(quiz.review_correct, attempt, now)
    )
    show_feedback = teacher or (
        attempt.is_released and services.review_allows(quiz.review_feedback, attempt, now)
    )
    seconds_left = None
    if attempt.deadline and not finished:
        seconds_left = max(0, int((attempt.deadline - now).total_seconds()))
    answers = attempt.answers.select_related("version__question").order_by("position")
    if not teacher and not finished and quiz.navigation == Quiz.Navigation.SEQUENTIAL:
        answers = answers.filter(page=attempt.current_page)
    questions = []
    for answer in answers:
        version, qtype = answer.version, answer.version.question.qtype
        item = {
            "position": answer.position,
            "page": answer.page,
            "qtype": qtype,
            # Cleaned HTML, safe to place in the page as it is (rich() above).
            "text": rich(version.text),
            "image_url": f"/api/v1/question-versions/{version.id}/image/" if version.image else None,
            "data": shown_data(
                qtype, version.data if teacher else schemas.public_data(qtype, version.data, answer.layout)
            ),
            "max_mark": str(answer.max_mark),
            "response": answer.response,
            "file_url": f"/api/v1/quiz-attempts/{attempt.id}/answers/{answer.position}/file/"
            if answer.file
            else None,
            "saved_at": answer.saved_at,
        }
        if finished and show_marks:
            item["awarded"] = _q(answer.awarded)
            item["state"] = (
                "needs_marking"
                if answer.needs_manual and answer.awarded is None
                else "correct"
                if answer.fraction is not None and answer.fraction >= 1
                else "partial"
                if answer.fraction and answer.fraction > 0
                else "incorrect"
            )
        if finished and show_feedback:
            item["feedback"] = clean(answer.auto_feedback)
            item["general_feedback"] = clean(version.general_feedback)
            item["comment"] = answer.comment
        if finished and show_correct:
            item["right_answer"] = marking.correct_response(qtype, version.data)
        if teacher:
            item.update(
                {
                    "question_id": version.question_id,
                    "version": version.number,
                    "fraction": None if answer.fraction is None else str(answer.fraction),
                    "needs_manual": answer.needs_manual,
                    "comment": answer.comment,
                    "marked_at": answer.marked_at,
                    "client_saved_at": answer.client_saved_at,
                }
            )
        questions.append(item)
    percent = attempt.percent if finished and show_marks and not attempt.needs_grading else None
    return {
        "id": attempt.id,
        "quiz": quiz.id,
        "quiz_title": quiz.title,
        "student_no": attempt.student.external_id,
        "number": attempt.number,
        "state": attempt.state,
        "server_time": now,
        "started_at": attempt.started_at,
        "deadline": attempt.deadline,
        "seconds_left": seconds_left,
        "submitted_at": attempt.submitted_at,
        "auto_submitted": attempt.auto_submitted,
        "navigation": quiz.navigation,
        "current_page": attempt.current_page,
        "last_page": services.last_page(attempt),
        "is_released": attempt.is_released,
        "needs_grading": attempt.needs_grading if finished else None,
        "score": _q(attempt.score) if finished and show_marks else None,
        "max_score": str(attempt.max_score),
        "percent": _q(percent),
        "passed": None if percent is None or quiz.pass_mark is None else percent >= quiz.pass_mark,
        "overall_feedback": services.overall_feedback(quiz, percent) if show_feedback else "",
        "questions": questions,
    }


class AnswerSerializer(serializers.Serializer):
    response = serializers.JSONField(allow_null=True)
    client_saved_at = serializers.DateTimeField(required=False, allow_null=True)


class ManualMarkSerializer(serializers.Serializer):
    mark = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=0)
    comment = serializers.CharField(required=False, allow_blank=True, default="")


AnswerSaved = inline_serializer(
    "AnswerSaved",
    {
        "position": serializers.IntegerField(),
        "saved": serializers.BooleanField(),
        "stale": serializers.BooleanField(),
        "server_time": serializers.DateTimeField(),
        "seconds_left": serializers.IntegerField(allow_null=True),
    },
)


class AttemptViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """One attempt. Students act only on their own; teaching staff of the site see and mark all."""

    permission_classes = [RolePermission]
    serializer_class = AttemptSummarySerializer
    queryset = Attempt.objects.none()  # for the schema; get_queryset scopes every request
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def get_queryset(self):
        user = self.request.user
        teaching = [s.id for s in visible_sites(user) if can_teach(user, s)]
        person = person_of(user)
        mine = Attempt.objects.filter(student=person) if person else Attempt.objects.none()
        return (Attempt.objects.filter(quiz__site_id__in=teaching) | mine).select_related(
            "quiz__site", "student"
        )

    def _own(self, attempt):
        person = person_of(self.request.user)
        if person is None or attempt.student_id != person.id:
            raise PermissionDenied("Only the student who started this attempt can answer it.")

    def _teaching(self, attempt):
        if not can_teach(self.request.user, attempt.quiz.site):
            raise PermissionDenied("Only the site's teaching staff can do this.")

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def retrieve(self, request, *args, **kwargs):
        """The attempt with its questions. An attempt whose time has run out is submitted first."""
        attempt = self.get_object()
        if services.finish_if_expired(attempt, user=request.user):
            attempt.refresh_from_db()
        return Response(attempt_payload(attempt, request))

    @extend_schema(request=AnswerSerializer, responses={200: AnswerSaved, 400: Problem, 409: Problem})
    @action(detail=True, methods=["put"], url_path=r"answers/(?P<position>\d+)")
    def answer(self, request, pk=None, position=None):
        """Save one answer as it is given. Safe to repeat. Server time decides whether it is in time; the
        device's time is kept, and an answer older than the one already saved is ignored (stale)."""
        attempt = self.get_object()
        self._own(attempt)
        data = AnswerSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            outcome = services.save_answer(
                attempt,
                int(position),
                data.validated_data["response"],
                client_saved_at=data.validated_data.get("client_saved_at"),
                user=request.user,
            )
        except Refusal as error:
            return refusal(error)
        except schemas.QuestionDataError as error:
            return Response({"code": "invalid_answer", "detail": str(error)}, status=400)
        now = timezone.now()
        return Response(
            {
                "position": int(position),
                "saved": outcome["saved"],
                "stale": outcome["stale"],
                "server_time": now,
                "seconds_left": max(0, int((attempt.deadline - now).total_seconds()))
                if attempt.deadline
                else None,
            }
        )

    @extend_schema(
        methods=["POST"],
        request=inline_serializer("AnswerFileUpload", {"file": serializers.FileField()}),
        responses={200: AnswerSaved, 400: Problem, 409: Problem},
    )
    @extend_schema(methods=["GET"], responses={(200, "application/octet-stream"): OpenApiTypes.BINARY})
    @action(
        detail=True,
        methods=["get", "post"],
        url_path=r"answers/(?P<position>\d+)/file",
        parser_classes=[MultiPartParser, FormParser],
    )
    def file(self, request, pk=None, position=None):
        """Upload (student) or download (student or teaching staff) the file for a file-response question."""
        attempt = self.get_object()
        if request.method == "GET":
            answer = get_object_or_404(attempt.answers, position=position)
            if not answer.file:
                return Response({"code": "no_file", "detail": "No file has been uploaded."}, status=404)
            record(request, "download", answer)
            name = (answer.response or {}).get("filename") or _filename(answer.file)
            return FileResponse(answer.file.open("rb"), as_attachment=True, filename=name)
        self._own(attempt)
        upload = request.FILES.get("file")
        if upload is None:
            return Response({"code": "no_file", "detail": "Choose a file to upload."}, status=400)
        try:
            services.save_file_answer(attempt, int(position), upload, user=request.user)
        except Refusal as error:
            return refusal(error)
        return Response(
            {
                "position": int(position),
                "saved": True,
                "stale": False,
                "server_time": timezone.now(),
                "seconds_left": None,
            }
        )

    @extend_schema(request=None, responses={200: OpenApiTypes.OBJECT, 409: Problem})
    @action(detail=True, methods=["post"], url_path="next-page")
    def next_page(self, request, pk=None):
        """Move on to the next page. With sequential navigation there is no way back."""
        attempt = self.get_object()
        self._own(attempt)
        try:
            services.next_page(attempt, user=request.user)
        except Refusal as error:
            return refusal(error)
        return Response(attempt_payload(attempt, request))

    @extend_schema(request=None, responses={200: OpenApiTypes.OBJECT})
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        """Submit the attempt. Automatic marking happens now; essays and files go to the marking queue."""
        attempt = self.get_object()
        self._own(attempt)
        if attempt.state == Attempt.State.IN_PROGRESS:
            with transaction.atomic():
                attempt = services.submit_attempt(attempt, user=request.user)
                record(request, "submit", attempt, after={"quiz": attempt.quiz_id, "number": attempt.number})
        attempt.refresh_from_db()
        return Response(attempt_payload(attempt, request))

    @extend_schema(
        request=ManualMarkSerializer, responses={200: OpenApiTypes.OBJECT, 400: Problem, 409: Problem}
    )
    @action(detail=True, methods=["post"], url_path=r"answers/(?P<position>\d+)/mark")
    def mark(self, request, pk=None, position=None):
        """Mark an essay or file response, or override any answer's mark. Audited."""
        attempt = self.get_object()
        self._teaching(attempt)
        answer = get_object_or_404(attempt.answers.select_related("attempt__quiz__site"), position=position)
        data = ManualMarkSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            services.manual_mark(
                answer, data.validated_data["mark"], data.validated_data["comment"], request=request
            )
        except Refusal as error:
            return refusal(error)
        attempt.refresh_from_db()
        return Response(attempt_payload(attempt, request))

    @extend_schema(request=None, responses={200: OpenApiTypes.OBJECT, 409: Problem})
    @action(detail=True, methods=["post"])
    def release(self, request, pk=None):
        """Release this attempt's result to the student, who is notified."""
        attempt = self.get_object()
        self._teaching(attempt)
        with transaction.atomic():
            if not services.release_attempt(attempt, request=request):
                return Response(
                    {"code": "not_marked", "detail": "The attempt is not submitted or not fully marked yet."},
                    status=409,
                )
        attempt.refresh_from_db()
        return Response(attempt_payload(attempt, request))

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def events(self, request, pk=None):
        """The attempt's event log: started, resumed, answers saved or refused, pages, submission, marking."""
        attempt = self.get_object()
        self._teaching(attempt)
        return Response([{"kind": e.kind, "at": e.at, "detail": e.detail} for e in attempt.events.all()])


router = DefaultRouter()
router.register("question-banks", QuestionBankViewSet, basename="question-bank")
router.register("question-categories", QuestionCategoryViewSet, basename="question-category")
router.register("questions", QuestionViewSet, basename="question")
router.register("question-versions", QuestionVersionViewSet, basename="question-version")
router.register("quizzes", QuizViewSet, basename="quiz")
router.register("quiz-slots", QuizSlotViewSet, basename="quiz-slot")
router.register("quiz-overrides", QuizOverrideViewSet, basename="quiz-override")
router.register("quiz-attempts", AttemptViewSet, basename="quiz-attempt")
urlpatterns = router.urls
