"""Packages (items 5.12, 5.13) and the LMS's statement store (item 6.09).

Teaching staff put a SCORM 1.2 or 2004 package (.zip) or an H5P file (.h5p) up as an item of a module, with
its licence like any file, and say whether it counts in coursework. H5P is not authored in the LMS: lecturers
make exercises in the free H5P editor (or the Lumi desktop app, which is not shipped with the LMS) and put
the .h5p file up here. Students open a package in an attempt; teaching staff try it in a preview attempt and
see every learner's attempts and statements.
"""

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.urls import path
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field, extend_schema_view
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from assessments.models import GradeCategory
from audit.services import record, snapshot
from core.serializers import ErrorSerializer
from courses import release, storage
from courses.access import TaughtRecord, can_teach, person_of, site_role, taught_sites, visible_sites
from courses.api import CREDITED
from courses.models import ContentItem, Membership, Module
from iam.permissions import RolePermission
from packages import archive, play, services, xapi
from packages.models import ContentPackage, PackageAttempt, Statement

H5P_AUTHORING = (
    "H5P exercises are not written in the LMS. Make them in the free H5P editor or the Lumi desktop app, "
    "save them as an .h5p file with their libraries, and put the file up here."
)


class PackageAttemptSerializer(serializers.ModelSerializer):
    learner = serializers.SerializerMethodField(help_text="The learner's name; null for a preview")
    student_no = serializers.CharField(source="person.external_id", read_only=True, default=None)
    score_percent = serializers.SerializerMethodField(help_text="The score as a percentage, or null")

    class Meta:
        model = PackageAttempt
        fields = (
            "id",
            "number",
            "registration",
            "is_preview",
            "learner",
            "student_no",
            "completion",
            "success",
            "score",
            "score_percent",
            "created_at",
            "last_commit_at",
            "completed_at",
        )
        read_only_fields = fields

    def get_learner(self, obj) -> str | None:
        return obj.person.full_name if obj.person and not obj.is_preview else None

    def get_score_percent(self, obj) -> str | None:
        return None if obj.score is None else f"{obj.score * 100:.1f}"


class PackageSerializer(serializers.ModelSerializer):
    title = serializers.CharField(source="item.title", read_only=True)
    site = serializers.IntegerField(source="item.module.site_id", read_only=True)
    module = serializers.IntegerField(source="item.module_id", read_only=True)
    is_published = serializers.BooleanField(source="item.is_published", read_only=True)
    licence = serializers.CharField(source="item.licence", read_only=True)
    source = serializers.CharField(source="item.source", read_only=True)
    grade_category = serializers.PrimaryKeyRelatedField(
        queryset=GradeCategory.objects.all(), required=False, allow_null=True
    )
    my_attempts = serializers.SerializerMethodField(help_text="The requester's own attempts (not previews)")
    attempts_left = serializers.SerializerMethodField(help_text="Null when there is no limit")
    my_result = serializers.SerializerMethodField(
        help_text="What counts for the requester: {fraction, state}, as in the gradebook"
    )

    class Meta:
        model = ContentPackage
        fields = (
            "id",
            "item",
            "title",
            "site",
            "module",
            "is_published",
            "licence",
            "source",
            "standard",
            "version_label",
            "scos",
            "entries",
            "unpacked_bytes",
            "weight",
            "grade_category",
            "max_attempts",
            "my_attempts",
            "attempts_left",
            "my_result",
        )
        read_only_fields = ("item", "standard", "version_label", "scos", "entries", "unpacked_bytes")

    def validate_grade_category(self, value):
        if value is not None and self.instance is not None and value.site_id != self.instance.site.id:
            raise serializers.ValidationError("Choose a category of the same course.")
        return value

    def _mine(self, obj) -> list[PackageAttempt]:
        request = self.context.get("request")
        person = person_of(request.user) if request else None
        return services.attempts_of(obj, person) if person is not None else []

    @extend_schema_field(PackageAttemptSerializer(many=True))
    def get_my_attempts(self, obj) -> list[dict]:
        return PackageAttemptSerializer(self._mine(obj), many=True).data

    def get_attempts_left(self, obj) -> int | None:
        if not obj.max_attempts:
            return None
        return max(obj.max_attempts - len(self._mine(obj)), 0)

    def get_my_result(self, obj) -> dict:
        request = self.context.get("request")
        person = person_of(request.user) if request else None
        if person is None:
            return {"fraction": None, "state": "not_due"}
        fraction, state = services.best_result(obj, person)
        return {"fraction": None if fraction is None else str(fraction), "state": state}


