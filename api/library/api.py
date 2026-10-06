"""The shared content library (item 5.14).

Who may do what:
- browse, read and use the library: anyone who teaches a course, and course administrators; the auditor
  browses and reads it, and changes nothing (item 1.02);
- add to a department's shelf, or change and remove what is there: course administrators, and lecturers
  whose lecturer role is scoped to that department (as for department question banks);
- add to the whole School's shelf: anyone who teaches; the person who added an item may always change it.
Using an item copies it into a module of a course the person teaches, as a draft, against that course's
storage allowance.
"""

from django.core.files import File
from django.db import transaction
from django.db.models import Max, Q
from django.http import FileResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import SAFE_METHODS
from rest_framework.response import Response

from audit.services import record, snapshot
from core.serializers import ErrorSerializer
from core.uploads import CONTENT, original_name, validate_upload
from courses import richtext, storage
from courses.access import TaughtRecord, taught_sites
from courses.api import CREDITED
from courses.models import ContentItem, Module
from iam.models import Role, RoleScope
from iam.permissions import RolePermission
from iam.services import SITE_ADMIN_ROLES, has_role
from library.models import LibraryItem, SharedBank
from packages import archive
from quizzes.models import Question, QuestionBank, QuestionVersion


def may_browse(user) -> bool:
    return has_role(user, *SITE_ADMIN_ROLES, Role.LECTURER) or taught_sites(user).exists()


def may_open(request) -> bool:
    """Whether the caller may use this part of the library: those who browse it, and the auditor to read."""
    if may_browse(request.user):
        return True
    return request.method in SAFE_METHODS and has_role(request.user, Role.AUDITOR)


def may_shelve(user, department_code: str) -> bool:
    """May add to (or manage) a department's shelf, or the whole School's when the code is empty."""
    if has_role(user, *SITE_ADMIN_ROLES):
        return True
    if not department_code:
        return may_browse(user)
    return RoleScope.objects.filter(user=user, role__code=Role.LECTURER, unit_code=department_code).exists()


def check_licence(attrs: dict, *, open_resource: bool = False) -> None:
    licence = attrs.get("licence")
    if open_resource and licence != ContentItem.Licence.OPEN_LICENCE:
        raise serializers.ValidationError(
            {"licence": ["An open educational resource is under an open licence."]}
        )
    if licence == ContentItem.Licence.OPEN_LICENCE and not attrs.get("open_licence"):
        raise serializers.ValidationError({"open_licence": ["Say which open licence."]})
    if licence != ContentItem.Licence.OPEN_LICENCE:
        attrs["open_licence"] = ""
    if licence in CREDITED and not (attrs.get("source") or "").strip():
        raise serializers.ValidationError(
            {"source": ["Say where the material comes from and how to credit its author."]}
        )
    if open_resource and not (attrs.get("publisher") or "").strip():
        raise serializers.ValidationError({"publisher": ["Name the publisher, such as FAO or CABI."]})


