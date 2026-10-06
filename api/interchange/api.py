"""Course interchange (item 6.08): export a course as a Common Cartridge, and import a cartridge or a Moodle
course backup into a course, with a report of what came in and what did not. Teaching staff of the course."""

import tempfile

from django.conf import settings
from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.urls import path
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from audit.services import record
from core.serializers import ErrorSerializer
from courses.access import can_teach, visible_sites
from iam.permissions import RolePermission
from interchange import cartridge, moodle
from interchange.common import ImportRefused

MB = 1024 * 1024


def _taught(request, pk: int):
    site = get_object_or_404(visible_sites(request.user), pk=pk)
    if not can_teach(request.user, site):
        raise PermissionDenied("Only the site's teaching staff can do this.")
    return site


@extend_schema(
    responses={(200, "application/zip"): OpenApiTypes.BINARY, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="Download the course's content as an IMS Common Cartridge 1.3 file (.imscc)",
    description="Modules, pages, files, links and packages; assignments as web pages; quiz questions as QTI "
    "1.2 where the type allows. README.txt in the cartridge lists what was left out. Never people or marks.",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def export_cartridge(request, pk: int):
    site = _taught(request, pk)
    stream = tempfile.SpooledTemporaryFile(max_size=20 * MB)  # noqa: SIM115 - FileResponse closes it
    summary = cartridge.export(site, stream)
    stream.seek(0)
    record(request, "export", site, after={"format": "common_cartridge_1.3", **summary})
    filename = f"{site.code}.imscc".replace("/", "-")
    return FileResponse(stream, as_attachment=True, filename=filename, content_type="application/zip")


class ImportSerializer(serializers.Serializer):
    file = serializers.FileField(
        help_text="A Common Cartridge (.imscc or .zip) or a Moodle course backup (.mbz); at most "
        "UPLOAD_LIMIT_PACKAGE_MB"
    )


class ImportReportSerializer(serializers.Serializer):
    format = serializers.ChoiceField(choices=["common_cartridge", "moodle_backup"])
    modules = serializers.IntegerField()
    items = serializers.IntegerField()
    questions = serializers.IntegerField()
    imported = serializers.ListField(child=serializers.DictField(), help_text="{kind, title, module}")
    skipped = serializers.ListField(child=serializers.DictField(), help_text="{title, reason}")
    warnings = serializers.ListField(child=serializers.CharField())


@extend_schema(
    request={"multipart/form-data": ImportSerializer},
    responses={200: ImportReportSerializer, 400: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="Import a Common Cartridge or a Moodle backup's content into the course, as drafts",
    description="Modules are added after the course's present ones; everything comes in unpublished, with "
    "its "
    "licence not yet known unless the file says. All or nothing: a file that cannot be read changes nothing.",
)
@api_view(["POST"])
@permission_classes([RolePermission])
@parser_classes([MultiPartParser])
def import_content(request, pk: int):
    site = _taught(request, pk)
    data = ImportSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    upload = data.validated_data["file"]
    limit = settings.UPLOAD_LIMIT_PACKAGE_MB
    if upload.size > limit * MB:
        return Response({"code": "too_large", "detail": f"The file is larger than {limit} MB."}, status=400)
    upload.seek(0)
    head = upload.read(4)
    upload.seek(0)
    name = upload.name.lower()
    is_backup = name.endswith(".mbz") or head.startswith(b"\x1f\x8b")
    try:
        with transaction.atomic():
            if is_backup:
                report = {"format": "moodle_backup", **moodle.import_backup(site, upload, request)}
            elif head == b"PK\x03\x04":
                report = {"format": "common_cartridge", **cartridge.import_cartridge(site, upload, request)}
            else:
                raise ImportRefused("Send a Common Cartridge (.imscc) or a Moodle course backup (.mbz).")
            summary = {k: report[k] for k in ("format", "modules", "items", "questions")}
            record(request, "import", site, after={**summary, "skipped": len(report["skipped"])})
    except ImportRefused as refused:
        return Response({"code": "import_refused", "detail": str(refused)}, status=400)
    return Response(report)


urlpatterns = [
    path("sites/<int:pk>/export-cartridge/", export_cartridge, name="site-export-cartridge"),
    path("sites/<int:pk>/import-content/", import_content, name="site-import-content"),
]