class UploadSerializer(serializers.Serializer):
    module = TaughtRecord(
        Module, "site", help_text="The module the package goes in; you must teach the course"
    )
    title = serializers.CharField(
        max_length=160, required=False, allow_blank=True, help_text="The package's own title when left out"
    )
    file = serializers.FileField(
        help_text="A SCORM 1.2 or 2004 package (.zip with imsmanifest.xml) or an H5P file (.h5p with its "
        "libraries); at most UPLOAD_LIMIT_PACKAGE_MB, within the course's storage allowance"
    )
    licence = serializers.ChoiceField(choices=ContentItem.Licence.choices)
    open_licence = serializers.ChoiceField(
        choices=ContentItem.OpenLicence.choices, required=False, allow_blank=True
    )
    source = serializers.CharField(required=False, allow_blank=True)
    is_published = serializers.BooleanField(required=False, default=False)
    weight = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, required=False, default=0)
    max_attempts = serializers.IntegerField(min_value=0, max_value=100, required=False, default=0)

    def validate(self, attrs):
        if attrs["licence"] == ContentItem.Licence.OPEN_LICENCE and not attrs.get("open_licence"):
            raise serializers.ValidationError({"open_licence": ["Say which open licence."]})
        if attrs["licence"] in CREDITED and not attrs.get("source", "").strip():
            raise serializers.ValidationError(
                {"source": ["Say where the material comes from and how to credit its author."]}
            )
        try:
            attrs["checked"] = archive.check(attrs["file"])
        except archive.PackageRefused as refused:
            raise serializers.ValidationError({"file": [str(refused)]}) from refused
        reason = storage.refusal(attrs["module"].site, attrs["file"].size)
        if reason:
            raise serializers.ValidationError({"file": [reason]})
        return attrs


class LaunchSerializer(serializers.Serializer):
    sco = serializers.CharField(
        required=False, allow_blank=True, help_text="Which part; the first when left out"
    )
    new_attempt = serializers.BooleanField(
        default=False, help_text="Start a new attempt when the last is finished and attempts remain"
    )


class LaunchedSerializer(serializers.Serializer):
    attempt = PackageAttemptSerializer()
    sco = serializers.DictField(help_text="The part opened: {id, title, href, parameters}")
    standard = serializers.CharField()
    play_url = serializers.CharField(help_text="Open in a sandboxed frame; valid for PACKAGE_PLAY_HOURS")
    commit_url = serializers.CharField(help_text="SCORM: where the run-time commits, as the learner")
    cmi = serializers.DictField(help_text="SCORM: the run-time data to start with (scorm-again loadFromJSON)")
    activity = serializers.CharField(help_text="The package's xAPI activity id")
    registration = serializers.UUIDField(help_text="Put in context.registration of every statement sent")


