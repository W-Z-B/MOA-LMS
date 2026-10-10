"""Registering outside tools and placing them on course sites (item 6.07), under /api/v1/.

Course administrators register tools and decide, tool by tool, whether it may receive names and email
addresses (off by default). Teaching staff place registered tools in their modules, set how a tool's
gradebook column counts, and see what each tool receives about their students.
"""

from decimal import Decimal

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.urls import path
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from assessments.models import GradeCategory
from audit.services import record, snapshot
from core import outbound
from core.serializers import ErrorSerializer
from courses import release
from courses.access import TaughtRecord, can_teach, taught_sites, visible_sites
from courses.models import ContentItem, Module
from iam.permissions import RolePermission
from iam.services import SITE_ADMIN_ROLES, has_role
from lti import keys, services
from lti.models import LineItem, Placement, Tool


def _secure(url: str) -> str:
    if url and not services._https(url):
        raise serializers.ValidationError("Use a secure address, starting https://.")
    return url


class ToolSerializer(serializers.ModelSerializer):
    receives = serializers.SerializerMethodField(help_text="What the tool receives about people, in words")
    can_choose_content = serializers.SerializerMethodField(help_text="Whether it offers content to choose")

    class Meta:
        model = Tool
        fields = (
            "id",
            "name",
            "description",
            "client_id",
            "deployment_id",
            "oidc_login_url",
            "launch_url",
            "deep_linking_url",
            "redirect_urls",
            "jwks_url",
            "public_key",
            "share_name",
            "share_email",
            "grades",
            "class_list",
            "is_active",
            "receives",
            "can_choose_content",
        )
        read_only_fields = ("client_id",)

    def get_receives(self, obj) -> list[str]:
        return receives(obj)

    def get_can_choose_content(self, obj) -> bool:
        return bool(obj.deep_linking_url)

    def validate_oidc_login_url(self, value):
        return _secure(value)

    def validate_launch_url(self, value):
        return _secure(value)

    def validate_deep_linking_url(self, value):
        return _secure(value)

    def validate_jwks_url(self, value):
        """The server fetches this address itself, so it may not name a private network (ASVS 5.2.6)."""
        if value and outbound.plainly_private(value):
            raise serializers.ValidationError("Give the tool's public key set address, not a private one.")
        return _secure(value)

    def validate_redirect_urls(self, value):
        return [_secure(u) for u in value]

    def validate_public_key(self, value):
        if value.strip():
            try:
                keys.parse_public_key(value)
            except ValueError as error:
                raise serializers.ValidationError(str(error)) from error
        return value.strip()

    def validate(self, attrs):
        jwks_url = attrs.get("jwks_url", getattr(self.instance, "jwks_url", ""))
        public_key = attrs.get("public_key", getattr(self.instance, "public_key", ""))
        if not jwks_url and not public_key:
            raise serializers.ValidationError(
                {"jwks_url": ["Give the tool's key set address, or paste its public key."]}
            )
        return attrs

    def to_representation(self, obj):
        data = super().to_representation(obj)
        request = self.context.get("request")
        if request is not None and not has_role(request.user, *SITE_ADMIN_ROLES):
            # Teaching staff choose tools and see what each receives; the registration is not theirs.
            for name in ("client_id", "deployment_id", "redirect_urls", "jwks_url", "public_key"):
                data.pop(name, None)
        return data


def receives(tool: Tool) -> list[str]:
    said = [
        "An identifier for each person that means nothing outside this tool",
        "Each person's role on the course (student, lecturer or teaching assistant)",
        "The course code and title",
    ]
    if tool.share_name:
        said.append("Each person's name")
    if tool.share_email:
        said.append("Each person's email address")
    if tool.grades:
        said.append("May post scores to the gradebook")
    if tool.class_list:
        said.append("May read the class list (the same details, for everyone on the course)")
    return said


def _teaches_anywhere(user) -> bool:
    return taught_sites(user).exists()


