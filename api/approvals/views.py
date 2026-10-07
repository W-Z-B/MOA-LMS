"""Approvals (ported from the HRMS approvals/views.py): what waits for me, and who stands in for me while I am
away. Any signed-in member of staff; course administrators also name stand-ins for others."""

from django.db import transaction
from django.db.models import Q, Value
from django.db.models.functions import Concat
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from approvals.inbox import waiting_for
from approvals.models import Delegation
from audit.services import record, snapshot
from core.serializers import ErrorSerializer
from iam.models import Role
from iam.permissions import RolePermission
from iam.services import has_role
from notifications.services import notify
from people.models import PersonRef


class WaitingItemSerializer(serializers.Serializer):
    kind = serializers.CharField()
    kind_name = serializers.CharField()
    title = serializers.CharField()
    since = serializers.DateTimeField()
    waited_days = serializers.IntegerField(help_text="Working days it has waited")
    overdue = serializers.BooleanField(help_text="Waited past its time limit")
    link = serializers.CharField(help_text="Where it is decided, in the web app")
    for_whom = serializers.CharField(help_text="Who it was sent to, when deciding as their stand-in")


@extend_schema(
    responses=WaitingItemSerializer(many=True), summary="Everything waiting for my decision, oldest first"
)
@api_view(["GET"])
@permission_classes([RolePermission])
def waiting(request):
    return Response(WaitingItemSerializer(waiting_for(request.user), many=True).data)


class ColleagueSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    employee_no = serializers.CharField()