def _readable_packages(request):
    """Packages whose item the requester may see: as ContentItemViewSet, release conditions applied."""
    user = request.user
    items = ContentItem.objects.filter(module__site__in=visible_sites(user), kind=ContentItem.Kind.PACKAGE)
    items = items.filter(is_published=True) | items.filter(module__site__in=taught_sites(user))
    hidden = release.hidden_items(request, items)
    if hidden:
        items = items.exclude(id__in=hidden)
    return ContentPackage.objects.filter(item__in=items).select_related("item__module__site")


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter("item", OpenApiTypes.INT, description="The package of this content item"),
            OpenApiParameter("site", OpenApiTypes.INT, description="Only this site's packages"),
        ],
        summary="Packages the requester may open",
    ),
    partial_update=extend_schema(summary="Change how a package counts: weight, category and attempts"),
)
class PackageViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = PackageSerializer
    permission_classes = [RolePermission]
    parser_classes = (JSONParser, MultiPartParser, FormParser)
    http_method_names = ["get", "post", "patch", "head", "options"]
    queryset = ContentPackage.objects.none()

    def get_queryset(self):
        qs = _readable_packages(self.request)
        params = self.request.query_params
        if params.get("item"):
            qs = qs.filter(item_id=params["item"])
        if params.get("site"):
            qs = qs.filter(item__module__site_id=params["site"])
        return qs.order_by("item__module__position", "item__position", "id")

    def get_serializer_class(self):
        return {"create": UploadSerializer, "launch": LaunchSerializer}.get(self.action, PackageSerializer)

    @extend_schema(
        request={"multipart/form-data": UploadSerializer},
        responses={201: PackageSerializer, 400: OpenApiTypes.OBJECT, 403: ErrorSerializer},
        summary="Put a SCORM package or an H5P file up as an item of a module (items 5.12, 5.13)",
        description=H5P_AUTHORING,
    )
    def create(self, request, *args, **kwargs):
        data = UploadSerializer(data=request.data, context={"request": request})
        data.is_valid(raise_exception=True)
        values = data.validated_data
        package = services.put_up(
            request,
            module=values["module"],
            upload=values["file"],
            checked=values["checked"],
            item_fields={
                "title": (values.get("title") or "").strip()[:160],
                "licence": values["licence"],
                "open_licence": values.get("open_licence", "") if values["licence"] == "open_licence" else "",
                "source": values.get("source", ""),
                "is_published": values["is_published"],
            },
            package_fields={"weight": values["weight"], "max_attempts": values["max_attempts"]},
        )
        body = PackageSerializer(package, context={"request": request}).data
        return Response({**body, "storage": storage.summary(values["module"].site)}, status=201)

    def perform_update(self, serializer):
        package = serializer.instance
        if not can_teach(self.request.user, package.site):
            raise PermissionDenied("Only the site's teaching staff can change a package.")
        with transaction.atomic():
            before = snapshot(package)
            saved = serializer.save(updated_by=self.request.user)
            record(self.request, "update", saved, before=before, after=snapshot(saved))

    @extend_schema(
        request=LaunchSerializer,
        responses={
            200: LaunchedSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            409: ErrorSerializer,
        },
        summary="Open the package: the attempt to work in, and the address of the sandboxed player",
        description="Students work in their open attempt, or a new one when the last is finished and they "
        "ask (within the package's limit). Teaching staff get a preview attempt, which never counts.",
    )
    @action(detail=True, methods=["post"])
    def launch(self, request, pk=None):
        package = self.get_object()
        role = site_role(request.user, package.site)
        learner = role == Membership.SiteRole.STUDENT
        if not learner and not can_teach(request.user, package.site):
            raise PermissionDenied(
                "Only the course's students, and its teaching staff in preview, open packages."
            )
        data = LaunchSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            sco = services.sco_of(package, data.validated_data.get("sco"))
            attempt = services.launch(
                package,
                user=request.user,
                person=person_of(request.user),
                learner=learner,
                new=data.validated_data["new_attempt"],
            )
        except services.Refused as refused:
            return Response({"code": refused.code, "detail": refused.detail}, status=refused.status)
        record(request, "package_launch", attempt, after={"package": package.pk, "attempt": attempt.number})
        scorm = package.standard != ContentPackage.Standard.H5P
        return Response(
            {
                "attempt": PackageAttemptSerializer(attempt).data,
                "sco": sco,
                "standard": package.standard,
                "play_url": play.play_url(attempt, sco),
                "commit_url": f"/api/v1/package-attempts/{attempt.pk}/commit/?sco={sco['id']}"
                if scorm
                else "",
                "cmi": services.initial_cmi(attempt, sco["id"]) if scorm else {},
                "activity": services.activity_iri(package),
                "registration": str(attempt.registration),
            }
        )

    @extend_schema(
        responses={200: PackageAttemptSerializer(many=True), 403: ErrorSerializer, 404: ErrorSerializer},
        summary="Every learner's attempts (teaching staff), or the requester's own",
    )
    @action(detail=True, methods=["get"])
    def attempts(self, request, pk=None):
        package = self.get_object()
        attempts = package.attempts.select_related("person")
        if can_teach(request.user, package.site):
            attempts = attempts.filter(is_preview=False)
        else:
            attempts = attempts.filter(user=request.user, is_preview=False)
        return Response(
            PackageAttemptSerializer(attempts.order_by("person__last_name", "number"), many=True).data
        )


class CommitResultSerializer(serializers.Serializer):
    result = serializers.BooleanField()
    errorCode = serializers.IntegerField()  # noqa: N815 - the name scorm-again reads
    attempt = PackageAttemptSerializer()