@extend_schema_view(
    list=extend_schema(
        summary="Registered tools: all for course administrators, active ones for teaching staff"
    ),
    create=extend_schema(summary="Register a tool (course administrators)"),
    partial_update=extend_schema(summary="Change a tool's registration or its data sharing"),
    destroy=extend_schema(summary="Remove a tool that is not placed on any course"),
)
class ToolViewSet(viewsets.ModelViewSet):
    permission_classes = [RolePermission]
    write_roles = SITE_ADMIN_ROLES
    serializer_class = ToolSerializer
    queryset = Tool.objects.none()
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        if has_role(user, *SITE_ADMIN_ROLES):
            return Tool.objects.all()
        if _teaches_anywhere(user):
            return Tool.objects.filter(is_active=True)
        return Tool.objects.none()

    def perform_create(self, serializer):
        with transaction.atomic():
            tool = serializer.save(created_by=self.request.user, updated_by=self.request.user)
            record(self.request, "create", tool, after=snapshot(tool))

    def perform_update(self, serializer):
        before = snapshot(serializer.instance)
        with transaction.atomic():
            tool = serializer.save(updated_by=self.request.user)
            record(self.request, "update", tool, before=before, after=snapshot(tool))

    def perform_destroy(self, instance):
        with transaction.atomic():
            entity_id, before = instance.pk, snapshot(instance)
            instance.delete()  # a tool still placed refuses (in_use)
            record(self.request, "delete", instance, entity_id=entity_id, before=before)


class PlatformSerializer(serializers.Serializer):
    issuer = serializers.CharField()
    jwks_url = serializers.CharField()
    auth_url = serializers.CharField()
    token_url = serializers.CharField()
    deep_link_return_url = serializers.CharField()
    launch_start = serializers.CharField()


@extend_schema(
    responses={200: PlatformSerializer, 403: ErrorSerializer},
    summary="The LMS's details to give a tool's maker when registering it (course administrators)",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def platform(request):
    if not has_role(request.user, *SITE_ADMIN_ROLES):
        raise PermissionDenied("Only course administrators register tools.")
    return Response(services.platform_details())


class LineItemSerializer(serializers.ModelSerializer):
    tool_name = serializers.CharField(source="tool.name", read_only=True)
    placement = serializers.PrimaryKeyRelatedField(read_only=True)
    grade_category = serializers.PrimaryKeyRelatedField(
        queryset=GradeCategory.objects.all(), required=False, allow_null=True
    )
    weight = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, required=False)

    class Meta:
        model = LineItem
        fields = ("id", "label", "tool_name", "placement", "score_maximum", "weight", "grade_category")
        read_only_fields = ("score_maximum",)

    def validate_grade_category(self, value):
        if value is not None and value.site_id != self.instance.site_id:
            raise serializers.ValidationError("The category is on another course.")
        return value


class PlacementSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    item = serializers.IntegerField(source="item.id", read_only=True)
    module = TaughtRecord(Module, "site", write_only=True)
    module_id = serializers.IntegerField(source="item.module_id", read_only=True)
    tool = serializers.PrimaryKeyRelatedField(queryset=Tool.objects.filter(is_active=True))
    tool_name = serializers.CharField(source="tool.name", read_only=True)
    title = serializers.CharField(max_length=160, source="item.title")
    is_published = serializers.BooleanField(source="item.is_published", read_only=True)
    launch_url = serializers.CharField(source="item.url", read_only=True)
    score_maximum = serializers.DecimalField(
        max_digits=9,
        decimal_places=2,
        min_value=Decimal("0.01"),
        required=False,
        allow_null=True,
        write_only=True,
        help_text="Give one to make a gradebook column the tool posts scores to",
    )


@extend_schema(
    request=PlacementSerializer,
    responses={201: PlacementSerializer, 400: ErrorSerializer, 403: ErrorSerializer},
    summary="Place a tool in a module as a link (a draft); teaching staff",
)
@api_view(["POST"])
@permission_classes([RolePermission])
def place(request):
    data = PlacementSerializer(data=request.data, context={"request": request})
    data.is_valid(raise_exception=True)
    values = data.validated_data
    module, tool = values["module"], values["tool"]
    with transaction.atomic():
        placement = services.place(module, tool, values["item"]["title"], user=request.user)
        record(request, "create", placement.item, after=snapshot(placement.item), reason=f"Tool: {tool.name}")
        if values.get("score_maximum") and tool.grades:
            line_item = LineItem.objects.create(
                site=module.site,
                tool=tool,
                placement=placement,
                label=placement.item.title,
                score_maximum=values["score_maximum"],
                created_by=request.user,
            )
            record(request, "create", line_item, after=snapshot(line_item))
    return Response(PlacementSerializer(placement).data, status=201)


