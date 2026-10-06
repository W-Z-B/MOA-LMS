"""Group work endpoints (item 4.12): groupings, random allocation, self-sign-up and a student's own groups.

Groups themselves are made, renamed and filled by hand through /groups/ (courses.api). Teaching staff manage
everything here; students list the groups they are in or may join, and join or leave self-sign-up groups.
"""

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.urls import path
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from audit.services import record, snapshot
from core.serializers import ErrorSerializer
from courses import groups
from courses.access import TaughtRecord, can_teach, person_of, taught_sites, visible_sites
from courses.api import TeachingViewSet, require_teaching
from courses.groups import Grouping, GroupRefused, GroupSignUp
from courses.models import CourseSite, SiteGroup
from iam.permissions import RolePermission


def refused(exc: GroupRefused, status: int = 409) -> Response:
    return Response({"code": exc.code, "detail": exc.detail}, status=status)


class GroupingSerializer(serializers.ModelSerializer):
    site = TaughtRecord(CourseSite)
    groups = TaughtRecord(SiteGroup, "site", many=True, required=False, help_text="Ids of the site's groups")

    class Meta:
        model = Grouping
        fields = ("id", "site", "name", "description", "groups")

    def validate(self, attrs):
        site = attrs.get("site") or self.instance.site
        if self.instance is not None and "site" in attrs and attrs["site"].pk != self.instance.site_id:
            raise serializers.ValidationError({"site": ["A grouping stays on its course."]})
        if any(g.site_id != site.id for g in attrs.get("groups", [])):
            raise serializers.ValidationError({"groups": ["Choose groups of this course."]})
        name = attrs.get("name")
        others = Grouping.objects.filter(site=site, name=name).exclude(pk=getattr(self.instance, "pk", None))
        if name and others.exists():
            raise serializers.ValidationError({"name": ["The course already has a grouping with this name."]})
        return attrs


@extend_schema_view(
    list=extend_schema(parameters=[OpenApiParameter("site", OpenApiTypes.INT, description="Only this site")])
)
class GroupingViewSet(TeachingViewSet):
    """Groupings: named sets of a site's groups. Teaching staff only."""

    serializer_class = GroupingSerializer

    def get_queryset(self):
        qs = Grouping.objects.filter(site__in=taught_sites(self.request.user)).prefetch_related("groups")
        site = self.request.query_params.get("site")
        return qs.filter(site_id=site) if site else qs

    def site_of(self, instance):
        return instance.site

    def site_from_data(self, data):
        return data["site"]


class AllocateSerializer(serializers.Serializer):
    groups = serializers.IntegerField(
        required=False, min_value=1, max_value=200, help_text="Make this many groups"
    )
    size = serializers.IntegerField(
        required=False, min_value=1, max_value=500, help_text="Or: groups of at most this many"
    )
    prefix = serializers.CharField(
        default="Group", max_length=60, help_text='Groups are named "<prefix> 1", "<prefix> 2"...'
    )
    grouping = serializers.CharField(
        required=False, allow_blank=True, max_length=80, help_text="Put the new groups in a new grouping"
    )

    def validate(self, attrs):
        if bool(attrs.get("groups")) == bool(attrs.get("size")):
            raise serializers.ValidationError("Give either a number of groups or a group size, not both.")
        return attrs


class AllocatedGroupSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    members = serializers.ListField(child=serializers.IntegerField(), help_text="Membership ids")


class AllocatedSerializer(serializers.Serializer):
    grouping = serializers.IntegerField(allow_null=True)
    groups = AllocatedGroupSerializer(many=True)


@extend_schema(
    request=AllocateSerializer,
    responses={
        201: AllocatedSerializer,
        400: OpenApiTypes.OBJECT,
        403: ErrorSerializer,
        404: ErrorSerializer,
        409: ErrorSerializer,
    },
    summary="Share the site's students at random into new groups: N groups, or groups of at most K",
)
@api_view(["POST"])
@permission_classes([RolePermission])
def allocate(request, pk: int):
    site = get_object_or_404(visible_sites(request.user), pk=pk)
    require_teaching(request.user, site)
    data = AllocateSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    v = data.validated_data
    try:
        with transaction.atomic():
            made, grouping = groups.allocate(
                site,
                groups=v.get("groups"),
                size=v.get("size"),
                prefix=v["prefix"].strip() or "Group",
                grouping_name=v.get("grouping", "").strip(),
                user=request.user,
            )
            for group in made:
                record(request, "create", group, after={**snapshot(group), "members": _member_ids(group)})
            if grouping is not None:
                record(request, "create", grouping, after=snapshot(grouping))
    except GroupRefused as exc:
        return refused(exc)
    body = {
        "grouping": grouping.id if grouping else None,
        "groups": [{"id": g.id, "name": g.name, "members": _member_ids(g)} for g in made],
    }
    return Response(body, status=201)


def _member_ids(group: SiteGroup) -> list[int]:
    return sorted(group.members.values_list("id", flat=True))


class SignUpSerializer(serializers.ModelSerializer):
    class Meta:
        model = GroupSignUp
        fields = ("is_open", "max_size", "closes_at")
        extra_kwargs = {"max_size": {"min_value": 1}}