@extend_schema(
    request=OpenApiTypes.OBJECT,
    parameters=[OpenApiParameter("sco", OpenApiTypes.STR, description="The part that commits")],
    responses={200: CommitResultSerializer, 400: ErrorSerializer, 404: ErrorSerializer},
    summary="Keep what a SCORM part committed (scorm-again's JSON commit), as the learner (item 5.12)",
)
@api_view(["POST"])
@permission_classes([RolePermission])
def commit(request, pk: int):
    attempt = get_object_or_404(
        PackageAttempt.objects.select_related("package__item__module__site", "person"),
        pk=pk,
        user=request.user,
    )
    try:
        attempt = services.commit(request, attempt, request.query_params.get("sco", ""), request.data)
    except services.Refused as refused:
        return Response({"code": refused.code, "detail": refused.detail}, status=refused.status)
    return Response({"result": True, "errorCode": 0, "attempt": PackageAttemptSerializer(attempt).data})


class StatementsSerializer(serializers.Serializer):
    statements = serializers.ListField(child=serializers.DictField())
    more = serializers.CharField(help_text="Always empty: the newest STATEMENT_PAGE statements are returned")


STATEMENT_PAGE = 200


@extend_schema(
    methods=["GET"],
    parameters=[
        OpenApiParameter("activity", OpenApiTypes.STR, description="Statements about this activity id"),
        OpenApiParameter("related_activities", OpenApiTypes.BOOL, description="And the activities below it"),
        OpenApiParameter(
            "agent", OpenApiTypes.STR, description='An agent as JSON: {"account": {"name": ...}}'
        ),
        OpenApiParameter("person", OpenApiTypes.INT, description="Or a learner by person id"),
        OpenApiParameter("registration", OpenApiTypes.UUID, description="One attempt"),
        OpenApiParameter("site", OpenApiTypes.INT, description="One course"),
        OpenApiParameter("since", OpenApiTypes.DATETIME, description="Stored after this time"),
    ],
    responses={200: StatementsSerializer, 400: ErrorSerializer, 403: ErrorSerializer},
    summary="Read the statements of the courses you teach (item 6.09; not a general LRS)",
)
@extend_schema(
    methods=["POST"],
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.OBJECT, 400: ErrorSerializer, 409: ErrorSerializer},
    summary="Send statements from the LMS's own packaged content, as the learner (item 6.09)",
    description="A statement or a list of at most 50. Each must carry its attempt's registration in "
    "context.registration and be about that package's activities; the LMS writes the actor and authority. "
    "Answers with the stored ids, as an xAPI LRS does.",
)
@api_view(["GET", "POST"])
@permission_classes([RolePermission])
def statements(request):
    if request.method == "POST":
        bodies = request.data if isinstance(request.data, list) else [request.data]
        try:
            ids = xapi.accept(request, bodies)
        except services.Refused as refused:
            return Response({"code": refused.code, "detail": refused.detail}, status=refused.status)
        response = Response(ids)
    else:
        if not taught_sites(request.user).exists():
            raise PermissionDenied("Only teaching staff read statements.")
        response = Response(_query(request))
    response["X-Experience-API-Version"] = xapi.VERSION
    return response


def _query(request) -> dict:
    import json as jsonlib

    from django.utils.dateparse import parse_datetime

    params = request.query_params
    qs = xapi.visible(Statement.objects.all(), request.user).order_by("-stored")
    if params.get("site"):
        qs = qs.filter(site_id=params["site"])
    if params.get("activity"):
        activity = params["activity"]
        if params.get("related_activities") in ("true", "1"):
            qs = qs.filter(
                Q(activity=activity)
                | Q(activity__startswith=f"{activity}/")
                | Q(activity__startswith=f"{activity}?")
            )
        else:
            qs = qs.filter(activity=activity)
    if params.get("registration"):
        qs = qs.filter(attempt__registration=params["registration"])
    if params.get("person"):
        qs = qs.filter(person_id=params["person"])
    if params.get("agent"):
        try:
            agent = jsonlib.loads(params["agent"])
            name = agent["account"]["name"]
        except (ValueError, KeyError, TypeError) as error:
            raise serializers.ValidationError(
                {"agent": ['Give an agent as {"account": {"name": ...}}.']}
            ) from error
        qs = qs.filter(person__external_id=name)
    if params.get("since"):
        since = parse_datetime(params["since"])
        if since is None:
            raise serializers.ValidationError({"since": ["Give a date and time (ISO 8601)."]})
        qs = qs.filter(stored__gt=since)
    return {"statements": [xapi.as_json(s) for s in qs[:STATEMENT_PAGE]], "more": ""}


router = DefaultRouter()
router.register("packages", PackageViewSet, basename="package")
urlpatterns = [
    path("package-attempts/<int:pk>/commit/", commit, name="package-commit"),
    path("xapi/statements/", statements, name="xapi-statements"),
    *router.urls,
]