class LibraryItemSerializer(serializers.ModelSerializer):
    file = serializers.FileField(
        write_only=True,
        required=False,
        help_text="For a file: a PDF, photograph or Office file (as course files). For a package: a SCORM "
        "package or an H5P file (as /packages/)",
    )
    filename = serializers.CharField(source="original_name", read_only=True)
    download_url = serializers.SerializerMethodField()
    may_change = serializers.SerializerMethodField(help_text="Whether the requester may change or remove it")
    body_format = serializers.ChoiceField(choices=["html", "text"], default="html", write_only=True)

    class Meta:
        model = LibraryItem
        fields = (
            "id",
            "kind",
            "title",
            "description",
            "body",
            "body_format",
            "file",
            "filename",
            "file_size",
            "download_url",
            "url",
            "package",
            "licence",
            "open_licence",
            "source",
            "publisher",
            "department_code",
            "is_open_resource",
            "tags",
            "shared_from",
            "may_change",
            "created_at",
        )
        read_only_fields = ("file_size", "package", "shared_from", "created_at")
        extra_kwargs = {"title": {"required": False}}

    def get_download_url(self, obj) -> str | None:
        return f"/api/v1/library/items/{obj.id}/download/" if obj.file else None

    def get_may_change(self, obj) -> bool:
        request = self.context.get("request")
        return bool(request) and (
            obj.created_by_id == request.user.id
            or (
                has_role(request.user, *SITE_ADMIN_ROLES)
                if not obj.department_code
                else may_shelve(request.user, obj.department_code)
            )
        )

    def validate(self, attrs):
        instance = self.instance
        if instance is not None and ("kind" in attrs and attrs["kind"] != instance.kind or "file" in attrs):
            raise serializers.ValidationError({"kind": ["Put up a new item to change its kind or its file."]})
        kind = attrs.get("kind") or instance.kind
        merged = {
            f: attrs.get(f, getattr(instance, f, ""))
            for f in ("licence", "open_licence", "source", "publisher")
        }
        open_resource = attrs.get("is_open_resource", getattr(instance, "is_open_resource", False))
        if not merged["licence"]:
            raise serializers.ValidationError({"licence": ["Say whose material this is."]})
        check_licence(merged, open_resource=open_resource)
        attrs["open_licence"] = merged["open_licence"]
        if instance is None:
            upload = attrs.get("file")
            if kind in (ContentItem.Kind.FILE, ContentItem.Kind.PACKAGE) and not upload:
                raise serializers.ValidationError({"file": ["Choose the file to put up."]})
            if kind == ContentItem.Kind.LINK and not attrs.get("url"):
                raise serializers.ValidationError({"url": ["Give the web address the link goes to."]})
            if kind == ContentItem.Kind.FILE:
                try:
                    attrs["file"] = validate_upload(upload, CONTENT)
                except serializers.ValidationError as refused:
                    raise serializers.ValidationError({"file": refused.detail}) from refused
            if kind == ContentItem.Kind.PACKAGE:
                try:
                    checked = archive.check(upload)
                except archive.PackageRefused as refused:
                    raise serializers.ValidationError({"file": [str(refused)]}) from refused
                attrs["package"] = {
                    "standard": checked.standard,
                    "version_label": checked.version_label,
                    "scos": [sco.as_dict() for sco in checked.scos],
                    "entries": checked.entries,
                    "unpacked_bytes": checked.unpacked_bytes,
                }
                attrs["title"] = attrs.get("title") or checked.title
            if not attrs.get("title"):
                raise serializers.ValidationError({"title": ["Give the item a title."]})
        body_format = attrs.pop("body_format", "html")
        if "body" in attrs:
            cleaned = (
                richtext.text_to_html(attrs["body"])
                if body_format == "text"
                else richtext.clean(attrs["body"])
            )
            if richtext.image_item_ids(cleaned):
                raise serializers.ValidationError(
                    {"body": ["A library page cannot show a course's pictures."]}
                )
            refused = richtext.errors(richtext.check(cleaned))
            if refused:
                raise serializers.ValidationError({"body": [issue.detail for issue in refused]})
            attrs["body"] = cleaned
        if attrs.get("tags"):
            attrs["tags"] = [t.strip()[:40] for t in attrs["tags"] if t.strip()][:20]
        return attrs

    def save(self, **kwargs):
        upload = self.validated_data.get("file")
        if upload:
            kwargs["original_name"] = original_name(upload)
            kwargs["file_size"] = upload.size
        return super().save(**kwargs)


class UseSerializer(serializers.Serializer):
    module = TaughtRecord(Module, "site", help_text="A module of a course you teach")


