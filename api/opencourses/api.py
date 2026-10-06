"""Open short courses (item 5.07): the public catalogue and registration, and joining once signed in.

Every endpoint answers 404 with open_courses_off while OPEN_COURSES_ENABLED is off (the default): GSA has
not yet decided to offer open courses (decision D0, ADR 0032).
"""

from django.shortcuts import get_object_or_404
from django.urls import path
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from core.serializers import ErrorSerializer
from courses.access import person_of
from courses.models import CourseSite
from iam.permissions import RolePermission
from opencourses import services


class PublicThrottle(AnonRateThrottle):
    """A ceiling on how often one address may use the public pages at all, beside the registration limits."""

    rate = "30/minute"


class OpenCourseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()
    title = serializers.CharField()
    summary = serializers.CharField()
    audience = serializers.CharField()
    length_hours = serializers.CharField(allow_null=True)
    places_left = serializers.IntegerField(allow_null=True, help_text="null when there is no limit")
    joined = serializers.BooleanField(help_text="The signed-in person is on it")
    certificate = serializers.BooleanField(help_text="A certificate is issued on completion")


class OpenNoticeSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    title = serializers.CharField()
    body = serializers.CharField()


class OpenCatalogueSerializer(serializers.Serializer):
    courses = OpenCourseSerializer(many=True)
    privacy_notice = OpenNoticeSerializer(allow_null=True, help_text="Read and accepted when registering")


class OpenRegisterSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=80)
    last_name = serializers.CharField(max_length=80)
    email = serializers.EmailField()
    site = serializers.PrimaryKeyRelatedField(
        queryset=CourseSite.objects.filter(kind=CourseSite.Kind.OPEN, is_published=True),
        required=False,
        allow_null=True,
        help_text="The open course to join once registered",
    )
    privacy_accepted = serializers.BooleanField(help_text="Must be true: the privacy notice was read")

    def validate_privacy_accepted(self, value):
        if not value:
            raise serializers.ValidationError("Read the privacy notice and accept it to register.")
        return value


class OpenConfirmSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=100)
    password = serializers.CharField(max_length=128, style={"input_type": "password"})


class OpenLinkSerializer(serializers.Serializer):
    email = serializers.EmailField()
    first_name = serializers.CharField()
    course = serializers.CharField(allow_null=True)


class OpenDoneSerializer(serializers.Serializer):
    detail = serializers.CharField()
    username = serializers.CharField(required=False)


def _refused(error: services.Refused) -> Response:
    return Response({"code": error.code, "detail": error.detail}, status=error.status)


def _course(site: CourseSite, person) -> dict:
    from staffdev.enrolment import places_left

    entry = site.catalogue
    return {
        "id": site.id,
        "code": site.code,
        "title": site.title,
        "summary": entry.summary,
        "audience": entry.audience,
        "length_hours": f"{entry.length_hours.normalize():f}" if entry.length_hours is not None else None,
        "places_left": places_left(entry),
        "joined": bool(person and site.memberships.filter(person=person, is_active=True).exists()),
        "certificate": entry.issue_certificate,
    }


@extend_schema(
    responses={200: OpenCatalogueSerializer, 404: ErrorSerializer},
    summary="The open short courses, for anyone (no sign-in), with the privacy notice",
    auth=[],
)
@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([PublicThrottle])
def catalogue(request):
    try:
        services.require_enabled()
    except services.Refused as error:
        return _refused(error)
    from privacy.services import current_notice

    person = person_of(request.user) if request.user.is_authenticated else None
    notice = current_notice()
    return Response(
        {
            "courses": [_course(site, person) for site in services.open_sites()],
            "privacy_notice": {"version": notice.version, "title": notice.title, "body": notice.body}
            if notice
            else None,
        }
    )


@extend_schema(
    request=OpenRegisterSerializer,
    responses={202: OpenDoneSerializer, 400: ErrorSerializer, 404: ErrorSerializer, 429: ErrorSerializer},
    summary="Register for open short courses: a link to choose a password is emailed to the address",
    description="The answer is the same whether or not the address has an account. Limits: "
    "OPEN_REGISTRATIONS_PER_ADDRESS an hour from one network address, three a day for one email address.",
    auth=[],
)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([PublicThrottle])
def register(request):
    try:
        services.require_enabled()
        data = OpenRegisterSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = dict(data.validated_data)
        values.pop("privacy_accepted")
        services.register(request, **values)
    except services.Refused as error:
        return _refused(error)
    return Response(
        {"detail": "Thank you. If the address can receive mail, a link to finish registering is on its way."},
        status=status.HTTP_202_ACCEPTED,
    )


@extend_schema(
    methods=["GET"],
    responses={200: OpenLinkSerializer, 400: ErrorSerializer, 404: ErrorSerializer},
    summary="Check a registration link before the password is chosen (?token=)",
    auth=[],
)
@extend_schema(
    methods=["POST"],
    request=OpenConfirmSerializer,
    responses={201: OpenDoneSerializer, 400: ErrorSerializer, 404: ErrorSerializer, 409: ErrorSerializer},
    summary="Follow the registration link: choose a password and the learner's account is made",
    description="The username is the email address. Refusals: link_not_valid, weak_password, "
    "already_registered. The learner sees open courses only, never an academic course.",
    auth=[],
)
@api_view(["GET", "POST"])
@permission_classes([AllowAny])
@throttle_classes([PublicThrottle])
def confirm(request):
    try:
        if request.method == "GET":
            found = services.check_link(request.query_params.get("token", ""))
            return Response(
                {
                    "email": found.email,
                    "first_name": found.first_name,
                    "course": found.site.title if found.site else None,
                }
            )
        data = OpenConfirmSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = services.confirm(request, **data.validated_data)
    except services.Refused as error:
        return _refused(error)
    return Response(
        {"detail": "Your account is ready. Sign in with your email address.", "username": user.username},
        status=status.HTTP_201_CREATED,
    )


@extend_schema(
    request=None,
    responses={200: OpenCourseSerializer, 403: ErrorSerializer, 404: ErrorSerializer, 409: ErrorSerializer},
    summary="Join an open short course (signed in)",
)
@api_view(["POST"])
@permission_classes([RolePermission])
def join(request, pk: int):
    try:
        services.require_enabled()
    except services.Refused as error:
        return _refused(error)
    person = person_of(request.user)
    if person is None:
        raise PermissionDenied("Your account has no person record to join a course with.")
    site = get_object_or_404(services.open_sites(), pk=pk)
    try:
        services.join(request, site, person)
    except services.Refused as error:
        return _refused(error)
    return Response(_course(site, person))


urlpatterns = [
    path("open-courses/", catalogue, name="open-courses"),
    path("open-courses/register/", register, name="open-courses-register"),
    path("open-courses/confirm/", confirm, name="open-courses-confirm"),
    path("open-courses/<int:pk>/join/", join, name="open-courses-join"),
]
