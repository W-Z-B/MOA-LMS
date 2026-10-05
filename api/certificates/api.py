"""Certificates (items 5.08 to 5.11): my certificates and their PDFs, templates for course administrators,
withdrawal, and the public check by reference and code, as an API and as a small page of its own."""

import html

from django.conf import settings
from django.db.models import OuterRef, Subquery
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import (
    action,
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter
from rest_framework.throttling import AnonRateThrottle

from audit.services import record
from certificates import checking, markup, services
from certificates.models import Certificate, CertificateTemplate
from core.serializers import ErrorSerializer
from courses.access import person_of
from iam.models import Role
from iam.permissions import RolePermission
from iam.services import has_role

MANAGERS = (Role.ADMINISTRATOR, Role.COURSE_ADMIN)
OVERSEERS = (*MANAGERS, Role.AUDITOR)


class CertificateSerializer(serializers.ModelSerializer):
    holder = serializers.CharField(source="person.full_name", read_only=True)
    course = serializers.CharField(source="site.title", read_only=True)
    status = serializers.SerializerMethodField(help_text="valid, expired or withdrawn")

    class Meta:
        model = Certificate
        fields = (
            "id",
            "reference",
            "site",
            "course",
            "person",
            "holder",
            "issued_on",
            "completed_on",
            "expires_on",
            "sha256",
            "status",
            "withdrawn_at",
            "withdrawal_reason",
        )
        read_only_fields = fields

    def get_status(self, obj) -> str:
        from django.utils import timezone

        if obj.is_withdrawn:
            return "withdrawn"
        if obj.expires_on is not None and obj.expires_on < timezone.localdate():
            return "expired"
        return "valid"


class WithdrawSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000, help_text="Why it was issued in error")


@extend_schema(
    parameters=[
        OpenApiParameter("person", int, description="For course administrators: one person's"),
        OpenApiParameter("site", int, description="For course administrators: one course's"),
    ]
)
class CertificateViewSet(viewsets.ReadOnlyModelViewSet):
    """My certificates; course administrators and the auditor see every certificate."""

    serializer_class = CertificateSerializer
    permission_classes = [RolePermission]
    queryset = Certificate.objects.none()

    def get_queryset(self):
        qs = Certificate.objects.select_related("person", "site")
        user = self.request.user
        if has_role(user, *OVERSEERS):
            params = self.request.query_params
            if params.get("person"):
                qs = qs.filter(person_id=params["person"])
            if params.get("site"):
                qs = qs.filter(site_id=params["site"])
            return qs
        person = person_of(user)
        return qs.filter(person=person) if person is not None else qs.none()

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY, 404: ErrorSerializer})
    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        certificate = self.get_object()
        record(request, "download", certificate, after={"reference": certificate.reference})
        return FileResponse(
            certificate.file.open("rb"),
            as_attachment=True,
            filename=f"{certificate.reference.replace('/', '-')}.pdf",
            content_type="application/pdf",
        )

    @extend_schema(
        request=WithdrawSerializer,
        responses={200: CertificateSerializer, 403: ErrorSerializer, 409: ErrorSerializer},
        summary="Withdraw a certificate issued in error; the public check then says it is withdrawn",
    )
    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        if not has_role(request.user, Role.COURSE_ADMIN):
            raise PermissionDenied("Only a course administrator withdraws a certificate.")
        certificate = self.get_object()
        data = WithdrawSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            services.withdraw(request, certificate, data.validated_data["reason"])
        except services.Refused as exc:
            return Response({"code": exc.code, "detail": exc.detail}, status=status.HTTP_409_CONFLICT)
        return Response(self.get_serializer(certificate).data)