class ShareSerializer(serializers.Serializer):
    item = TaughtRecord(ContentItem, "module__site", help_text="An item of a course you teach")
    department_code = serializers.CharField(required=False, allow_blank=True, default="")
    description = serializers.CharField(required=False, allow_blank=True, default="")
    tags = serializers.ListField(child=serializers.CharField(max_length=40), required=False, default=list)


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter("q", OpenApiTypes.STR, description="Words in the title, description or tags"),
            OpenApiParameter("kind", OpenApiTypes.STR, description="page, file, link or package"),
            OpenApiParameter(
                "department", OpenApiTypes.STR, description="One department's shelf; '-' for the School's"
            ),
            OpenApiParameter("open", OpenApiTypes.BOOL, description="Only open educational resources"),
        ],
        summary="Browse the shared content library (item 5.14)",
    ),
    create=extend_schema(
        request={"multipart/form-data": LibraryItemSerializer, "application/json": LibraryItemSerializer},
        summary="Add to the library: a page, file, link or package, or an open educational resource",
    ),
)
class LibraryItemViewSet(viewsets.ModelViewSet):
    serializer_class = LibraryItemSerializer
    permission_classes = [RolePermission]
    parser_classes = (JSONParser, MultiPartParser, FormParser)
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    queryset = LibraryItem.objects.none()

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not may_open(request):
            raise PermissionDenied("The content library is for teaching staff.")

    def get_queryset(self):
        qs = LibraryItem.objects.all()
        params = self.request.query_params
        if params.get("q"):
            words = params["q"].strip()
            qs = qs.filter(
                Q(title__icontains=words) | Q(description__icontains=words) | Q(tags__contains=[words])
            )
        if params.get("kind"):
            qs = qs.filter(kind=params["kind"])
        if params.get("department"):
            qs = qs.filter(department_code="" if params["department"] == "-" else params["department"])
        if params.get("open") in ("true", "1"):
            qs = qs.filter(is_open_resource=True)
        return qs

    def get_serializer_class(self):
        return {"use": UseSerializer, "share": ShareSerializer}.get(self.action, LibraryItemSerializer)

    def _require_shelf(self, department_code: str, item: LibraryItem | None = None) -> None:
        if item is not None and item.created_by_id == self.request.user.id:
            return
        if (
            item is not None
            and not item.department_code
            and not has_role(self.request.user, *SITE_ADMIN_ROLES)
        ):
            # Anyone who teaches adds to the whole School's shelf; only who added it, or a course
            # administrator, changes or removes it there.
            raise PermissionDenied("Only who added it, or a course administrator, changes this item.")
        if not may_shelve(self.request.user, department_code):
            raise PermissionDenied(
                "Only course administrators and that department's lecturers manage its shelf of the library."
            )

    def perform_create(self, serializer):
        self._require_shelf(serializer.validated_data.get("department_code", ""))
        with transaction.atomic():
            item = serializer.save(created_by=self.request.user, updated_by=self.request.user)
            record(self.request, "create", item, after=snapshot(item))

    def perform_update(self, serializer):
        self._require_shelf(serializer.instance.department_code, serializer.instance)
        if "department_code" in serializer.validated_data:
            self._require_shelf(serializer.validated_data["department_code"])
        with transaction.atomic():
            before = snapshot(serializer.instance)
            item = serializer.save(updated_by=self.request.user)
            record(self.request, "update", item, before=before, after=snapshot(item))

    def perform_destroy(self, instance):
        self._require_shelf(instance.department_code, instance)
        with transaction.atomic():
            before, entity_id = snapshot(instance), instance.pk
            instance.delete()
            record(self.request, "delete", instance, before=before, entity_id=entity_id)

    @extend_schema(responses={(200, "application/octet-stream"): OpenApiTypes.BINARY, 404: ErrorSerializer})
    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        item = self.get_object()
        if not item.file:
            return Response({"code": "no_file", "detail": "This item has no file."}, status=404)
        record(request, "download", item, after={"title": item.title})
        return FileResponse(item.file.open("rb"), as_attachment=True, filename=item.original_name or "file")

    @extend_schema(
        request=UseSerializer,
        responses={201: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 403: ErrorSerializer},
        summary="Copy a library item into a module of a course you teach, as a draft",
    )
    @action(detail=True, methods=["post"])
    def use(self, request, pk=None):
        item = self.get_object()
        data = UseSerializer(data=request.data, context={"request": request})
        data.is_valid(raise_exception=True)
        module = data.validated_data["module"]
        site = module.site
        with transaction.atomic():
            if item.file:
                storage.require_room(site, item.file_size)
            last = module.items.aggregate(last=Max("position"))["last"] or 0
            copy = ContentItem(
                module=module,
                kind=item.kind,
                title=item.title,
                body=item.body,
                url=item.url,
                position=last + 1,
                is_published=False,
                licence=item.licence,
                open_licence=item.open_licence,
                source=_credit(item),
                created_by=request.user,
                updated_by=request.user,
            )
            if item.file:
                with item.file.open("rb") as handle:
                    copy.file.save(item.original_name or "file", File(handle), save=False)
                copy.original_name, copy.file_size = item.original_name, item.file_size
            copy.save()
            if item.kind == ContentItem.Kind.PACKAGE:
                from packages.models import ContentPackage

                ContentPackage.objects.create(
                    item=copy,
                    standard=item.package.get("standard", ""),
                    version_label=item.package.get("version_label", ""),
                    scos=item.package.get("scos", []),
                    entries=item.package.get("entries", 0),
                    unpacked_bytes=item.package.get("unpacked_bytes", 0),
                    created_by=request.user,
                    updated_by=request.user,
                )
            record(request, "create", copy, after={**snapshot(copy), "from_library": item.id})
        return Response(
            {
                "item": copy.id,
                "module": module.id,
                "site": site.id,
                "title": copy.title,
                "storage": storage.summary(site),
            },
            status=201,
        )

    @extend_schema(
        request=ShareSerializer,
        responses={201: LibraryItemSerializer, 400: OpenApiTypes.OBJECT, 403: ErrorSerializer},
        summary="Put a copy of an item of your course on the library's shelves",
    )
    @action(detail=False, methods=["post"])
    def share(self, request):
        data = ShareSerializer(data=request.data, context={"request": request})
        data.is_valid(raise_exception=True)
        source = data.validated_data["item"]
        department = data.validated_data["department_code"].strip()
        self._require_shelf(department)
        if source.under_review or source.takedowns.exists():
            return Response(
                {
                    "code": "taken_down",
                    "detail": "Material reported for takedown cannot go into the library.",
                },
                status=409,
            )
        if source.licence == ContentItem.Licence.UNKNOWN:
            return Response(
                {"code": "licence_unknown", "detail": "Say whose material this is before sharing it."},
                status=409,
            )
        if richtext.image_item_ids(source.body):
            return Response(
                {
                    "code": "has_pictures",
                    "detail": "A page showing the course's pictures cannot be shared yet.",
                },
                status=409,
            )
        package = getattr(source, "package", None)
        with transaction.atomic():
            item = LibraryItem(
                kind=source.kind,
                title=source.title,
                description=data.validated_data["description"],
                body=source.body,
                url=source.url,
                licence=source.licence,
                open_licence=source.open_licence,
                source=source.source,
                department_code=department,
                tags=data.validated_data["tags"][:20],
                shared_from=source,
                created_by=request.user,
                updated_by=request.user,
            )
            if package is not None:
                item.package = {
                    "standard": package.standard,
                    "version_label": package.version_label,
                    "scos": package.scos,
                    "entries": package.entries,
                    "unpacked_bytes": package.unpacked_bytes,
                }
            if source.file:
                with source.file.open("rb") as handle:
                    item.file.save(source.original_name or "file", File(handle), save=False)
                item.original_name, item.file_size = source.original_name, source.file_size
            item.save()
            record(request, "create", item, after={**snapshot(item), "shared_from": source.id})
        return Response(LibraryItemSerializer(item, context={"request": request}).data, status=201)