def _taught_group(request, pk: int) -> SiteGroup:
    group = get_object_or_404(SiteGroup.objects.filter(site__in=visible_sites(request.user)), pk=pk)
    require_teaching(request.user, group.site)
    return group


@extend_schema(
    methods=["PUT"],
    request=SignUpSerializer,
    responses={200: SignUpSerializer, 400: OpenApiTypes.OBJECT, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="Let students join this group themselves, with a largest size and a closing time",
)
@extend_schema(
    methods=["DELETE"],
    request=None,
    responses={204: None, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="Stop self-sign-up for this group; its members stay",
)
@api_view(["PUT", "DELETE"])
@permission_classes([RolePermission])
def sign_up_settings(request, pk: int):
    group = _taught_group(request, pk)
    current = GroupSignUp.objects.filter(group=group).first()
    with transaction.atomic():
        if request.method == "DELETE":
            if current is not None:
                before, entity_id = snapshot(current), current.pk
                current.delete()
                record(request, "delete", current, before=before, entity_id=entity_id)
            return Response(status=204)
        data = SignUpSerializer(current, data=request.data)
        data.is_valid(raise_exception=True)
        before = snapshot(current) if current else None
        stamps = {"updated_by": request.user} if current else {"created_by": request.user, "group": group}
        sign_up = data.save(**stamps)
        record(request, "update" if current else "create", sign_up, before=before, after=snapshot(sign_up))
    return Response(SignUpSerializer(sign_up).data)


class JoinedSerializer(serializers.Serializer):
    group = serializers.IntegerField()
    member = serializers.BooleanField()


def _join_or_leave(request, pk: int, joining: bool) -> Response:
    group = get_object_or_404(SiteGroup.objects.filter(site__in=visible_sites(request.user)), pk=pk)
    person = person_of(request.user)
    membership = groups.student_membership(person, group.site)
    try:
        with transaction.atomic():
            (groups.join if joining else groups.leave)(group, person)
            record(
                request,
                "group_joined" if joining else "group_left",
                membership,
                after={"group": group.id, "name": group.name},
            )
    except GroupRefused as exc:
        return refused(exc, 403 if exc.code in ("not_a_student", "not_self_sign_up") else 409)
    return Response({"group": group.id, "member": joining})


@extend_schema(
    request=None,
    responses={200: JoinedSerializer, 403: ErrorSerializer, 404: ErrorSerializer, 409: ErrorSerializer},
    summary="Join a self-sign-up group (students). Refused when full, closed, or already in its set",
)
@api_view(["POST"])
@permission_classes([RolePermission])
def join(request, pk: int):
    return _join_or_leave(request, pk, True)


@extend_schema(
    request=None,
    responses={200: JoinedSerializer, 403: ErrorSerializer, 404: ErrorSerializer, 409: ErrorSerializer},
    summary="Leave a self-sign-up group while sign-up is open (students)",
)
@api_view(["POST"])
@permission_classes([RolePermission])
def leave(request, pk: int):
    return _join_or_leave(request, pk, False)


class MyGroupSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    groupings = serializers.ListField(child=serializers.CharField())
    member = serializers.BooleanField(help_text="Whether I am in it")
    self_sign_up = serializers.BooleanField()
    open = serializers.BooleanField(help_text="Whether I may join or leave it now")
    places_left = serializers.IntegerField(allow_null=True, help_text="Null when there is no limit")
    closes_at = serializers.DateTimeField(allow_null=True)


@extend_schema(
    responses={200: MyGroupSerializer(many=True), 404: ErrorSerializer},
    summary="My groups on a site, and the self-sign-up groups I may join. Teaching staff see every group",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def my_groups(request, pk: int):
    site = get_object_or_404(visible_sites(request.user), pk=pk)
    person = person_of(request.user)
    mine = groups.member_group_ids(person, site)
    rows = SiteGroup.objects.filter(site=site).select_related("sign_up").prefetch_related("groupings")
    if not can_teach(request.user, site):
        rows = [g for g in rows if g.id in mine or hasattr(g, "sign_up")]
    out = []
    for group in rows:
        sign_up = getattr(group, "sign_up", None)
        count = group.members.count()
        out.append(
            {
                "id": group.id,
                "name": group.name,
                "groupings": [g.name for g in group.groupings.all()],
                "member": group.id in mine,
                "self_sign_up": sign_up is not None,
                "open": bool(sign_up and sign_up.accepting()),
                "places_left": max(sign_up.max_size - count, 0) if sign_up and sign_up.max_size else None,
                "closes_at": sign_up.closes_at if sign_up else None,
            }
        )
    return Response(out)


router = DefaultRouter()
router.register("groupings", GroupingViewSet, basename="grouping")
urlpatterns = [
    path("sites/<int:pk>/allocate-groups/", allocate, name="site-allocate-groups"),
    path("sites/<int:pk>/my-groups/", my_groups, name="site-my-groups"),
    path("groups/<int:pk>/sign-up/", sign_up_settings, name="group-sign-up"),
    path("groups/<int:pk>/join/", join, name="group-join"),
    path("groups/<int:pk>/leave/", leave, name="group-leave"),
    *router.urls,
]
