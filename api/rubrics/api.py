"""Rubrics and marking guides: a site's own, and the GSA library kept by course administrators.

Items 3.09 and 3.10.
"""

from django.db import transaction
from django.db.models import Q
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from audit.services import record
from core.serializers import ErrorSerializer
from courses.access import TaughtRecord, taught_sites
from courses.models import CourseSite
from iam.permissions import RolePermission
from iam.services import SITE_ADMIN_ROLES, has_role
from rubrics import services
from rubrics.models import Rubric


class LevelSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    points = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=0, required=False, default=0)
    description = serializers.CharField()


class CriterionSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    max_points = serializers.DecimalField(
        max_digits=6, decimal_places=2, min_value=0, required=False, allow_null=True, help_text="Guides only"
    )
    levels = LevelSerializer(many=True, required=False, default=list)


class RubricSerializer(serializers.ModelSerializer):
    site = TaughtRecord(CourseSite, required=False, allow_null=True, help_text="Empty for the GSA library")
    criteria = CriterionSerializer(many=True)
    max_points = serializers.SerializerMethodField(help_text="The most the rubric gives; 0 when descriptive")
    in_use = serializers.SerializerMethodField(help_text="Marks were given with it, so it cannot change")

    class Meta:
        model = Rubric
        fields = (
            "id",
            "site",
            "title",
            "description",
            "kind",
            "copied_from",
            "criteria",
            "max_points",
            "in_use",
        )
        read_only_fields = ("copied_from",)

    def get_max_points(self, obj) -> str:
        return str(obj.max_points())

    def get_in_use(self, obj) -> bool:
        return services.in_use(obj)

    def to_representation(self, obj):
        data = super().to_representation(obj)
        data["criteria"] = [
            {
                "id": c.id,
                "title": c.title,
                "description": c.description,
                "max_points": str(c.max_points) if c.max_points is not None else None,
                "levels": [
                    {"id": lv.id, "points": str(lv.points), "description": lv.description}
                    for lv in c.levels.all()
                ],
            }
            for c in obj.criteria.prefetch_related("levels")
        ]
        return data

    def validate(self, attrs):
        kind = attrs.get("kind", getattr(self.instance, "kind", Rubric.Kind.SCORED))
        for row in attrs.get("criteria", []):
            if kind == Rubric.Kind.GUIDE:
                if not row.get("max_points"):
                    raise serializers.ValidationError(
                        {"criteria": [f"Give '{row['title']}' a maximum above 0."]}
                    )
            elif not row.get("levels"):
                raise serializers.ValidationError(
                    {"criteria": [f"Give '{row['title']}' at least one level."]}
                )
        if "criteria" in attrs and not attrs["criteria"]:
            raise serializers.ValidationError({"criteria": ["Add at least one criterion."]})
        return attrs


class RubricCopySerializer(serializers.Serializer):
    site = TaughtRecord(CourseSite, help_text="The site that gets the copy")


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter("site", OpenApiTypes.INT, description="Only this site's rubrics"),
            OpenApiParameter("library", OpenApiTypes.STR, enum=["1"], description="1 lists the GSA library"),
        ],
        summary="Rubrics and marking guides the caller may use",
    )
)
class RubricViewSet(viewsets.ModelViewSet):
    """A site's rubrics are kept by its teaching staff; the library by course administrators. A rubric that
    marks were given with cannot change or go: copy it instead."""

    permission_classes = [RolePermission]
    serializer_class = RubricSerializer
    queryset = Rubric.objects.none()
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        mine = Q(site__in=taught_sites(user))
        library = (
            Q(site__isnull=True)
            if (has_role(user, *SITE_ADMIN_ROLES) or services.teaches_anywhere(user))
            else Q(pk__in=[])
        )
        qs = Rubric.objects.filter(mine | library).select_related("site")
        params = self.request.query_params
        if params.get("site"):
            qs = qs.filter(site_id=params["site"])
        if params.get("library") == "1":
            qs = qs.filter(site__isnull=True)
        return qs

    def _require_manage(self, rubric) -> None:
        if not services.can_manage(self.request.user, rubric):
            raise PermissionDenied(
                "Only course administrators keep the GSA library."
                if rubric.site_id is None
                else "Only the site's teaching staff can do this."
            )

    def perform_create(self, serializer):
        site = serializer.validated_data.get("site")
        self._require_manage(Rubric(site=site))
        criteria = serializer.validated_data.pop("criteria")
        with transaction.atomic():
            rubric = serializer.save(created_by=self.request.user, updated_by=self.request.user)
            services.replace_criteria(rubric, criteria)
            record(self.request, "create", rubric, after={"title": rubric.title, "criteria": len(criteria)})

    def perform_update(self, serializer):
        rubric = serializer.instance
        self._require_manage(rubric)
        if services.in_use(rubric):
            raise PermissionDenied("Marks were given with this rubric, so it cannot change. Copy it instead.")
        if "site" in serializer.validated_data and serializer.validated_data["site"] != rubric.site:
            raise serializers.ValidationError({"site": ["A rubric cannot move to another site."]})
        criteria = serializer.validated_data.pop("criteria", None)
        with transaction.atomic():
            rubric = serializer.save(updated_by=self.request.user)
            if criteria is not None:
                services.replace_criteria(rubric, criteria)
            record(self.request, "update", rubric, after={"title": rubric.title})

    def perform_destroy(self, instance):
        self._require_manage(instance)
        with transaction.atomic():
            entity_id = instance.pk
            instance.delete()  # an assignment still using it refuses (in_use)
            record(self.request, "delete", instance, entity_id=entity_id, before={"title": instance.title})

    @extend_schema(
        request=RubricCopySerializer,
        responses={201: RubricSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
        summary="Copy a rubric, such as one from the GSA library, to a site so an assignment can use it",
    )
    @action(detail=True, methods=["post"])
    def copy(self, request, pk=None):
        rubric = self.get_object()
        data = RubricCopySerializer(data=request.data, context={"request": request})
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            copy = services.copy_rubric(rubric, data.validated_data["site"], request.user)
            record(request, "create", copy, after={"title": copy.title, "copied_from": rubric.id})
        return Response(RubricSerializer(copy, context={"request": request}).data, status=201)


def rubric_for_students(rubric: Rubric) -> dict:
    """The rubric as students see it with the assignment (item 3.09)."""
    return RubricSerializer(rubric).to_representation(rubric)


router = DefaultRouter()
router.register("rubrics", RubricViewSet, basename="rubric")
urlpatterns = router.urls