@extend_schema(
    parameters=[
        OpenApiParameter(
            "q", str, required=True, description="Two letters or more of a name or employee number"
        )
    ],
    responses={200: ColleagueSerializer(many=True), 403: ErrorSerializer},
    summary="Colleagues on the staff who can sign in, to name one as a stand-in",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def colleagues(request):
    """The stand-in form finds the colleague it names here: at most ten, active and able to sign in."""
    own = getattr(request.user, "person", None)
    if not has_role(request.user, Role.COURSE_ADMIN) and (own is None or own.kind != PersonRef.Kind.STAFF):
        return Response(
            {"code": "permission_denied", "detail": "Stand-ins are named by members of staff."},
            status=status.HTTP_403_FORBIDDEN,
        )
    text = (request.query_params.get("q") or "").strip()
    if len(text) < 2:
        return Response([])
    people = (
        PersonRef.objects.filter(kind=PersonRef.Kind.STAFF, is_active=True, user__is_active=True)
        .annotate(whole=Concat("first_name", Value(" "), "last_name"))
        .filter(
            Q(first_name__icontains=text)
            | Q(last_name__icontains=text)
            | Q(whole__icontains=text)
            | Q(external_id__icontains=text)
        )
        .order_by("last_name", "first_name", "id")[:10]
    )
    return Response([{"id": p.pk, "name": p.full_name, "employee_no": p.external_id} for p in people])


class StaffPerson(serializers.PrimaryKeyRelatedField):
    def get_queryset(self):
        return PersonRef.objects.filter(kind=PersonRef.Kind.STAFF)


class DelegationSerializer(serializers.ModelSerializer):
    delegator = StaffPerson(
        required=False, help_text="Whose decisions: yourself unless a course administrator"
    )
    delegate = StaffPerson(help_text="A colleague on the staff who can sign in")
    delegator_name = serializers.CharField(source="delegator.full_name", read_only=True)
    delegate_name = serializers.CharField(source="delegate.full_name", read_only=True)
    in_force = serializers.SerializerMethodField()

    class Meta:
        model = Delegation
        fields = (
            "id",
            "delegator",
            "delegator_name",
            "delegate",
            "delegate_name",
            "starts",
            "ends",
            "reason",
            "cancelled",
            "in_force",
            "created_at",
        )
        read_only_fields = ("id", "cancelled", "created_at")

    def get_in_force(self, delegation) -> bool:
        today = timezone.localdate()
        return not delegation.cancelled and delegation.starts <= today <= delegation.ends

    def validate(self, attrs):
        request = self.context["request"]
        own = getattr(request.user, "person", None)
        delegator = attrs.get("delegator") or own
        if delegator is None:
            raise serializers.ValidationError(
                {"delegator": ["Your account is not linked to a staff record."]}
            )
        if delegator != own and not has_role(request.user, Role.COURSE_ADMIN):
            raise serializers.ValidationError({"delegator": ["You can name a stand-in for yourself only."]})
        delegate = attrs["delegate"]
        if delegate == delegator:
            raise serializers.ValidationError({"delegate": ["A stand-in is someone else."]})
        if not delegate.is_active or delegate.user is None or not delegate.user.is_active:
            raise serializers.ValidationError(
                {"delegate": [f"{delegate.full_name} cannot sign in to decide."]}
            )
        if attrs["ends"] < attrs["starts"]:
            raise serializers.ValidationError({"ends": ["It ends on or after the day it starts."]})
        if attrs["ends"] < timezone.localdate():
            raise serializers.ValidationError({"ends": ["That time has already passed."]})
        overlapping = Delegation.objects.filter(
            delegator=delegator, cancelled=False, starts__lte=attrs["ends"], ends__gte=attrs["starts"]
        )
        if overlapping.exists():
            raise serializers.ValidationError(
                {"starts": [f"{delegator.full_name} already has a stand-in for part of that time."]}
            )
        attrs["delegator"] = delegator
        return attrs


@extend_schema(
    parameters=[OpenApiParameter("person", int, description="For course administrators: one member of staff")]
)
class DelegationViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """My stand-ins and those I stand in for; course administrators also see and name them for others."""

    queryset = Delegation.objects.none()
    serializer_class = DelegationSerializer
    permission_classes = [RolePermission]

    def get_queryset(self):
        user = self.request.user
        own = getattr(user, "person", None)
        qs = Delegation.objects.select_related("delegator", "delegate")
        person = self.request.query_params.get("person")
        if person and has_role(user, Role.COURSE_ADMIN):
            return qs.filter(delegator_id=person)
        if own is None:
            return qs.none()
        return qs.filter(delegator=own) | qs.filter(delegate=own)

    def create(self, request, *args, **kwargs):
        # Stand-ins are named by members of staff (as the colleague search says), or by a course administrator
        # for someone else; settled before the form is read, so a student is refused rather than corrected.
        own = getattr(request.user, "person", None)
        if not has_role(request.user, Role.COURSE_ADMIN) and (
            own is None or own.kind != PersonRef.Kind.STAFF
        ):
            return Response(
                {"code": "permission_denied", "detail": "Stand-ins are named by members of staff."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().create(request, *args, **kwargs)

    @transaction.atomic
    def perform_create(self, serializer):
        delegation = serializer.save(created_by=self.request.user)
        record(self.request, "create", delegation, after=snapshot(delegation), reason=delegation.reason)
        notify(
            [delegation.delegate.user],
            title=f"You stand in for {delegation.delegator.full_name}",
            body=(
                f"From {delegation.starts:%d/%m/%Y} to {delegation.ends:%d/%m/%Y} you may decide what is "
                f"sent to {delegation.delegator.full_name}. It appears under To do."
            ),
            link="/to-do",
            dedupe_key=f"delegation:{delegation.pk}",
        )

    @extend_schema(
        request=None,
        responses={200: DelegationSerializer, 403: ErrorSerializer, 409: ErrorSerializer},
        summary="End a stand-in early, or before it starts",
    )
    @action(detail=True, methods=["post"])
    def end(self, request, pk=None):
        delegation = self.get_object()
        own = getattr(request.user, "person", None)
        if delegation.delegator != own and not has_role(request.user, Role.COURSE_ADMIN):
            return Response(
                {
                    "code": "forbidden",
                    "detail": "Only the person who named the stand-in, or a course administrator, ends it.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        if delegation.cancelled or delegation.ends < timezone.localdate():
            return Response(
                {"code": "over", "detail": "It is already over."}, status=status.HTTP_409_CONFLICT
            )
        with transaction.atomic():
            before = snapshot(delegation)
            delegation.cancelled = True
            delegation.save(update_fields=["cancelled", "updated_at"])
            record(request, "delegation_ended", delegation, before=before, after=snapshot(delegation))
        return Response(self.get_serializer(delegation).data)


router = SimpleRouter()
router.register("delegations", DelegationViewSet, basename="delegation")
