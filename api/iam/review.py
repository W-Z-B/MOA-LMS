"""The access review each term (item 1.21): who holds a system role, and who teaches which course site.

Administrators and course administrators read the list, take away what is no longer needed, and sign it off;
the auditor reads it and the sign-offs. A reminder goes out when the last sign-off is a term old (iam.tasks).
"""

from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from audit.services import record
from core.serializers import ErrorSerializer
from iam.models import AccessReview, Role, RoleScope
from iam.permissions import RolePermission
from iam.services import has_role

READERS = (Role.ADMINISTRATOR, Role.COURSE_ADMIN, Role.AUDITOR)
SIGNERS = (Role.ADMINISTRATOR, Role.COURSE_ADMIN)


def _name(user) -> str | None:
    return (user.get_full_name() or user.get_username()) if user else None


def role_holders() -> list[dict]:
    grants = RoleScope.objects.select_related("user", "role").order_by("role__code", "user__username")
    return [
        {
            "username": g.user.get_username(),
            "name": _name(g.user),
            "role": g.role.code,
            "role_name": g.role.name,
            "campus_code": g.campus_code,
            "given": g.created_at,
            "last_sign_in": g.user.last_login,
            "account_active": g.user.is_active,
        }
        for g in grants
    ]


def teaching_staff() -> list[dict]:
    from courses.models import Membership

    teaching = (
        Membership.objects.filter(
            is_active=True, role__in=[Membership.SiteRole.LECTURER, Membership.SiteRole.ASSISTANT]
        )
        .select_related("site", "person", "person__user")
        .order_by("site__code", "person__last_name")
    )
    return [
        {
            "site_code": m.site.code,
            "site_title": m.site.title,
            "term_code": m.site.term_code,
            "employee_no": m.person.external_id,
            "name": m.person.full_name,
            "site_role": m.get_role_display(),
            "person_active": m.person.is_active,
            "last_sign_in": m.person.user.last_login if m.person.user_id else None,
        }
        for m in teaching
    ]


class RoleHolderSerializer(serializers.Serializer):
    username = serializers.CharField()
    name = serializers.CharField()
    role = serializers.CharField()
    role_name = serializers.CharField()
    campus_code = serializers.CharField()
    given = serializers.DateTimeField()
    last_sign_in = serializers.DateTimeField(allow_null=True)
    account_active = serializers.BooleanField()


class TeachingSerializer(serializers.Serializer):
    site_code = serializers.CharField()
    site_title = serializers.CharField()
    term_code = serializers.CharField()
    employee_no = serializers.CharField()
    name = serializers.CharField()
    site_role = serializers.CharField()
    person_active = serializers.BooleanField()
    last_sign_in = serializers.DateTimeField(allow_null=True)


class SignOffSerializer(serializers.ModelSerializer):
    reviewed_by = serializers.SerializerMethodField()

    class Meta:
        model = AccessReview
        fields = ("id", "reviewed_by", "reviewed_at", "role_holders", "teaching_staff", "notes")
        read_only_fields = ("id", "reviewed_by", "reviewed_at", "role_holders", "teaching_staff")

    def get_reviewed_by(self, review) -> str | None:
        return _name(review.reviewed_by)


class AccessReviewSerializer(serializers.Serializer):
    last_review = SignOffSerializer(allow_null=True)
    role_holders = RoleHolderSerializer(many=True)
    teaching_staff = TeachingSerializer(many=True)


def _refused():
    return Response(
        {"code": "permission_denied", "detail": "You do not hold a role that permits this action."},
        status=status.HTTP_403_FORBIDDEN,
    )


@extend_schema(
    responses={200: AccessReviewSerializer, 403: ErrorSerializer},
    summary="Who holds a role and who teaches which site",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def access_review_view(request):
    if not has_role(request.user, *READERS):
        return _refused()
    payload = {
        "last_review": AccessReview.objects.select_related("reviewed_by").first(),
        "role_holders": role_holders(),
        "teaching_staff": teaching_staff(),
    }
    return Response(AccessReviewSerializer(payload).data)


@extend_schema(
    request=SignOffSerializer,
    responses={201: SignOffSerializer, 403: ErrorSerializer},
    summary="Sign off the access review: the list was read and what is no longer needed was removed",
)
@api_view(["POST"])
@permission_classes([RolePermission])
def access_review_sign_off(request):
    if not has_role(request.user, *SIGNERS):
        return _refused()
    data = SignOffSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    with transaction.atomic():
        review = AccessReview.objects.create(
            reviewed_by=request.user,
            role_holders=RoleScope.objects.count(),
            teaching_staff=len(teaching_staff()),
            notes=data.validated_data.get("notes", ""),
        )
        record(
            request,
            "access_review_signed",
            review,
            after={"role_holders": review.role_holders, "teaching_staff": review.teaching_staff},
            reason=review.notes,
        )
    return Response(SignOffSerializer(review).data, status=status.HTTP_201_CREATED)
