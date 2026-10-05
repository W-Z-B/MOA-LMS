"""Inviting people to their accounts (item 1.22): everyone not yet invited on a campus or in a term at once,
or one person. Administrators only; the same is done from the command line with `invite_people`."""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from core.serializers import ErrorSerializer
from iam import accounts
from iam.models import Role
from iam.permissions import role_required
from people.models import PersonRef

INVITERS = role_required(Role.ADMINISTRATOR)


class InviteAllSerializer(serializers.Serializer):
    campus_code = serializers.CharField(max_length=10, required=False, allow_blank=True, default="")
    term_code = serializers.CharField(max_length=16, required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if not attrs["campus_code"] and not attrs["term_code"]:
            raise serializers.ValidationError("Name a campus, a term, or both.")
        return attrs


class InvitedSerializer(serializers.Serializer):
    invited = serializers.IntegerField(help_text="Invitations sent (accounts opened where there were none)")
    emailed = serializers.IntegerField(help_text="Of those, how many emails were accepted for delivery")
    in_use = serializers.IntegerField(help_text="Left alone: the account is already in use")


class UninvitedSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    without_email = serializers.IntegerField(help_text="Not invited because the record has no email address")


class InviteOneSerializer(serializers.Serializer):
    person = serializers.IntegerField()
    outcome = serializers.ChoiceField(choices=["invited", "in_use", "no_email"])
    emailed = serializers.BooleanField()


SCOPE = [
    OpenApiParameter("campus_code", str, description="People of this campus"),
    OpenApiParameter("term_code", str, description="People on a site of this term"),
]


@extend_schema(
    parameters=SCOPE,
    responses={200: UninvitedSerializer, 403: ErrorSerializer},
    summary="How many people of a campus or term have not been invited yet",
)
@api_view(["GET"])
@permission_classes([INVITERS])
def uninvited_view(request):
    campus, term = request.query_params.get("campus_code", ""), request.query_params.get("term_code", "")
    without = PersonRef.objects.filter(is_active=True, invited_at__isnull=True, email="")
    if campus:
        without = without.filter(campus_code=campus)
    if term:
        without = without.filter(memberships__site__term_code=term, memberships__is_active=True)
    return Response(
        {
            "count": accounts.uninvited(campus_code=campus, term_code=term).count(),
            "without_email": without.distinct().count(),
        }
    )


@extend_schema(
    request=InviteAllSerializer,
    responses={200: InvitedSerializer, 400: ErrorSerializer, 403: ErrorSerializer},
    summary="Invite everyone not yet invited on a campus or in a term to choose a password",
)
@api_view(["POST"])
@permission_classes([INVITERS])
def invite_all_view(request):
    data = InviteAllSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    return Response(accounts.invite_all(request, **data.validated_data))


@extend_schema(
    request=None,
    responses={200: InviteOneSerializer, 403: ErrorSerializer, 404: ErrorSerializer, 409: ErrorSerializer},
    summary="Invite one person, or send the invitation again; opens their account if they have none",
    operation_id="auth_accounts_invite_one",
)
@api_view(["POST"])
@permission_classes([INVITERS])
def invite_one_view(request, person_id: int):
    person = get_object_or_404(PersonRef, pk=person_id)
    if not person.is_active:
        return Response(
            {"code": "inactive", "detail": "This person's record is no longer active."},
            status=status.HTTP_409_CONFLICT,
        )
    result = accounts.invite(request, person)
    if result["outcome"] == "no_email":
        return Response(
            {"code": "no_email", "detail": "The record has no email address to send the invitation to."},
            status=status.HTTP_409_CONFLICT,
        )
    return Response(result)
