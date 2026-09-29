"""Course sites, modules, content, announcements. Students see published material only."""

from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from audit.services import record, snapshot
from courses.access import ADMIN, can_teach, person_of, site_role, visible_sites
from courses.models import Announcement, ContentItem, CourseSite, Membership, Module
from iam.permissions import RolePermission
from iam.services import SITE_ADMIN_ROLES, has_role


class PublishedByDefault(serializers.BooleanField):
    """On multipart uploads a missing boolean means "not sent", not "false": keep the model default."""

    default_empty_html = True


class ContentItemSerializer(serializers.ModelSerializer):
    is_published = PublishedByDefault(required=False)
    file = serializers.FileField(write_only=True, required=False)
    filename = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = ContentItem
        fields = (
            "id",
            "module",
            "kind",
            "title",
            "body",
            "file",
            "filename",
            "download_url",
            "url",
            "position",
            "is_published",
        )

    def get_filename(self, obj):
        return obj.file.name.rsplit("/", 1)[-1] if obj.file else None

    def get_download_url(self, obj):
        return f"/api/v1/content/{obj.id}/download/" if obj.file else None


class ModuleSerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField()

    class Meta:
        model = Module
        fields = ("id", "site", "title", "position", "items")

    def get_items(self, obj):
        items = obj.items.all()
        if not self.context.get("teaching", False):
            items = [i for i in items if i.is_published]
        return ContentItemSerializer(items, many=True).data


class AnnouncementSerializer(serializers.ModelSerializer):
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
            "my_role",
            "members",
        )
        read_only_fields = ("source",)

    def get_my_role(self, obj):
        return site_role(self.context["request"].user, obj)

    def get_members(self, obj):
        return obj.memberships.filter(is_active=True).count()


class SiteViewSet(viewsets.ModelViewSet):
    serializer_class = SiteSerializer
    permission_classes = [RolePermission]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = visible_sites(self.request.user)
        term = self.request.query_params.get("term")
        return qs.filter(term_code=term) if term else qs

    def perform_create(self, serializer):
        if not has_role(self.request.user, *SITE_ADMIN_ROLES):
            raise PermissionDenied("Only course administrators create sites.")
        with transaction.atomic():
            site = serializer.save(
                source=CourseSite.Source.LOCAL, created_by=self.request.user, updated_by=self.request.user
            )
            record(self.request, "create", site, after=snapshot(site))

    def perform_update(self, serializer):
        if not can_teach(self.request.user, serializer.instance):
            raise PermissionDenied("Only the site's teaching staff can change it.")
        with transaction.atomic():
            before = snapshot(serializer.instance)
            site = serializer.save(updated_by=self.request.user)
            record(self.request, "update", site, before=before, after=snapshot(site))

    @action(detail=True, methods=["get"])
    def contents(self, request, pk=None):
        site = self.get_object()
        teaching = can_teach(request.user, site)
        modules = site.modules.prefetch_related("items")
        return Response(
            {
                "site": SiteSerializer(site, context={"request": request}).data,
                "modules": ModuleSerializer(modules, many=True, context={"teaching": teaching}).data,
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
                    "person_id": m.person_id,
                    "external_id": m.person.external_id,
                    "name": m.person.full_name,
                    "role": m.role,
                }
                for m in rows
            ]
        )


class TeachingViewSet(viewsets.ModelViewSet):
    """Base for objects that belong to a site and are managed by its teaching staff."""

    permission_classes = [RolePermission]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def site_of(self, instance) -> CourseSite:
        raise NotImplementedError

    def site_from_data(self, data) -> CourseSite:
        raise NotImplementedError

    def _require_teaching(self, site: CourseSite) -> None:
        if not can_teach(self.request.user, site):
            raise PermissionDenied("Only the site's teaching staff can do this.")

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

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "teaching": True}

    def get_queryset(self):
        return Module.objects.filter(site__in=visible_sites(self.request.user)).prefetch_related("items")

    def site_of(self, instance):
        return instance.site

    def site_from_data(self, data):
        return data["site"]


class ContentItemViewSet(TeachingViewSet):
    serializer_class = ContentItemSerializer

    def get_queryset(self):
        return ContentItem.objects.filter(module__site__in=visible_sites(self.request.user))

    def site_of(self, instance):
        return instance.module.site

    def site_from_data(self, data):
        return data["module"].site

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        item = get_object_or_404(self.get_queryset(), pk=pk)
        site = item.module.site
        role = site_role(request.user, site)
        if role is None or (not item.is_published and not can_teach(request.user, site)):
            raise PermissionDenied("You cannot open this file.")
        if not item.file:
            return Response({"code": "no_file", "detail": "This item has no file."}, status=404)
        record(request, "download", item, after={"title": item.title})
        return FileResponse(
            item.file.open("rb"), as_attachment=True, filename=item.file.name.rsplit("/", 1)[-1]
        )


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


router = DefaultRouter()
router.register("sites", SiteViewSet, basename="site")
router.register("modules", ModuleViewSet, basename="module")
router.register("content", ContentItemViewSet, basename="content")
router.register("announcements", AnnouncementViewSet, basename="announcement")
urlpatterns = router.urls