def _credit(item: LibraryItem) -> str:
    if item.publisher and item.publisher not in item.source:
        return f"{item.source} ({item.publisher})".strip() if item.source else item.publisher
    return item.source


# ---------------------------------------------------------------------------------------------------------
# Question banks


class SharedBankSerializer(serializers.Serializer):
    id = serializers.IntegerField(help_text="The department bank")
    name = serializers.CharField()
    department_code = serializers.CharField()
    questions = serializers.IntegerField()
    licence = serializers.CharField(allow_null=True, help_text="Null when no licence was recorded")
    open_licence = serializers.CharField(allow_blank=True)
    source = serializers.CharField(allow_blank=True)
    publisher = serializers.CharField(allow_blank=True)
    copied_from = serializers.IntegerField(allow_null=True)


class ShareBankSerializer(serializers.Serializer):
    # A course's bank, settled first (item 1.15): one on a course the caller cannot open reads as unknown, one
    # on a course they do not teach on is refused, before the rest of the form is read.
    bank = TaughtRecord(QuestionBank, "site")
    department_code = serializers.CharField(max_length=20)
    name = serializers.CharField(max_length=160, required=False, allow_blank=True)
    licence = serializers.ChoiceField(choices=ContentItem.Licence.choices)
    open_licence = serializers.ChoiceField(
        choices=ContentItem.OpenLicence.choices, required=False, allow_blank=True
    )
    source = serializers.CharField(required=False, allow_blank=True, default="")
    publisher = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        from quizzes.services import can_manage_bank

        if not can_manage_bank(self.context["request"].user, attrs["bank"]):
            raise PermissionDenied("Only the course's teaching staff share its question bank.")
        check_licence(attrs)
        return attrs


