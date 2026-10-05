"""Course sites, modules, content, announcements. Students see published, released material only."""

from datetime import timedelta

from django.core.files import File
from django.db import transaction
from django.db.models import F, Max
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from audit.services import record, snapshot
from core.serializers import ErrorSerializer
from core.uploads import CONTENT, original_name, validate_upload
from courses import copying, release, richtext, site_templates, storage
from courses.access import (
    ADMIN,
    TEACHING,
    TaughtRecord,
    can_teach,
    person_of,
    site_role,
    taught_sites,
    visible_sites,
)
from courses.models import (
    Announcement,
    ContentItem,
    CourseSite,
    ItemCompletion,
    Membership,
    Module,
    SiteGroup,
    SiteTemplate,
    TakedownRequest,
)
from iam.permissions import RolePermission
from iam.services import SITE_ADMIN_ROLES, has_role

# Licences that use someone else's material: where it comes from must be said.
CREDITED = {
    ContentItem.Licence.OPEN_LICENCE,
    ContentItem.Licence.FAIR_DEALING,
    ContentItem.Licence.PERMISSION_HELD,
}


class PublishedByDefault(serializers.BooleanField):
    """On multipart uploads a missing boolean means "not sent", not "false": keep the model default."""

    default_empty_html = True


def role_on(serializer, site: CourseSite) -> str | None:
    """The requester's role on a site, worked out once per response (the context is shared by nested
    serializers)."""
    cache = serializer.context.setdefault("_roles", {})
    if site.id not in cache:
        request = serializer.context.get("request")
        cache[site.id] = site_role(request.user, site) if request is not None else None
    return cache[site.id]


class ReleaseFields(serializers.ModelSerializer):
    """The release conditions shared by modules and items (item 2.16)."""

    conditions = serializers.SerializerMethodField(
        help_text="The release conditions in words; for teaching staff only, null for everyone else"
    )

    def get_conditions(self, obj) -> str | None:
        return release.describe(obj) if role_on(self, obj.site) in TEACHING else None

    def check_release(self, attrs, site: CourseSite, instance=None) -> None:
        required = attrs.get("requires_item")
        if required is not None:
            if required.module.site_id != site.id:
                raise serializers.ValidationError({"requires_item": ["Choose an item on the same course."]})
            if instance is not None and (
                required.pk == instance.pk or release.would_loop(instance, required)
            ):
                raise serializers.ValidationError(
                    {"requires_item": ["This would make items wait for each other, so none would ever open."]}
                )
        for group in attrs.get("groups", []):
            if group.site_id != site.id:
                raise serializers.ValidationError({"groups": ["Choose groups of the same course."]})


