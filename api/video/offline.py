"""Reading a module offline (item 4.03; ADR 0011, point 4).

The phone asks what a module needs before it keeps anything, so the space it will take is shown first:
the module's pages, its documents and the pictures its pages show, and each video in the low copy with
its poster frame and captions. The app keeps these addresses in the signed-in person's own cache
(web/public/sw.js) and reads them back when there is no signal. Only what the person may see now is
listed: released, published, not under review. Links leave the LMS, so they are listed as left out.

The addresses are the ones the app reads them by; the app adds offline=1 when it fetches them, so keeping
a module records no progress (courses.api.for_offline).
"""

from django.shortcuts import get_object_or_404
from django.urls import path
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.serializers import ErrorSerializer
from courses import release, richtext
from courses.access import visible_sites
from courses.api import items_for
from courses.models import ContentItem, Module
from video.models import Rendition, Video

# A rough allowance for each piece of JSON kept with the files: a module's text, never its weight.
DATA_BYTES = 4 * 1024


class OfflineFileSerializer(serializers.Serializer):
    url = serializers.CharField(help_text="The address the app reads it by, under /api/v1")
    kind = serializers.ChoiceField(
        choices=["data", "page", "document", "picture", "video", "poster", "captions"]
    )
    title = serializers.CharField()
    size = serializers.IntegerField(help_text="Bytes; for data and pages an estimate")


class OfflineModuleSerializer(serializers.Serializer):
    module = serializers.IntegerField()
    title = serializers.CharField()
    site = serializers.IntegerField()
    site_title = serializers.CharField()
    files = OfflineFileSerializer(many=True)
    total_bytes = serializers.IntegerField(help_text="What keeping the module offline takes, shown first")
    left_out = serializers.ListField(
        child=serializers.CharField(), help_text="Items that cannot be read offline: links, videos not ready"
    )


def _entry(url: str, kind: str, title: str, size: int) -> dict:
    return {"url": url, "kind": kind, "title": title, "size": size}


def manifest(request, module: Module) -> dict:
    items = list(items_for(request).filter(module=module).order_by("position", "id"))
    site = module.site
    files = [
        _entry("/auth/me/", "data", "Who is signed in", DATA_BYTES),
        _entry(f"/sites/{site.id}/contents/", "data", site.title, DATA_BYTES),
    ]
    left_out = []
    pictures = set()
    for item in items:
        if item.kind == ContentItem.Kind.PAGE:
            files.append(
                _entry(f"/content/{item.id}/", "page", item.title, len(item.body.encode()) + DATA_BYTES)
            )
            pictures |= richtext.image_item_ids(item.body)
        elif item.kind == ContentItem.Kind.FILE and item.file:
            files.append(_entry(f"/content/{item.id}/download/", "document", item.title, item.file_size))
        elif item.kind == ContentItem.Kind.VIDEO:
            entries = _video(item)
            if entries:
                files.extend(entries)
            else:
                left_out.append(item.title)
        else:
            left_out.append(item.title)
    shown = {i.id for i in items}
    # Pictures on the module's pages that live elsewhere on the course, and that the person may open.
    for picture in items_for(request).filter(id__in=pictures - shown, module__site=site).exclude(file=""):
        files.append(_entry(f"/content/{picture.id}/download/", "picture", picture.title, picture.file_size))
    return {
        "module": module.id,
        "title": module.title,
        "site": site.id,
        "site_title": site.title,
        "files": files,
        "total_bytes": sum(f["size"] for f in files),
        "left_out": left_out,
    }


def _video(item: ContentItem) -> list[dict]:
    video = Video.objects.filter(item=item, status=Video.Status.READY).first()
    low = video.renditions.filter(quality=Rendition.Quality.LOW).first() if video else None
    if low is None:
        return []
    entries = [
        _entry(f"/videos/{item.id}/", "data", item.title, DATA_BYTES),
        _entry(f"/videos/{item.id}/play/low/", "video", item.title, low.size),
    ]
    if video.poster:
        entries.append(_entry(f"/videos/{item.id}/poster/", "poster", item.title, video.poster_size))
    for track in video.captions.all():
        size = len(track.text.encode())
        entries.append(_entry(f"/videos/{item.id}/captions/{track.language}/", "captions", track.label, size))
    return entries


@extend_schema(
    responses={200: OfflineModuleSerializer, 404: ErrorSerializer},
    summary="What keeping a module to read offline takes, and the addresses to keep (item 4.03)",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def offline_module(request, pk: int):
    module = get_object_or_404(
        Module.objects.select_related("site"), pk=pk, site__in=visible_sites(request.user)
    )
    if module.id in release.hidden_modules(request, Module.objects.filter(pk=module.pk)):
        return Response({"code": "not_found", "detail": "No such module."}, status=404)
    return Response(manifest(request, module))


urlpatterns = [path("offline/modules/<int:pk>/", offline_module, name="offline-module")]