def _bank_row(bank: QuestionBank) -> dict:
    shared = getattr(bank, "shared", None)
    return {
        "id": bank.id,
        "name": bank.name,
        "department_code": bank.department_code,
        "questions": bank.questions.filter(is_archived=False).count(),
        "licence": shared.licence if shared else None,
        "open_licence": shared.open_licence if shared else "",
        "source": shared.source if shared else "",
        "publisher": shared.publisher if shared else "",
        "copied_from": shared.copied_from_id if shared else None,
    }


class SharedBankViewSet(viewsets.ViewSet):
    """Department question banks, with their licences: shared with every lecturer (item 5.14)."""

    permission_classes = [RolePermission]
    serializer_class = SharedBankSerializer

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not may_open(request):
            raise PermissionDenied("The content library is for teaching staff.")

    @extend_schema(
        responses=SharedBankSerializer(many=True), summary="Department question banks and their licences"
    )
    def list(self, request):
        banks = (
            QuestionBank.objects.filter(site__isnull=True)
            .select_related("shared")
            .order_by("department_code", "name")
        )
        return Response([_bank_row(bank) for bank in banks])

    @extend_schema(
        request=ShareBankSerializer,
        responses={201: SharedBankSerializer, 400: OpenApiTypes.OBJECT, 403: ErrorSerializer},
        summary="Copy a course's question bank to a department's shelf, with its licence",
        description="Every question that is not archived is copied, at its latest version, in its "
        "categories.",
    )
    @action(detail=False, methods=["post"])
    def share(self, request):
        from quizzes.services import _category_for, category_path_of

        data = ShareBankSerializer(data=request.data, context={"request": request})
        data.is_valid(raise_exception=True)
        values = data.validated_data
        if not may_shelve(request.user, values["department_code"]):
            raise PermissionDenied(
                "Only course administrators and that department's lecturers add to its shelf."
            )
        source = values["bank"]
        user = request.user
        with transaction.atomic():
            bank = QuestionBank.objects.create(
                name=(values.get("name") or source.name)[:160],
                department_code=values["department_code"],
                description=source.description,
                created_by=user,
                updated_by=user,
            )
            cache: dict = {}
            questions = source.questions.filter(is_archived=False).select_related("category__parent")
            for question in questions:
                latest = question.latest
                if latest is None:
                    continue
                category = _category_for(bank, None, category_path_of(question.category), cache, user)
                copy = Question.objects.create(
                    bank=bank,
                    category=category,
                    qtype=question.qtype,
                    name=question.name,
                    tags=question.tags,
                    created_by=user,
                    updated_by=user,
                )
                QuestionVersion.objects.create(
                    question=copy,
                    text=latest.text,
                    data=latest.data,
                    default_mark=latest.default_mark,
                    general_feedback=latest.general_feedback,
                    image=latest.image,
                    created_by=user,
                )
            SharedBank.objects.create(
                bank=bank,
                copied_from=source,
                licence=values["licence"],
                open_licence=values.get("open_licence", ""),
                source=values["source"],
                publisher=values["publisher"],
                created_by=user,
                updated_by=user,
            )
            record(request, "create", bank, after={**snapshot(bank), "copied_from": source.id})
        return Response(_bank_row(QuestionBank.objects.get(pk=bank.pk)), status=201)


def library_router():
    from rest_framework.routers import DefaultRouter

    router = DefaultRouter()
    router.register("library/items", LibraryItemViewSet, basename="library-item")
    router.register("library/banks", SharedBankViewSet, basename="library-bank")
    return router.urls


urlpatterns = library_router()