class ContentItemSerializer(ReleaseFields):
    module = TaughtRecord(Module, "site")
    is_published = PublishedByDefault(required=False)
    body = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="A page's text: HTML from the editor, cleaned on the server against an allow-list "
        "(courses.richtext), or plain text when body_format is 'text'. An image without alternative text "
        "is refused.",
    )
    body_format = serializers.ChoiceField(
        choices=["html", "text"],
        default="html",
        write_only=True,
        help_text="'text' turns plain text into paragraphs; 'html' (the default) is cleaned as HTML",
    )
    file = serializers.FileField(
        write_only=True,
        required=False,
        help_text="A PDF, a photograph, or a Word, Excel or PowerPoint file without macros; at most "
        "UPLOAD_LIMIT_CONTENT_MB (50 MB by default), within the site's storage allowance",
    )
    filename = serializers.SerializerMethodField(help_text="The name the file had when it was put up")
    download_url = serializers.SerializerMethodField()
    requires_item = TaughtRecord(
        ContentItem,
        "module__site",
        required=False,
        allow_null=True,
        help_text="Hidden from a student until they have completed this item of the same course",
    )
    groups = TaughtRecord(
        SiteGroup, "site", many=True, required=False, help_text="Shown only to members of these groups"
    )
    licence = serializers.ChoiceField(
        choices=ContentItem.Licence.choices,
        required=False,
        help_text="Whose material this is. Required for files and links; pages default to gsa_own",
    )
    completed = serializers.SerializerMethodField(help_text="Whether the requester has completed the item")
    accessibility_issues = serializers.SerializerMethodField(
        help_text="Problems the accessibility check found in the page, after a save; null otherwise"
    )
    storage = serializers.SerializerMethodField(
        help_text="The site's storage use after a file was saved, with a warning from 80%; null otherwise"
    )

    class Meta:
        model = ContentItem
        fields = (
            "id",
            "module",
            "kind",
            "title",
            "body",
            "body_format",
            "file",
            "filename",
            "file_size",
            "download_url",
            "url",
            "position",
            "is_published",
            "available_from",
            "requires_item",
            "groups",
            "conditions",
            "completed",
            "licence",
            "open_licence",
            "source",
            "under_review",
            "accessibility_issues",
            "storage",
        )
        read_only_fields = ("file_size", "under_review")
        extra_kwargs = {"position": {"required": False}}

    def validate_file(self, upload):
        return validate_upload(upload, CONTENT)

    def validate(self, attrs):
        instance = self.instance
        module = attrs.get("module") or instance.module
        site = module.site
        if instance is not None and "module" in attrs and module.site_id != instance.module.site_id:
            raise serializers.ValidationError(
                {"module": ["An item can only move between modules of the same course."]}
            )
        if (
            instance is not None
            and attrs.get("is_published")
            and not instance.is_published
            and release.taken_down(instance)
            and not has_role(self.context["request"].user, *SITE_ADMIN_ROLES)
        ):
            raise serializers.ValidationError(
                {
                    "is_published": [
                        "This item was withdrawn after a takedown request; a course administrator "
                        "must restore it."
                    ]
                }
            )
        kind = attrs.get("kind") or (instance.kind if instance else ContentItem.Kind.PAGE)
        self.check_release(attrs, site, instance)
        self._check_licence(attrs, kind)
        if instance is None and kind == ContentItem.Kind.FILE and not attrs.get("file"):
            raise serializers.ValidationError({"file": ["Choose the file to put up."]})
        if instance is None and kind == ContentItem.Kind.LINK and not attrs.get("url"):
            raise serializers.ValidationError({"url": ["Give the web address the link goes to."]})
        body_format = attrs.pop("body_format", "html")
        if "body" in attrs:
            attrs["body"] = self._checked_body(attrs["body"], body_format, site)
        upload = attrs.get("file")
        if upload:
            freed = instance.file_size if instance is not None else 0
            reason = storage.refusal(site, upload.size, freed)
            if reason:
                raise serializers.ValidationError({"file": [reason]})
        return attrs

    def _check_licence(self, attrs, kind):
        instance = self.instance
        if (
            instance is None
            and kind in (ContentItem.Kind.FILE, ContentItem.Kind.LINK)
            and not attrs.get("licence")
        ):
            raise serializers.ValidationError(
                {
                    "licence": [
                        "Say whose material this is: GSA's own, under an open licence, used under fair "
                        "dealing, or used with permission."
                    ]
                }
            )
        licence = attrs.get("licence") or (instance.licence if instance else ContentItem.Licence.GSA_OWN)
        attrs["licence"] = licence
        which = attrs.get("open_licence", instance.open_licence if instance else "")
        if licence == ContentItem.Licence.OPEN_LICENCE and not which:
            raise serializers.ValidationError(
                {"open_licence": ["Say which open licence: CC BY, CC BY-SA, CC BY-NC, CC0 or another."]}
            )
        if licence != ContentItem.Licence.OPEN_LICENCE:
            attrs["open_licence"] = ""
        source = attrs.get("source", instance.source if instance else "")
        if licence in CREDITED and not (source or "").strip():
            raise serializers.ValidationError(
                {"source": ["Say where the material comes from and how to credit its author."]}
            )

    def _checked_body(self, body: str, body_format: str, site: CourseSite) -> str:
        cleaned = richtext.text_to_html(body) if body_format == "text" else richtext.clean(body)
        issues = richtext.check(cleaned)
        refused = richtext.errors(issues)
        if refused:
            raise serializers.ValidationError({"body": [issue.detail for issue in refused]})
        images = richtext.image_item_ids(cleaned)
        if images and ContentItem.objects.filter(id__in=images, module__site=site).count() != len(images):
            raise serializers.ValidationError(
                {"body": ["A picture on the page is not a file on this course. Put it up here first."]}
            )
        self._issues = [issue.as_dict() for issue in issues]
        return cleaned

    def get_filename(self, obj) -> str | None:
        return (obj.original_name or obj.file.name.rsplit("/", 1)[-1]) if obj.file else None

    def get_download_url(self, obj) -> str | None:
        return f"/api/v1/content/{obj.id}/download/" if obj.file else None

    def get_completed(self, obj) -> bool:
        request = self.context.get("request")
        state = release.state_for(request) if request is not None else None
        return state is not None and obj.id in state.completed

    def get_accessibility_issues(self, obj) -> list[dict] | None:
        return getattr(self, "_issues", None)

    def get_storage(self, obj) -> dict | None:
        return getattr(self, "_storage", None)

    def create(self, validated_data):
        if "position" not in validated_data:
            last = validated_data["module"].items.aggregate(last=Max("position"))["last"] or 0
            validated_data["position"] = last + 1
        return super().create(validated_data)

    def save(self, **kwargs):
        upload = self.validated_data.get("file")
        if upload:
            kwargs["original_name"] = original_name(upload)
            kwargs["file_size"] = upload.size
        item = super().save(**kwargs)
        if upload:
            self._storage = storage.summary(item.module.site)
        return item


class ModuleSerializer(ReleaseFields):
    site = TaughtRecord(CourseSite)
    requires_item = TaughtRecord(
        ContentItem,
        "module__site",
        required=False,
        allow_null=True,
        help_text="Hidden from a student until they have completed this item of the same course",
    )
    groups = TaughtRecord(
        SiteGroup, "site", many=True, required=False, help_text="Shown only to members of these groups"
    )
    items = serializers.SerializerMethodField()

    class Meta:
        model = Module
        fields = (
            "id",
            "site",
            "title",
            "position",
            "available_from",
            "requires_item",
            "groups",
            "conditions",
            "items",
        )
        extra_kwargs = {"position": {"required": False}}

    def validate(self, attrs):
        site = attrs.get("site") or self.instance.site
        self.check_release(attrs, site)
        required = attrs.get("requires_item")
        if required is not None and self.instance is not None and required.module_id == self.instance.pk:
            raise serializers.ValidationError(
                {"requires_item": ["A module cannot wait for one of its own items: it would never open."]}
            )
        return attrs

    def create(self, validated_data):
        if "position" not in validated_data:
            last = validated_data["site"].modules.aggregate(last=Max("position"))["last"] or 0
            validated_data["position"] = last + 1
        return super().create(validated_data)

    def get_items(self, obj) -> list[dict]:
        items = list(obj.items.all())
        role = role_on(self, obj.site)
        if role == Membership.SiteRole.STUDENT:
            state = release.state_for(self.context["request"])
            items = [i for i in items if state is not None and release.item_open(i, state)]
        elif role not in TEACHING:
            items = [i for i in items if i.is_published and not i.under_review]
        return ContentItemSerializer(items, many=True, context=self.context).data


