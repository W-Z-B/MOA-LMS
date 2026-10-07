"""AI assistance within decision D5 (items 6.11, 6.12), under /api/v1/. Off unless GSA switches it on.

Every draft is shown to the lecturer only; nothing is saved until the lecturer saves it through the usual
screens, and that save is then marked in the audit log as AI-drafted ("ai_draft_saved"). The study helper
keeps neither questions nor answers.
"""

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.urls import path
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from assist import services
from assist.models import Exchange, SiteSwitch
from assist.providers import enabled
from audit.services import record, snapshot
from core.serializers import ErrorSerializer
from courses.access import can_teach, visible_sites
from courses.models import ContentItem
from iam.permissions import RolePermission


class AiThrottle(UserRateThrottle):
    """The model is slow and shared: at most 30 requests a minute from one person."""

    scope = "ai"
    rate = "30/minute"


def _refused(refusal: services.Refusal) -> Response:
    return Response({"code": refusal.code, "detail": refusal.detail}, status=refusal.status)


def _site(request, pk: int):
    return get_object_or_404(visible_sites(request.user), pk=pk)


def _teaching_site(request, pk: int):
    site = _site(request, pk)
    if not can_teach(request.user, site):
        raise PermissionDenied("Only the site's teaching staff can do this.")
    return site


class StatusSerializer(serializers.Serializer):
    enabled = serializers.BooleanField(help_text="GSA has switched AI on for the LMS (AI_ENABLED)")
    teaching = serializers.BooleanField()
    drafts = serializers.BooleanField(help_text="Drafts for teaching staff are on for this course")
    study_helper = serializers.BooleanField(help_text="The study helper is on for this course")
    helper_available = serializers.BooleanField(help_text="The caller may use the study helper now")
    helper_reason = serializers.CharField(allow_null=True, help_text="Why not, in words")
    pictures = serializers.BooleanField(help_text="A model that describes pictures is set up")


class SwitchSerializer(serializers.Serializer):
    drafts = serializers.BooleanField(required=False)
    study_helper = serializers.BooleanField(required=False)


@extend_schema(methods=["GET"], responses={200: StatusSerializer}, summary="AI help on a course: what is on")
@extend_schema(
    methods=["PATCH"],
    request=SwitchSerializer,
    responses={200: StatusSerializer, 403: ErrorSerializer},
    summary="Switch drafts or the study helper on or off for a course (teaching staff; only when GSA has "
    "switched AI on)",
)
@api_view(["GET", "PATCH"])
@permission_classes([RolePermission])
def site_status(request, pk: int):
    site = _site(request, pk)
    if request.method == "PATCH":
        site = _teaching_site(request, pk)
        if not enabled():
            return _refused(services.Refusal("ai_off", "AI help is not switched on for the GSA LMS."))
        data = SwitchSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            chosen, _ = SiteSwitch.objects.get_or_create(site=site, defaults={"created_by": request.user})
            before = snapshot(chosen)
            for name, value in data.validated_data.items():
                setattr(chosen, name, value)
            chosen.updated_by = request.user
            chosen.save()
            record(request, "update", chosen, before=before, after=snapshot(chosen))
    return Response(services.status(request.user, site))


class QuestionsAskSerializer(serializers.Serializer):
    item = serializers.IntegerField(help_text="A page, or a Word or PowerPoint file, on this course")
    count = serializers.IntegerField(min_value=1, max_value=10, default=5)


class DraftSerializer(serializers.Serializer):
    draft = serializers.IntegerField(help_text="Name it when saving, so the save is marked AI-drafted")
    output = serializers.JSONField(help_text="The draft, to review and edit before saving")


def _draft(exchange: Exchange) -> dict:
    return {"draft": exchange.id, "output": exchange.output}


def _audited(request, exchange: Exchange) -> Response:
    record(
        request,
        "ai_drafted",
        exchange,
        after={"kind": exchange.kind, "source": exchange.source_id},
        reason="Draft made with AI help, for the lecturer to review",
    )
    return Response(_draft(exchange), status=201)


@extend_schema(
    request=QuestionsAskSerializer,
    responses={201: DraftSerializer, 400: ErrorSerializer, 403: ErrorSerializer, 502: ErrorSerializer},
    summary="Draft multiple-choice questions from a page or file of the course, for the lecturer to edit",
)
@api_view(["POST"])
@permission_classes([RolePermission])
@throttle_classes([AiThrottle])
def draft_questions(request, pk: int):
    site = _teaching_site(request, pk)
    data = QuestionsAskSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    item = get_object_or_404(ContentItem, pk=data.validated_data["item"], module__site=site)
    try:
        exchange = services.draft_questions(request.user, site, item, data.validated_data["count"])
    except services.Refusal as refusal:
        return _refused(refusal)
    return _audited(request, exchange)


class RubricAskSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=160)
    task = serializers.CharField(max_length=4000, help_text="What the students are asked to do")
    criteria = serializers.ListField(
        child=serializers.CharField(max_length=200), min_length=1, max_length=12, help_text="Criterion names"
    )
    levels = serializers.IntegerField(min_value=2, max_value=6, default=4)


@extend_schema(
    request=RubricAskSerializer,
    responses={201: DraftSerializer, 403: ErrorSerializer, 502: ErrorSerializer},
    summary="Draft the wording of a rubric's levels, for the lecturer to edit",
)
@api_view(["POST"])
@permission_classes([RolePermission])
@throttle_classes([AiThrottle])
def draft_rubric(request, pk: int):
    site = _teaching_site(request, pk)
    data = RubricAskSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    values = data.validated_data
    try:
        exchange = services.draft_rubric(
            request.user, site, values["title"], values["task"], values["criteria"], values["levels"]
        )
    except services.Refusal as refusal:
        return _refused(refusal)
    return _audited(request, exchange)


class AltTextAskSerializer(serializers.Serializer):
    item = serializers.IntegerField(help_text="A picture put up on this course")


@extend_schema(
    request=AltTextAskSerializer,
    responses={201: DraftSerializer, 400: ErrorSerializer, 403: ErrorSerializer, 503: ErrorSerializer},
    summary="Suggest alternative text for a picture on the course, for the lecturer to edit",
)
@api_view(["POST"])
@permission_classes([RolePermission])
@throttle_classes([AiThrottle])
def draft_alt_text(request, pk: int):
    site = _teaching_site(request, pk)
    data = AltTextAskSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    item = get_object_or_404(ContentItem, pk=data.validated_data["item"], module__site=site)
    try:
        exchange = services.suggest_alt_text(request.user, site, item)
    except services.Refusal as refusal:
        return _refused(refusal)
    return _audited(request, exchange)


SAVED_KINDS = {
    "question": ("quizzes.Question", "bank__site"),
    "rubric": ("rubrics.Rubric", "site"),
    "content": ("courses.ContentItem", "module__site"),
}


class SavedSerializer(serializers.Serializer):
    record = serializers.ChoiceField(choices=sorted(SAVED_KINDS), help_text="What the draft was saved as")
    id = serializers.IntegerField()


@extend_schema(
    request=SavedSerializer,
    responses={204: None, 400: ErrorSerializer, 404: ErrorSerializer},
    summary="Say that a reviewed draft was saved as this record: the audit log marks it AI-drafted",
)
@api_view(["POST"])
@permission_classes([RolePermission])
def draft_saved(request, pk: int):
    from django.apps import apps

    exchange = get_object_or_404(
        Exchange.objects.exclude(kind=Exchange.Kind.HELPER), pk=pk, user=request.user
    )
    data = SavedSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    label, site_path = SAVED_KINDS[data.validated_data["record"]]
    model = apps.get_model(label)
    saved = get_object_or_404(model, pk=data.validated_data["id"], **{site_path: exchange.site})
    record(
        request,
        "ai_draft_saved",
        saved,
        after={"draft": exchange.id, "kind": exchange.kind},
        reason="Drafted with AI help; reviewed and saved by the lecturer",
    )
    return Response(status=204)


class AskSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=1000)


class SourceSerializer(serializers.Serializer):
    item = serializers.IntegerField()
    title = serializers.CharField()
    module = serializers.CharField()
    link = serializers.CharField()


class HelperAnswerSerializer(serializers.Serializer):
    answered = serializers.BooleanField(help_text="False when the course's material does not answer it")
    answer = serializers.CharField()
    sources = SourceSerializer(many=True)


@extend_schema(
    request=AskSerializer,
    responses={200: HelperAnswerSerializer, 403: ErrorSerializer, 503: ErrorSerializer},
    summary="Ask the study helper: answered only from the course's own material, with its sources; off "
    "during an open quiz or assignment",
)
@api_view(["POST"])
@permission_classes([RolePermission])
@throttle_classes([AiThrottle])
def ask(request, pk: int):
    site = _site(request, pk)
    data = AskSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    try:
        answer = services.ask(request, site, data.validated_data["question"])
    except services.Refusal as refusal:
        return _refused(refusal)
    return Response({"answered": answer.answered, "answer": answer.answer, "sources": answer.sources})


urlpatterns = [
    path("sites/<int:pk>/ai/", site_status, name="ai-status"),
    path("sites/<int:pk>/ai/drafts/questions/", draft_questions, name="ai-draft-questions"),
    path("sites/<int:pk>/ai/drafts/rubric/", draft_rubric, name="ai-draft-rubric"),
    path("sites/<int:pk>/ai/drafts/alt-text/", draft_alt_text, name="ai-draft-alt-text"),
    path("sites/<int:pk>/ai/ask/", ask, name="ai-ask"),
    path("ai/drafts/<int:pk>/saved/", draft_saved, name="ai-draft-saved"),
]