class TemplateSerializer(serializers.ModelSerializer):
    fields_used = serializers.SerializerMethodField(help_text="The fields the wording uses")

    class Meta:
        model = CertificateTemplate
        fields = (
            "id",
            "code",
            "version",
            "name",
            "heading",
            "body",
            "signatory_name",
            "signatory_title",
            "is_active",
            "fields_used",
            "created_at",
        )
        read_only_fields = ("id", "version", "created_at")

    def get_fields_used(self, obj) -> list[str]:
        return markup.fields_in(obj.heading, obj.body)

    def validate(self, attrs):
        for name in ("heading", "body"):
            text = attrs.get(name, "")
            if markup.unclosed(text):
                raise serializers.ValidationError({name: ["A field is typed wrongly: use {{field_name}}."]})
            unknown = [f for f in markup.fields_in(text) if f not in services.FIELDS]
            if unknown:
                raise serializers.ValidationError({name: [f"Unknown field: {', '.join(unknown)}."]})
        return attrs


class TemplateChangeSerializer(TemplateSerializer):
    class Meta(TemplateSerializer.Meta):
        read_only_fields = ("id", "code", "version", "created_at")
        extra_kwargs = {field: {"required": False} for field in ("name", "body")}


@extend_schema(parameters=[OpenApiParameter("versions", str, enum=["all"], description="Every version")])
class TemplateViewSet(mixins.CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    """Certificate templates. A change is saved as a new version; issued certificates keep theirs."""

    serializer_class = TemplateSerializer
    permission_classes = [RolePermission]
    read_roles = OVERSEERS
    write_roles = MANAGERS
    queryset = CertificateTemplate.objects.none()

    def get_queryset(self):
        qs = CertificateTemplate.objects.all()
        if self.request.query_params.get("versions") != "all":
            newest = (
                CertificateTemplate.objects.filter(code=OuterRef("code"))
                .order_by("-version")
                .values("pk")[:1]
            )
            qs = qs.filter(pk=Subquery(newest))
        return qs.order_by("name", "-version")

    def perform_create(self, serializer):
        if CertificateTemplate.objects.filter(code=serializer.validated_data["code"]).exists():
            raise serializers.ValidationError({"code": ["That template exists: change it as a new version."]})
        made = serializer.save(created_by=self.request.user)
        record(self.request, "create", made, after={"code": made.code, "version": made.version})

    @extend_schema(
        request=TemplateChangeSerializer,
        responses={201: TemplateSerializer, 400: ErrorSerializer},
        summary="Change a template: saved as its next version",
    )
    @action(detail=True, methods=["post"], url_path="new-version")
    def new_version(self, request, pk=None):
        template = get_object_or_404(CertificateTemplate, pk=pk)
        data = TemplateChangeSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        made = services.new_version(request, template, data.validated_data)
        return Response(TemplateSerializer(made).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------------------------------------
# The public check (item 5.09)


class CheckSerializer(serializers.Serializer):
    reference = serializers.CharField(max_length=40, help_text="As printed, such as GSA/LMS/2026/0001")
    code = serializers.CharField(max_length=40, help_text="As printed at the foot of the certificate")


class CheckedSerializer(serializers.Serializer):
    """The answer: whether the certificate is genuine and, when it is, what it says, nothing more."""

    status = serializers.ChoiceField(choices=["genuine", "withdrawn", "no_match"])
    detail = serializers.CharField()
    reference = serializers.CharField(allow_null=True)
    holder = serializers.CharField(allow_null=True)
    course = serializers.CharField(allow_null=True)
    completed_on = serializers.DateField(allow_null=True)
    issued_on = serializers.DateField(allow_null=True)
    expires_on = serializers.DateField(allow_null=True)
    withdrawn_on = serializers.DateField(allow_null=True)


class CheckThrottle(AnonRateThrottle):
    """Beside the limit on wrong codes, a ceiling on how often one address may ask at all."""

    rate = "30/minute"


TOO_MANY = {
    "code": "too_many_attempts",
    "detail": "Too many wrong codes have been tried. Try again later.",
}


@extend_schema(
    request=CheckSerializer,
    responses={200: CheckedSerializer, 429: ErrorSerializer},
    summary="Check that a certificate is genuine, by its reference and code, without signing in",
    auth=[],
)
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([CheckThrottle])
def check_certificate(request):
    """Open to anyone shown a certificate. A wrong code and an unknown reference are answered alike."""
    data = CheckSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    try:
        found = checking.check(request, data.validated_data["reference"], data.validated_data["code"])
    except checking.TooMany:
        return Response(TOO_MANY, status=status.HTTP_429_TOO_MANY_REQUESTS)
    return Response(CheckedSerializer(checking.answer(found)).data)


PAGE = """<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Check a certificate · {org}</title>
<style>
body {{ font: 16px/1.5 system-ui, sans-serif; margin: 0; color: #111; background: #f6f7f5; }}
main {{ max-width: 34rem; margin: 0 auto; padding: 1rem; }}
h1 {{ font-size: 1.4rem; color: #2f6b46; }}
label {{ display: block; margin-top: .8rem; font-weight: 600; }}
input {{ width: 100%; box-sizing: border-box; padding: .6rem; font-size: 1rem; border: 1px solid #777;
  border-radius: 4px; }}
button {{ margin-top: 1rem; padding: .6rem 1.2rem; font-size: 1rem; background: #2f6b46; color: #fff;
  border: 0; border-radius: 4px; }}
.answer {{ margin-top: 1.2rem; padding: .8rem; border-radius: 4px; background: #fff;
  border: 2px solid #777; }}
.genuine {{ border-color: #2f6b46; }} .withdrawn, .no_match, .too_many_attempts {{ border-color: #a33; }}
dl {{ margin: .5rem 0 0; }} dt {{ font-weight: 600; }} dd {{ margin: 0 0 .4rem; }}
</style>
</head>
<body><main>
<h1>Check a certificate from {org}</h1>
<p>Enter the reference and the code printed at the foot of the certificate.</p>
<form method="post">
<label for="reference">Reference</label>
<input id="reference" name="reference" required maxlength="40" value="{reference}" autocomplete="off">
<label for="code">Code</label>
<input id="code" name="code" required maxlength="40" autocomplete="off">
<button type="submit">Check</button>
</form>
{answer}
</main></body>
</html>"""


def _shown(value) -> str:
    return value.strftime("%d/%m/%Y") if hasattr(value, "strftime") else str(value)


def _answer_html(answer: dict) -> str:
    escape = html.escape
    rows = [
        ("Holder", answer.get("holder")),
        ("Course", answer.get("course")),
        ("Completed", answer.get("completed_on")),
        ("Issued", answer.get("issued_on")),
        ("Valid until", answer.get("expires_on")),
        ("Withdrawn", answer.get("withdrawn_on")),
    ]
    facts = "".join(
        f"<dt>{escape(label)}</dt><dd>{escape(_shown(value))}</dd>" for label, value in rows if value
    )
    listed = f"<dl>{facts}</dl>" if facts else ""
    status_class = escape(answer["status"])
    return f'<div class="answer {status_class}" role="status"><p>{escape(answer["detail"])}</p>{listed}</div>'


@csrf_exempt  # nothing is changed for the person asking, and they hold no session here
def check_page(request):
    """The check as a page of its own, for anyone without the web app: no script, no sign-in (item 5.09)."""
    reference, answer = "", ""
    if request.method == "POST":
        reference = (request.POST.get("reference") or "").strip()[:40]
        code = (request.POST.get("code") or "").strip()[:40]
        if reference and code:
            try:
                found = checking.check(request, reference, code)
                answer = _answer_html(checking.answer(found))
            except checking.TooMany:
                answer = _answer_html({"status": "too_many_attempts", "detail": TOO_MANY["detail"]})
    elif request.method != "GET":
        return HttpResponse(status=405)
    body = PAGE.format(
        org=html.escape(settings.CERTIFICATE_ORGANISATION), reference=html.escape(reference), answer=answer
    )
    response = HttpResponse(body, content_type="text/html; charset=utf-8")
    response["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
        "frame-ancestors 'none'; base-uri 'none'"
    )
    response["Cache-Control"] = "no-store"
    response["Referrer-Policy"] = "no-referrer"
    return response


router = SimpleRouter()
router.register("certificates", CertificateViewSet, basename="certificate")
router.register("certificate-templates", TemplateViewSet, basename="certificate-template")
urlpatterns = [path("certificates/check/", check_certificate, name="certificate-check"), *router.urls]