class AnnouncementSerializer(serializers.ModelSerializer):
    site = TaughtRecord(CourseSite)
    author_name = serializers.CharField(source="author.full_name", read_only=True, default=None)

    class Meta:
        model = Announcement
        fields = ("id", "site", "title", "body", "author_name", "created_at")


class SiteSerializer(serializers.ModelSerializer):
    my_role = serializers.SerializerMethodField()
    members = serializers.SerializerMethodField()

    class Meta:
        model = CourseSite
        fields = (
            "id",
            "code",
            "title",
            "term_code",
            "campus_code",
            "source",
            "kind",
            "description",
            "is_published",
            "coursework_weight",
            "storage_allowance_mb",
            "my_role",
            "members",
        )
        read_only_fields = ("source",)
        extra_kwargs = {
            "storage_allowance_mb": {
                "help_text": "Storage for the site's files in megabytes; only a course administrator may set "
                "it. Null means the standard allowance (SITE_STORAGE_ALLOWANCE_MB)"
            }
        }

    def validate(self, attrs):
        request = self.context["request"]
        if "storage_allowance_mb" in attrs and not has_role(request.user, *SITE_ADMIN_ROLES):
            raise PermissionDenied("Only a course administrator can change a site's storage allowance.")
        return attrs

    def get_my_role(self, obj) -> str | None:
        return site_role(self.context["request"].user, obj)

    def get_members(self, obj) -> int:
        return obj.memberships.filter(is_active=True).count()


class OrderSerializer(serializers.Serializer):
    order = serializers.ListField(
        child=serializers.IntegerField(), help_text="Every id, once each, in the order wanted"
    )


class CopySerializer(serializers.Serializer):
    source = TaughtRecord(CourseSite, help_text="The earlier course to copy from; you must teach on it")
    offset_days = serializers.IntegerField(
        required=False, help_text="Move every date by this many days (negative moves them earlier)"
    )
    start_date = serializers.DateField(
        required=False, help_text="Or: move every date so that the earliest falls on this day"
    )
    replace_existing = serializers.BooleanField(
        default=False, help_text="Remove this course's present modules and items first"
    )

    def validate(self, attrs):
        if "offset_days" in attrs and "start_date" in attrs:
            raise serializers.ValidationError("Give either a number of days or a new start date, not both.")
        return attrs


class ShiftSerializer(serializers.Serializer):
    offset_days = serializers.IntegerField(required=False)
    start_date = serializers.DateField(required=False)

    def validate(self, attrs):
        if ("offset_days" in attrs) == ("start_date" in attrs):
            raise serializers.ValidationError("Give either a number of days or a new start date.")
        return attrs


class DateSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["module", "item", "assignment"])
    id = serializers.IntegerField()
    title = serializers.CharField(read_only=True)
    field = serializers.ChoiceField(choices=["available_from", "opens_at", "due_at"])
    value = serializers.DateTimeField(allow_null=True)


class DateChangesSerializer(serializers.Serializer):
    changes = DateSerializer(many=True)


class StorageSerializer(serializers.Serializer):
    used_bytes = serializers.IntegerField()
    allowance_bytes = serializers.IntegerField()
    percent = serializers.FloatField()
    warning = serializers.CharField(allow_null=True)
    largest_files = serializers.ListField(child=serializers.DictField(), required=False)


class TemplateChoiceSerializer(serializers.Serializer):
    template = serializers.PrimaryKeyRelatedField(
        queryset=SiteTemplate.objects.all(), required=False, help_text="The default template when left out"
    )


def require_teaching(user, site: CourseSite) -> None:
    if not can_teach(user, site):
        raise PermissionDenied("Only the site's teaching staff can do this.")


def renumber(rows, order: list[int], what: str) -> dict:
    """Give rows the positions 1.. in the order of the ids sent, which must be every row once."""
    by_id = {row.id: row for row in rows}
    if sorted(order) != sorted(by_id) or len(set(order)) != len(order):
        raise serializers.ValidationError({"order": [f"Send every {what} id once each: {sorted(by_id)}."]})
    before = {row.id: row.position for row in rows}
    for position, pk in enumerate(order, start=1):
        if by_id[pk].position != position:
            by_id[pk].position = position
            by_id[pk].save(update_fields=["position", "updated_at"])
    return before


