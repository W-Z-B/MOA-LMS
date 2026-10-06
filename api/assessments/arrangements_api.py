"""Extensions for a student or a group (item 2.26) and accommodations held once per student (item 3.23)."""

from django.db import transaction
from django.db.models import Q
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import serializers, viewsets

from assessments.models import Accommodation, Assignment, Extension
from audit.services import masked, record, snapshot
from courses.access import TaughtRecord, person_of, taught_sites
from courses.api import TeachingViewSet
from courses.models import Membership, SiteGroup
from iam.permissions import RolePermission
from iam.services import SITE_ADMIN_ROLES
from people.models import PersonRef


class ExtensionSerializer(serializers.ModelSerializer):
    assignment = TaughtRecord(Assignment, "site")
    student = serializers.PrimaryKeyRelatedField(
        queryset=PersonRef.objects.all(), required=False, allow_null=True, help_text="A student (person id)"
    )
    group = serializers.PrimaryKeyRelatedField(
        queryset=SiteGroup.objects.all(), required=False, allow_null=True, help_text="Or a group of the site"
    )
    student_no = serializers.CharField(source="student.external_id", read_only=True, default=None)

    class Meta:
        model = Extension
        fields = ("id", "assignment", "student", "student_no", "group", "due_at", "reason", "granted_by")
        read_only_fields = ("granted_by",)
        validators = []  # one extension per student or group is checked in validate, with a clearer message

    def validate(self, attrs):
        assignment = attrs.get("assignment") or self.instance.assignment
        student = attrs.get("student", getattr(self.instance, "student", None))
        group = attrs.get("group", getattr(self.instance, "group", None))
        if (student is None) == (group is None):
            raise serializers.ValidationError("Name one student or one group.")
        if (
            student is not None
            and not Membership.objects.filter(
                site=assignment.site, person=student, role=Membership.SiteRole.STUDENT
            ).exists()
        ):
            raise serializers.ValidationError({"student": ["Choose a student of this course."]})
        if group is not None and group.site_id != assignment.site_id:
            raise serializers.ValidationError({"group": ["Choose a group of this course."]})
        due_at = attrs.get("due_at", getattr(self.instance, "due_at", None))
        if due_at is not None and due_at <= assignment.due_at:
            raise serializers.ValidationError(
                {"due_at": ["An extension ends after the assignment's due date."]}
            )
        if not (attrs.get("reason") or getattr(self.instance, "reason", "")).strip():
            raise serializers.ValidationError({"reason": ["Give the reason."]})
        duplicate = Extension.objects.filter(assignment=assignment).filter(
            Q(student=student) if student else Q(group=group)
        )
        if self.instance is not None:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise serializers.ValidationError("There is already an extension for them; change that one.")
        return attrs


@extend_schema_view(
    list=extend_schema(
        parameters=[OpenApiParameter("assignment", OpenApiTypes.INT, description="Only this assignment")],
        summary="Extensions on the assignments the caller teaches",
    )
)
class ExtensionViewSet(TeachingViewSet):
    """A later due date for one student or one group, with the reason. The late flag, closing, late
    penalties and the zero for missing work all use it."""

    serializer_class = ExtensionSerializer
    queryset = Extension.objects.none()

    def get_queryset(self):
        qs = Extension.objects.filter(assignment__site__in=taught_sites(self.request.user)).select_related(
            "assignment__site", "student", "group"
        )
        assignment = self.request.query_params.get("assignment")
        return qs.filter(assignment_id=assignment) if assignment else qs

    def site_of(self, instance):
        return instance.assignment.site

    def site_from_data(self, data):
        return data["assignment"].site

    def perform_create(self, serializer):
        self._require_teaching(self.site_from_data(serializer.validated_data))
        with transaction.atomic():
            instance = serializer.save(
                granted_by=person_of(self.request.user),
                created_by=self.request.user,
                updated_by=self.request.user,
            )
            record(self.request, "create", instance, after=snapshot(instance), reason=instance.reason)

    def perform_update(self, serializer):
        if (
            "assignment" in serializer.validated_data
            and serializer.validated_data["assignment"] != serializer.instance.assignment
        ):
            raise serializers.ValidationError(
                {"assignment": ["An extension cannot move to another assignment."]}
            )
        super().perform_update(serializer)


class AccommodationSerializer(serializers.ModelSerializer):
    person = serializers.PrimaryKeyRelatedField(
        queryset=PersonRef.objects.filter(kind=PersonRef.Kind.STUDENT), help_text="The student (person id)"
    )
    student_no = serializers.CharField(source="person.external_id", read_only=True)

    class Meta:
        model = Accommodation
        fields = (
            "id",
            "person",
            "student_no",
            "extra_time_percent",
            "extra_days",
            "other_format",
            "reason",
            "is_active",
        )

    def validate_extra_time_percent(self, value):
        if value > 300:
            raise serializers.ValidationError("At most 300 percent.")
        return value

    def validate_extra_days(self, value):
        if value > 60:
            raise serializers.ValidationError("At most 60 days.")
        return value


def _kept(instance) -> dict:
    """The audit log keeps that the reason changed, never the reason itself (it may be about health)."""
    data = snapshot(instance)
    data["reason"] = masked(data.get("reason"))
    return data


@extend_schema_view(
    list=extend_schema(summary="Accommodations (course administrators)"),
)
class AccommodationViewSet(viewsets.ModelViewSet):
    """Held once per student by course administrators and applied automatically: the extra time to every
    quiz time limit, the extra days to every assignment due date. Teaching staff see only that an
    accommodation applies (accommodation_applies on submissions), never the reason."""

    permission_classes = [RolePermission]
    read_roles = SITE_ADMIN_ROLES
    write_roles = SITE_ADMIN_ROLES
    serializer_class = AccommodationSerializer
    queryset = Accommodation.objects.select_related("person")
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def perform_create(self, serializer):
        with transaction.atomic():
            instance = serializer.save(created_by=self.request.user, updated_by=self.request.user)
            record(self.request, "create", instance, after=_kept(instance))

    def perform_update(self, serializer):
        with transaction.atomic():
            before = _kept(serializer.instance)
            instance = serializer.save(updated_by=self.request.user)
            record(self.request, "update", instance, before=before, after=_kept(instance))

    def perform_destroy(self, instance):
        with transaction.atomic():
            before, entity_id = _kept(instance), instance.pk
            instance.delete()
            record(self.request, "delete", instance, before=before, entity_id=entity_id)