@extend_schema(
    request=None,
    responses={204: None, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="Remove a tool from a module; its gradebook column stays while it holds scores",
)
@api_view(["DELETE"])
@permission_classes([RolePermission])
def remove_placement(request, pk: int):
    placement = get_object_or_404(
        Placement.objects.select_related("item__module__site"),
        pk=pk,
        item__module__site__in=visible_sites(request.user),
    )
    if not can_teach(request.user, placement.site):
        raise PermissionDenied("Only the site's teaching staff can do this.")
    item = placement.item
    with transaction.atomic():
        before = snapshot(item)
        LineItem.objects.filter(placement=placement, scores__isnull=True).delete()
        item_id = item.pk
        item.delete()
        record(
            request, "delete", item, entity_id=item_id, before=before, reason="Tool removed from the module"
        )
    return Response(status=204)


@extend_schema(
    request=LineItemSerializer,
    responses={200: LineItemSerializer, 400: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="Set how a tool's gradebook column counts: its weight (0 does not count) and category",
)
@api_view(["PATCH"])
@permission_classes([RolePermission])
def change_line_item(request, pk: int):
    line_item = get_object_or_404(LineItem, pk=pk, site__in=visible_sites(request.user))
    if not can_teach(request.user, line_item.site):
        raise PermissionDenied("Only the site's teaching staff can do this.")
    data = LineItemSerializer(line_item, data=request.data, partial=True)
    data.is_valid(raise_exception=True)
    before = snapshot(line_item)
    with transaction.atomic():
        line_item = data.save(updated_by=request.user)
        record(request, "update", line_item, before=before, after=snapshot(line_item))
    return Response(LineItemSerializer(line_item).data)


class SiteToolsSerializer(serializers.Serializer):
    teaching = serializers.BooleanField()
    placements = PlacementSerializer(many=True)
    line_items = LineItemSerializer(many=True, help_text="Teaching staff only; empty for students")
    tools = ToolSerializer(many=True, help_text="Tools teaching staff can place; empty for students")


@extend_schema(
    responses={200: SiteToolsSerializer, 404: ErrorSerializer},
    summary="The outside tools on a course: placements, and for teaching staff the gradebook columns",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def site_tools(request, pk: int):
    site = get_object_or_404(visible_sites(request.user), pk=pk)
    teaching = can_teach(request.user, site)
    placements = Placement.objects.filter(item__module__site=site).select_related("item", "tool")
    if not teaching:
        placements = placements.filter(item__is_published=True, item__under_review=False)
        hidden = release.hidden_items(request, ContentItem.objects.filter(tool_link__in=placements))
        placements = placements.exclude(item_id__in=hidden)  # release conditions, as the module shows them
    body = {
        "teaching": teaching,
        "placements": PlacementSerializer(
            placements.order_by("item__module__position", "item__position"), many=True
        ).data,
        "line_items": LineItemSerializer(services.line_items(site), many=True).data if teaching else [],
        "tools": ToolSerializer(
            Tool.objects.filter(is_active=True), many=True, context={"request": request}
        ).data
        if teaching
        else [],
    }
    return Response(body)


router = SimpleRouter()
router.register("tools", ToolViewSet, basename="tool")
urlpatterns = [
    path("lti/platform/", platform, name="lti-platform"),
    path("tool-placements/", place, name="tool-placements"),
    path("tool-placements/<int:pk>/", remove_placement, name="tool-placement"),
    path("tool-line-items/<int:pk>/", change_line_item, name="tool-line-item"),
    path("sites/<int:pk>/tools/", site_tools, name="site-tools"),
    *router.urls,
]