class SiteViewSet(viewsets.ModelViewSet):
    serializer_class = SiteSerializer
    permission_classes = [RolePermission]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = visible_sites(self.request.user)
        term = self.request.query_params.get("term")
        return qs.filter(term_code=term) if term else qs

    def get_serializer_class(self):
        return {
            "reorder_modules": OrderSerializer,
            "copy_from": CopySerializer,
            "shift_dates": ShiftSerializer,
            "apply_template": TemplateChoiceSerializer,
        }.get(self.action, SiteSerializer)

    def create(self, request, *args, **kwargs):
        # Who may write is settled before anything sent is looked at (item 1.15).
        if not has_role(request.user, *SITE_ADMIN_ROLES):
            raise PermissionDenied("Only course administrators create sites.")
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not can_teach(request.user, self.get_object()):
            raise PermissionDenied("Only the site's teaching staff can change it.")
        return super().update(request, *args, **kwargs)

    def perform_create(self, serializer):
        if not has_role(self.request.user, *SITE_ADMIN_ROLES):
            raise PermissionDenied("Only course administrators create sites.")
        with transaction.atomic():
            site = serializer.save(
                source=CourseSite.Source.LOCAL, created_by=self.request.user, updated_by=self.request.user
            )
            record(self.request, "create", site, after=snapshot(site))
            site_templates.apply_template(site, request=self.request)  # item 2.17

    def perform_update(self, serializer):
        if not can_teach(self.request.user, serializer.instance):
            raise PermissionDenied("Only the site's teaching staff can change it.")
        with transaction.atomic():
            before = snapshot(serializer.instance)
            site = serializer.save(updated_by=self.request.user)
            record(self.request, "update", site, before=before, after=snapshot(site))

    def _taught_site(self) -> CourseSite:
        """The site in the address, which the caller must teach on: settled before the body is read."""
        site = self.get_object()
        require_teaching(self.request.user, site)
        return site

    @action(detail=True, methods=["get"])
    def contents(self, request, pk=None):
        site = self.get_object()
        modules = site.modules.prefetch_related("items__groups", "items__requires_item", "groups")
        hidden = release.hidden_modules(request, site.modules.all())
        modules = [m for m in modules if m.id not in hidden]
        context = {"request": request}
        return Response(
            {
                "site": SiteSerializer(site, context=context).data,
                "modules": ModuleSerializer(modules, many=True, context=context).data,
                "announcements": AnnouncementSerializer(site.announcements.all()[:20], many=True).data,
            }
        )

    @action(detail=True, methods=["get"])
    def members(self, request, pk=None):
        site = self.get_object()
        if site_role(request.user, site) not in (ADMIN, "lecturer", "assistant", "auditor"):
            raise PermissionDenied("Only teaching staff can see the class list.")
        rows = (
            site.memberships.filter(is_active=True)
            .select_related("person")
            .order_by("role", "person__last_name")
        )
        return Response(
            [
                {
                    "membership_id": m.id,
                    "person_id": m.person_id,
                    "external_id": m.person.external_id,
                    "name": m.person.full_name,
                    "role": m.role,
                }
                for m in rows
            ]
        )

    @extend_schema(
        request=OrderSerializer,
        responses={
            200: OrderSerializer,
            400: OpenApiTypes.OBJECT,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
        summary="Put the site's modules in a new order (item 2.15)",
    )
    @action(detail=True, methods=["post"], url_path="reorder-modules")
    def reorder_modules(self, request, pk=None):
        site = self._taught_site()
        data = OrderSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        order = data.validated_data["order"]
        with transaction.atomic():
            before = renumber(list(site.modules.select_for_update()), order, "module")
            record(request, "reorder", site, before={"modules": before}, after={"modules": order})
        return Response({"order": order})

    @extend_schema(
        request=TemplateChoiceSerializer,
        responses={
            200: inline_serializer("TemplateApplied", {"modules": serializers.IntegerField()}),
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
        summary="Give an empty site a course template's modules and draft pages (item 2.17)",
    )
    @action(detail=True, methods=["post"], url_path="apply-template")
    def apply_template(self, request, pk=None):
        site = self._taught_site()
        data = TemplateChoiceSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        template = data.validated_data.get("template") or site_templates.default_template()
        if template is None:
            return Response({"code": "no_template", "detail": "There is no course template yet."}, status=409)
        if site.modules.exists():
            return Response(
                {
                    "code": "not_empty",
                    "detail": "A template can only be applied to a course with no modules.",
                },
                status=409,
            )
        return Response({"modules": site_templates.apply_template(site, template, request=request)})

    @extend_schema(
        request=CopySerializer,
        responses={
            200: inline_serializer(
                "CopyDone",
                {
                    "modules": serializers.IntegerField(),
                    "items": serializers.IntegerField(),
                    "assignments": serializers.IntegerField(),
                    "offset_days": serializers.IntegerField(),
                    "missing_files": serializers.ListField(child=serializers.CharField()),
                    "left_out": serializers.ListField(child=serializers.CharField()),
                },
            ),
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
        summary="Copy an earlier course's content into this one and move every date (item 2.18)",
        description="Copies modules, items (files as new stored copies), release dates and assignments. "
        "Never people, groups, submissions, marks, completions or announcements.",
    )
    @action(detail=True, methods=["post"], url_path="copy-from")
    def copy_from(self, request, pk=None):
        site = self._taught_site()
        data = CopySerializer(data=request.data, context={"request": request})
        data.is_valid(raise_exception=True)
        source = data.validated_data["source"]
        if "start_date" in data.validated_data:
            offset = copying.offset_to(source, data.validated_data["start_date"])
        else:
            offset = timedelta(days=data.validated_data.get("offset_days", 0))
        try:
            summary = copying.copy_content(
                source, site, offset, request, replace=data.validated_data["replace_existing"]
            )
        except copying.CopyRefused as refused:
            return Response({"code": "copy_refused", "detail": str(refused)}, status=409)
        return Response(summary)

    @extend_schema(
        methods=["GET"],
        responses={200: DateSerializer(many=True), 403: ErrorSerializer, 404: ErrorSerializer},
        summary="Every date on the site: when modules and items are shown, when assignments open and are due",
    )
    @extend_schema(
        methods=["PATCH"],
        request=DateChangesSerializer,
        responses={200: DateSerializer(many=True), 400: ErrorSerializer, 403: ErrorSerializer},
        summary="Change many of the site's dates at once; all or nothing (item 2.18)",
    )
    @action(detail=True, methods=["get", "patch"])
    def dates(self, request, pk=None):
        site = self._taught_site()
        if request.method == "PATCH":
            data = DateChangesSerializer(data=request.data)
            data.is_valid(raise_exception=True)
            try:
                copying.update_dates(site, data.validated_data["changes"], request)
            except ValueError as refused:
                return Response({"code": "invalid_date", "detail": str(refused)}, status=400)
        return Response(DateSerializer(copying.dated_things(site), many=True).data)

    @extend_schema(
        request=ShiftSerializer,
        responses={200: DateSerializer(many=True), 400: OpenApiTypes.OBJECT, 403: ErrorSerializer},
        summary="Move every date on the site by a number of days, or so the earliest falls on a new day",
    )
    @action(detail=True, methods=["post"], url_path="shift-dates")
    def shift_dates(self, request, pk=None):
        site = self._taught_site()
        data = ShiftSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        if "start_date" in data.validated_data:
            offset = copying.offset_to(site, data.validated_data["start_date"])
        else:
            offset = timedelta(days=data.validated_data["offset_days"])
        copying.shift_dates(site, offset, request)
        return Response(DateSerializer(copying.dated_things(site), many=True).data)

    @extend_schema(
        responses={200: StorageSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
        summary="The site's storage use and allowance, and its largest files for housekeeping (item 2.20)",
    )
    @action(detail=True, methods=["get"])
    def storage(self, request, pk=None):
        site = self._taught_site()
        files = [
            {
                "id": item.id,
                "title": item.title,
                "module": item.module.title,
                "filename": item.original_name,
                "file_size": item.file_size,
            }
            for item in storage.largest_files(site)
        ]
        return Response({**storage.summary(site), "largest_files": files})


class TeachingViewSet(viewsets.ModelViewSet):
    """Base for objects that belong to a site and are managed by its teaching staff.

    Every write settles the site first (item 1.15): a record, or a site named by id, that the caller cannot
    open reads as unknown (404, or "does not exist" for an id in the body, see courses.access.TaughtRecord),
    and a site they can open but do not teach on is refused, before any other field is looked at.
    """

    permission_classes = [RolePermission]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def site_of(self, instance) -> CourseSite:
        raise NotImplementedError

    def site_from_data(self, data) -> CourseSite:
        raise NotImplementedError

    def _require_teaching(self, site: CourseSite) -> None:
        require_teaching(self.request.user, site)

    def update(self, request, *args, **kwargs):
        self._require_teaching(self.site_of(self.get_object()))
        return super().update(request, *args, **kwargs)

    def perform_create(self, serializer):
        self._require_teaching(self.site_from_data(serializer.validated_data))
        with transaction.atomic():
            instance = serializer.save(created_by=self.request.user, updated_by=self.request.user)
            record(self.request, "create", instance, after=snapshot(instance))

    def perform_update(self, serializer):
        self._require_teaching(self.site_of(serializer.instance))
        with transaction.atomic():
            before = snapshot(serializer.instance)
            instance = serializer.save(updated_by=self.request.user)
            record(self.request, "update", instance, before=before, after=snapshot(instance))

    def perform_destroy(self, instance):
        self._require_teaching(self.site_of(instance))
        with transaction.atomic():
            before, entity_id = snapshot(instance), instance.pk
            instance.delete()
            record(self.request, "delete", instance, before=before, entity_id=entity_id)


class ModuleViewSet(TeachingViewSet):
    serializer_class = ModuleSerializer

    def get_queryset(self):
        modules = Module.objects.filter(site__in=visible_sites(self.request.user))
        hidden = release.hidden_modules(self.request, modules)
        modules = modules.exclude(id__in=hidden) if hidden else modules
        return modules.select_related("site").prefetch_related("items__groups", "groups")

    def site_of(self, instance):
        return instance.site

    def site_from_data(self, data):
        return data["site"]

    @extend_schema(
        request=OrderSerializer,
        responses={
            200: OrderSerializer,
            400: OpenApiTypes.OBJECT,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
        summary="Put the module's items in a new order (item 2.15)",
    )
    @action(detail=True, methods=["post"], url_path="reorder-items")
    def reorder_items(self, request, pk=None):
        module = self.get_object()
        self._require_teaching(module.site)
        data = OrderSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        order = data.validated_data["order"]
        with transaction.atomic():
            before = renumber(list(module.items.select_for_update()), order, "item")
            record(request, "reorder", module, before={"items": before}, after={"items": order})
        return Response({"order": order})


class MoveSerializer(serializers.Serializer):
    module = TaughtRecord(Module, "site", help_text="A module of the same course")
    position = serializers.IntegerField(
        min_value=1, required=False, help_text="Place in the module, from 1; the end when left out"
    )


class ReportSerializer(serializers.Serializer):
    reason = serializers.CharField(help_text="Why the item should not be on the course")


class CheckPageSerializer(serializers.Serializer):
    body = serializers.CharField(allow_blank=True)
    body_format = serializers.ChoiceField(choices=["html", "text"], default="html")


class CheckedPageSerializer(serializers.Serializer):
    body = serializers.CharField(help_text="The body as it would be saved")
    issues = serializers.ListField(
        child=serializers.DictField(),
        help_text="Each problem: code, detail, and severity ('error' refuses the save, 'warning' does not)",
    )


class TakedownSerializer(serializers.ModelSerializer):
    item_title = serializers.CharField(source="item.title", read_only=True)
    site = serializers.IntegerField(source="item.module.site_id", read_only=True)

    class Meta:
        model = TakedownRequest
        fields = (
            "id",
            "item",
            "item_title",
            "site",
            "reason",
            "status",
            "created_at",
            "reviewed_at",
            "review_note",
        )
        read_only_fields = fields


class ContentItemViewSet(TeachingViewSet):
    serializer_class = ContentItemSerializer

    def get_queryset(self):
        """Published items on the sites the user can open, and drafts only where they teach: a draft is
        unknown to everyone else. A student does not see an item until its release conditions are met,
        nor one under review for takedown."""
        user = self.request.user
        items = ContentItem.objects.filter(module__site__in=visible_sites(user))
        items = items.select_related("module__site", "requires_item").prefetch_related("groups")
        items = items.filter(is_published=True) | items.filter(module__site__in=taught_sites(user))
        hidden = release.hidden_items(self.request, items)
        return items.exclude(id__in=hidden) if hidden else items

    def get_serializer_class(self):
        return {
            "move": MoveSerializer,
            "report": ReportSerializer,
            "check_page": CheckPageSerializer,
        }.get(self.action, ContentItemSerializer)

    def site_of(self, instance):
        return instance.module.site

    def site_from_data(self, data):
        return data["module"].site

    def _complete(self, item: ContentItem, how: str) -> None:
        """Record a student's progress through the item; anyone else's viewing records nothing."""
        person = person_of(self.request.user)
        if person is None or site_role(self.request.user, item.module.site) != Membership.SiteRole.STUDENT:
            return
        completion, created = release.complete(person, item, how)
        if created:
            record(self.request, "create", completion, after=snapshot(completion))
            state = release.state_for(self.request)  # already read for this request: keep it true
            if state is not None:
                state.completed.add(item.id)

    def retrieve(self, request, *args, **kwargs):
        item = self.get_object()
        if item.kind == ContentItem.Kind.PAGE:
            self._complete(item, ItemCompletion.How.VIEWED)  # opening a page completes it (item 2.16)
        return Response(self.get_serializer(item).data)

    @extend_schema(responses={(200, "application/octet-stream"): OpenApiTypes.BINARY, 404: ErrorSerializer})
    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        item = get_object_or_404(self.get_queryset(), pk=pk)
        if not item.file:
            return Response({"code": "no_file", "detail": "This item has no file."}, status=404)
        record(request, "download", item, after={"title": item.title})
        self._complete(item, ItemCompletion.How.DOWNLOADED)
        return FileResponse(
            item.file.open("rb"),
            as_attachment=True,
            filename=item.original_name or item.file.name.rsplit("/", 1)[-1],
        )

    @extend_schema(
        request=None,
        responses={200: ContentItemSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
        summary="Mark an item complete, for a student of the course (item 2.16)",
    )
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        item = self.get_object()
        if site_role(request.user, item.module.site) != Membership.SiteRole.STUDENT:
            raise PermissionDenied("Only students of this course record their progress.")
        self._complete(item, ItemCompletion.How.MARKED)
        return Response(ContentItemSerializer(item, context=self.get_serializer_context()).data)

    @extend_schema(
        request=None,
        responses={
            201: ContentItemSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
        summary="Copy an item, placed after it as a draft; a file is copied as a new stored file (item 2.15)",
    )
    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        item = self.get_object()
        site = item.module.site
        self._require_teaching(site)
        if release.taken_down(item):
            return Response(
                {
                    "code": "taken_down",
                    "detail": "This item is under review or was withdrawn after a takedown request, so it "
                    "cannot be copied.",
                },
                status=409,
            )
        with transaction.atomic():
            if item.file:
                storage.require_room(site, item.file_size)
            item.module.items.filter(position__gt=item.position).update(position=F("position") + 1)
            groups = list(item.groups.all())
            copy = ContentItem.objects.get(pk=item.pk)
            copy.pk = copy.id = None
            copy.title = f"Copy of {item.title}"[:160]
            copy.position = item.position + 1
            copy.is_published = False
            copy.under_review = False
            copy.created_by = copy.updated_by = request.user
            if item.file:
                with item.file.open("rb") as handle:
                    copy.file.save(item.original_name or item.file.name, File(handle), save=False)
            copy.save()
            copy.groups.set(groups)
            record(request, "create", copy, after={**snapshot(copy), "copied_from": item.id})
        serializer = ContentItemSerializer(copy, context=self.get_serializer_context())
        if item.file:
            serializer._storage = storage.summary(site)
        return Response(serializer.data, status=201)

    @extend_schema(
        request=MoveSerializer,
        responses={
            200: ContentItemSerializer,
            400: OpenApiTypes.OBJECT,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
        summary="Move an item to another module of the same course, or to another place (item 2.15)",
    )
    @action(detail=True, methods=["post"])
    def move(self, request, pk=None):
        item = self.get_object()
        self._require_teaching(item.module.site)
        data = MoveSerializer(data=request.data, context=self.get_serializer_context())
        data.is_valid(raise_exception=True)
        target = data.validated_data["module"]
        if target.site_id != item.module.site_id:
            raise serializers.ValidationError(
                {"module": ["An item can only move between modules of the same course."]}
            )
        with transaction.atomic():
            before = snapshot(item)
            source = item.module
            rest = [i.id for i in target.items.exclude(pk=item.pk).order_by("position", "id")]
            place = min(data.validated_data.get("position", len(rest) + 1), len(rest) + 1)
            rest.insert(place - 1, item.id)
            item.module = target
            item.updated_by = request.user
            item.save()
            renumber(list(target.items.all()), rest, "item")
            if source.pk != target.pk:
                renumber(
                    list(source.items.all()), [i.id for i in source.items.order_by("position", "id")], "item"
                )
            item.refresh_from_db()
            record(request, "update", item, before=before, after=snapshot(item))
        return Response(ContentItemSerializer(item, context=self.get_serializer_context()).data)

    @extend_schema(
        request=ReportSerializer,
        responses={201: TakedownSerializer, 400: OpenApiTypes.OBJECT, 404: ErrorSerializer},
        summary="Ask for an item to be taken down; it is hidden from students until reviewed (item 2.19)",
    )
    @action(detail=True, methods=["post"])
    def report(self, request, pk=None):
        item = self.get_object()
        data = ReportSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            takedown = TakedownRequest.objects.create(
                item=item,
                reported_by=request.user,
                reason=data.validated_data["reason"],
                created_by=request.user,
                updated_by=request.user,
            )
            record(request, "create", takedown, after=snapshot(takedown))
            if not item.under_review:
                before = snapshot(item)
                item.under_review = True
                item.save(update_fields=["under_review", "updated_at"])
                record(request, "update", item, before=before, after=snapshot(item))
        return Response(TakedownSerializer(takedown).data, status=201)

    @extend_schema(
        request=CheckPageSerializer,
        responses={200: CheckedPageSerializer, 403: ErrorSerializer},
        summary="Clean a page body and check it for accessibility problems, without saving (item 2.13)",
    )
    @action(detail=False, methods=["post"], url_path="check-page")
    def check_page(self, request):
        if not taught_sites(request.user).exists():
            raise PermissionDenied("Only teaching staff write pages.")
        data = CheckPageSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        body = data.validated_data["body"]
        if data.validated_data["body_format"] == "text":
            body = richtext.text_to_html(body)
        else:
            body = richtext.clean(body)
        return Response({"body": body, "issues": [issue.as_dict() for issue in richtext.check(body)]})


class AnnouncementViewSet(TeachingViewSet):
    serializer_class = AnnouncementSerializer

    def get_queryset(self):
        qs = Announcement.objects.filter(site__in=visible_sites(self.request.user)).select_related("author")
        site = self.request.query_params.get("site")
        return qs.filter(site_id=site) if site else qs

    def site_of(self, instance):
        return instance.site

    def site_from_data(self, data):
        return data["site"]

    def perform_create(self, serializer):
        site = serializer.validated_data["site"]
        self._require_teaching(site)
        with transaction.atomic():
            instance = serializer.save(
                author=person_of(self.request.user),
                created_by=self.request.user,
                updated_by=self.request.user,
            )
            record(self.request, "create", instance, after=snapshot(instance))
            self._notify(instance)

    @staticmethod
    def _notify(announcement):
        from notifications.services import notify

        students = Membership.objects.filter(
            site=announcement.site,
            is_active=True,
            role=Membership.SiteRole.STUDENT,
            person__user__isnull=False,
        ).select_related("person__user")
        notify(
            [m.person.user for m in students],
            title=f"{announcement.site.code}: {announcement.title}",
            body=announcement.body[:500],
            link=f"/sites/{announcement.site_id}",
            dedupe_key=f"announcement:{announcement.id}",
        )


class SiteGroupSerializer(serializers.ModelSerializer):
    site = TaughtRecord(CourseSite)
    members = serializers.PrimaryKeyRelatedField(
        many=True,
        required=False,
        queryset=Membership.objects.all(),
        help_text="Membership ids (from the site's members list) of the people in the group",
    )

    class Meta:
        model = SiteGroup
        fields = ("id", "site", "name", "members")

    def validate(self, attrs):
        site = attrs.get("site") or self.instance.site
        if self.instance is not None and "site" in attrs and attrs["site"].pk != self.instance.site_id:
            raise serializers.ValidationError({"site": ["A group stays on its course."]})
        if any(m.site_id != site.id for m in attrs.get("members", [])):
            raise serializers.ValidationError({"members": ["Choose members of this course."]})
        name = attrs.get("name")
        if (
            name
            and SiteGroup.objects.filter(site=site, name=name)
            .exclude(pk=getattr(self.instance, "pk", None))
            .exists()
        ):
            raise serializers.ValidationError({"name": ["The course already has a group with this name."]})
        return attrs


class SiteGroupViewSet(TeachingViewSet):
    """Groups of a site's members, for releasing content to some of the class. Teaching staff only."""

    serializer_class = SiteGroupSerializer

    def get_queryset(self):
        qs = SiteGroup.objects.filter(site__in=taught_sites(self.request.user)).prefetch_related("members")
        site = self.request.query_params.get("site")
        return qs.filter(site_id=site) if site else qs

    def site_of(self, instance):
        return instance.site

    def site_from_data(self, data):
        return data["site"]


class SiteTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteTemplate
        fields = ("id", "name", "description", "structure", "is_default")

    def validate_structure(self, value):
        problem = (
            'Give {"modules": [{"title": ..., "items": [{"kind": "page", "title": ..., "body": ...}]}]}.'
        )
        modules = value.get("modules") if isinstance(value, dict) else None
        if not isinstance(modules, list) or not modules:
            raise serializers.ValidationError(problem)
        for module in modules:
            if not isinstance(module, dict) or not str(module.get("title", "")).strip():
                raise serializers.ValidationError(problem)
            for item in module.get("items", []):
                if not isinstance(item, dict) or item.get("kind", "page") != "page" or not item.get("title"):
                    raise serializers.ValidationError("A template holds pages only, each with a title.")
                if richtext.errors(richtext.check(richtext.clean(item.get("body", "")))):
                    raise serializers.ValidationError(f"The page “{item['title']}” has an image problem.")
        return value


class SiteTemplateViewSet(viewsets.ModelViewSet):
    """Course templates. Anyone signed in may read them; course administrators manage them."""

    serializer_class = SiteTemplateSerializer
    permission_classes = [RolePermission]
    write_roles = SITE_ADMIN_ROLES
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    queryset = SiteTemplate.objects.all()

    def _save(self, serializer, action_name):
        with transaction.atomic():
            before = snapshot(serializer.instance) if serializer.instance else None
            stamps = {"updated_by": self.request.user}
            if serializer.instance is None:
                stamps["created_by"] = self.request.user
            template = serializer.save(**stamps)
            if template.is_default:
                SiteTemplate.objects.exclude(pk=template.pk).filter(is_default=True).update(is_default=False)
            record(self.request, action_name, template, before=before, after=snapshot(template))

    def perform_create(self, serializer):
        self._save(serializer, "create")

    def perform_update(self, serializer):
        self._save(serializer, "update")

    def perform_destroy(self, instance):
        with transaction.atomic():
            before, entity_id = snapshot(instance), instance.pk
            instance.delete()
            record(self.request, "delete", instance, before=before, entity_id=entity_id)


class ReviewSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(
        choices=["withdraw", "restore"],
        help_text="withdraw: the item is unpublished; restore: it is shown again",
    )
    note = serializers.CharField(required=False, allow_blank=True)


class TakedownViewSet(viewsets.ReadOnlyModelViewSet):
    """Takedown requests: course administrators see and decide all; anyone else sees their own."""

    serializer_class = TakedownSerializer
    permission_classes = [RolePermission]
    queryset = TakedownRequest.objects.none()  # for the schema; get_queryset decides

    def get_queryset(self):
        qs = TakedownRequest.objects.select_related("item__module")
        if has_role(self.request.user, *SITE_ADMIN_ROLES):
            status = self.request.query_params.get("status")
            return qs.filter(status=status) if status else qs
        return qs.filter(reported_by=self.request.user)

    @extend_schema(
        request=ReviewSerializer,
        responses={200: TakedownSerializer, 403: ErrorSerializer, 404: ErrorSerializer, 409: ErrorSerializer},
        summary="Decide a takedown request: withdraw the item or restore it (course administrators)",
    )
    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        if not has_role(request.user, *SITE_ADMIN_ROLES):
            raise PermissionDenied("Only a course administrator decides takedown requests.")
        takedown = self.get_object()
        if takedown.status != TakedownRequest.Status.OPEN:
            return Response(
                {"code": "already_decided", "detail": "This request has been decided."}, status=409
            )
        data = ReviewSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        withdraw = data.validated_data["decision"] == "withdraw"
        with transaction.atomic():
            before = snapshot(takedown)
            takedown.status = (
                TakedownRequest.Status.WITHDRAWN if withdraw else TakedownRequest.Status.RESTORED
            )
            takedown.reviewed_by = request.user
            takedown.reviewed_at = timezone.now()
            takedown.review_note = data.validated_data.get("note", "")
            takedown.updated_by = request.user
            takedown.save()
            record(request, "review", takedown, before=before, after=snapshot(takedown))
            item = takedown.item
            item_before = snapshot(item)
            if withdraw:
                item.is_published = False
                TakedownRequest.objects.filter(item=item, status=TakedownRequest.Status.OPEN).update(
                    status=TakedownRequest.Status.WITHDRAWN,
                    reviewed_by=request.user,
                    reviewed_at=takedown.reviewed_at,
                )
            if not item.takedowns.filter(status=TakedownRequest.Status.OPEN).exists():
                item.under_review = False
            item.updated_by = request.user
            item.save()
            record(request, "update", item, before=item_before, after=snapshot(item))
        return Response(TakedownSerializer(takedown).data)


router = DefaultRouter()
router.register("sites", SiteViewSet, basename="site")
router.register("modules", ModuleViewSet, basename="module")
router.register("content", ContentItemViewSet, basename="content")
router.register("announcements", AnnouncementViewSet, basename="announcement")
router.register("groups", SiteGroupViewSet, basename="group")
router.register("site-templates", SiteTemplateViewSet, basename="site-template")
router.register("takedowns", TakedownViewSet, basename="takedown")
urlpatterns = router.urls
