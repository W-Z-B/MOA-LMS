"""Lecture video (items 4.06, 4.07): put up once, prepared by the job worker, played in the quality the
student chooses, with captions put up, corrected in the browser, or written on GSA's own server.

A video is a content item of kind "video" and is reached by the item's id: whoever may see the item may
play it, under the same rules (published, released, not under review; drafts only for teaching staff).
"""

import re
from pathlib import PurePath

from django.conf import settings
from django.db import transaction
from django.http import FileResponse, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from audit.services import record, snapshot
from core.serializers import ErrorSerializer
from core.uploads import original_name
from courses import storage
from courses.access import can_teach, person_of, site_role
from courses.api import ContentItemSerializer, for_offline, items_for
from courses.models import ContentItem, ItemCompletion, Membership
from courses.release import complete as record_progress
from video import captions, transcribe
from video.models import CaptionTrack, Rendition, Video
from video.serializers import VideoInfoSerializer, describe

EXTENSIONS = {".mp4", ".m4v", ".mov", ".webm", ".mkv", ".3gp"}
LANGUAGE = r"[a-z]{2,3}(?:-[A-Za-z]{2,4})?"
CHUNK = 256 * 1024
RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


def looks_like_video(upload) -> bool:
    """MP4, QuickTime and 3GP files start with an ftyp box; WebM and Matroska with an EBML header. FFprobe
    then reads the whole file in the job worker, which refuses anything that is not a video."""
    upload.seek(0)
    head = upload.read(16)
    upload.seek(0)
    return head[4:8] == b"ftyp" or head.startswith(b"\x1a\x45\xdf\xa3")


class VideoUploadSerializer(serializers.Serializer):
    """What the lecturer sends: the item's details, as for any content item, and the video file."""

    module = serializers.IntegerField(help_text="The module it goes in; you must teach on its course")
    title = serializers.CharField(max_length=160)
    file = serializers.FileField(
        help_text="MP4, MOV, WebM, MKV or 3GP, at most UPLOAD_LIMIT_VIDEO_MB (1024 MB by default), within "
        "the site's storage allowance"
    )
    licence = serializers.ChoiceField(choices=ContentItem.Licence.choices)
    open_licence = serializers.ChoiceField(choices=ContentItem.OpenLicence.choices, required=False)
    source = serializers.CharField(required=False, allow_blank=True)
    is_published = serializers.BooleanField(required=False, default=True)
    available_from = serializers.DateTimeField(required=False, allow_null=True)

    def validate_file(self, upload):
        limit = settings.UPLOAD_LIMIT_VIDEO_MB
        if upload.size > limit * 1024 * 1024:
            raise serializers.ValidationError(f"The video is larger than {limit} MB.")
        if PurePath(upload.name).suffix.lower() not in EXTENSIONS:
            raise serializers.ValidationError("Send a video: MP4, MOV, WebM, MKV or 3GP.")
        if not looks_like_video(upload):
            raise serializers.ValidationError(
                "The file's contents do not match its name. Save it again as MP4 and send that."
            )
        return upload


class CaptionUploadSerializer(serializers.Serializer):
    file = serializers.FileField(help_text="A WebVTT (.vtt) captions file, at most 1 MB")
    language = serializers.RegexField(f"^{LANGUAGE}$", default="en", help_text="A language tag: en, es, pt")
    label = serializers.CharField(max_length=60, required=False, help_text="How the player names them")


class CueSerializer(serializers.Serializer):
    start = serializers.FloatField(min_value=0, help_text="Seconds from the start")
    end = serializers.FloatField(min_value=0)
    text = serializers.CharField(allow_blank=True, max_length=captions.MAX_CUE_CHARS)


class CuesSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=60, required=False)
    cues = CueSerializer(many=True)


class TranscribeSerializer(serializers.Serializer):
    language = serializers.ChoiceField(choices=list(transcribe.LANGUAGES.items()), default="en")


def _later(task, **kwargs) -> None:
    """Hand work to the job worker once the change is committed."""
    transaction.on_commit(lambda: task.defer(**kwargs))


def stream(request, field, content_type: str) -> HttpResponse:
    """A stored file, whole or the byte range asked for, so a player can seek without fetching it all."""
    size = field.size
    match = RANGE.match(request.headers.get("Range", "").strip())
    if not match or not (match.group(1) or match.group(2)):
        response = FileResponse(field.open("rb"), content_type=content_type)
    else:
        first, last = match.groups()
        if first:
            start, end = int(first), min(int(last), size - 1) if last else size - 1
        else:
            start, end = max(size - int(last), 0), size - 1
        if start >= size or start > end:
            response = HttpResponse(status=416)
            response["Content-Range"] = f"bytes */{size}"
            return response
        handle = field.open("rb")
        handle.seek(start)
        length = end - start + 1

        def chunks():
            left = length
            try:
                while left > 0:
                    data = handle.read(min(CHUNK, left))
                    if not data:
                        break
                    left -= len(data)
                    yield data
            finally:
                handle.close()

        response = StreamingHttpResponse(chunks(), status=206, content_type=content_type)
        response["Content-Range"] = f"bytes {start}-{end}/{size}"
        response["Content-Length"] = str(length)
    response["Accept-Ranges"] = "bytes"
    response["Cache-Control"] = "private, max-age=3600"
    return response


PLAY_TYPES = {Rendition.Quality.AUDIO: "audio/mp4"}
NOT_READY = {"code": "not_ready", "detail": "The video is still being prepared. Try again in a few minutes."}


class VideoViewSet(viewsets.GenericViewSet):
    """Videos by the id of their content item."""

    lookup_field = "item"
    lookup_value_regex = r"\d+"
    serializer_class = VideoInfoSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        return Video.objects.filter(item__in=items_for(self.request)).select_related("item__module__site")

    def _video(self) -> Video:
        return get_object_or_404(self.get_queryset(), item_id=self.kwargs["item"])

    def _taught(self) -> Video:
        video = self._video()
        if not can_teach(self.request.user, video.item.module.site):
            raise PermissionDenied("Only the course's teaching staff can do this.")
        return video

    def _info(self, video: Video) -> dict:
        return describe(video.item, teaching=can_teach(self.request.user, video.item.module.site))

    @extend_schema(
        request={"multipart/form-data": VideoUploadSerializer},
        responses={201: ContentItemSerializer, 400: OpenApiTypes.OBJECT, 403: ErrorSerializer},
        summary="Put a lecture video up once; the copies are made by the job worker (item 4.06)",
        description="Creates a content item of kind 'video'. The low (240p), standard and sound-only copies "
        "and a poster frame follow, made by FFmpeg on GSA's server; the item's video.status says when they "
        "are ready. The original counts against the site's storage allowance until the copies replace it.",
    )
    def create(self, request):
        upload = VideoUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)
        sent = upload.validated_data
        fields = {
            key: request.data.getlist(key) if key == "groups" else request.data.get(key)
            for key in request.data.keys()
            if key != "file"
        }
        item_data = ContentItemSerializer(
            data={**fields, "kind": ContentItem.Kind.VIDEO, "is_published": sent["is_published"]},
            context={"request": request, "video_upload": True},
        )
        item_data.is_valid(raise_exception=True)
        site = item_data.validated_data["module"].site
        reason = storage.refusal(site, sent["file"].size)
        if reason:
            return Response({"file": [reason]}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            item = item_data.save(
                created_by=request.user, updated_by=request.user, file_size=sent["file"].size
            )
            video = Video(
                item=item,
                original_name=original_name(sent["file"]),
                original_size=sent["file"].size,
                created_by=request.user,
                updated_by=request.user,
            )
            video.original.save(video.original_name, sent["file"], save=False)
            video.save()
            record(request, "create", item, after=snapshot(item))
            record(request, "create", video, after=snapshot(video))
            from video.tasks import convert_video

            _later(convert_video, video_id=video.id)
        item_data._storage = storage.summary(site)
        return Response(item_data.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        responses={200: VideoInfoSerializer, 404: ErrorSerializer},
        summary="A video's state, the qualities it plays in, its poster and captions",
    )
    def retrieve(self, request, item=None):
        return Response(self._info(self._video()))

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "quality", OpenApiTypes.STR, OpenApiParameter.PATH, enum=["low", "standard", "audio"]
            ),
            OpenApiParameter(
                "Range", OpenApiTypes.STR, OpenApiParameter.HEADER, description="bytes=start-end"
            ),
            OpenApiParameter("offline", OpenApiTypes.STR, enum=["1"], description="1: a copy kept offline"),
        ],
        responses={
            (200, "video/mp4"): OpenApiTypes.BINARY,
            (206, "video/mp4"): OpenApiTypes.BINARY,
            404: ErrorSerializer,
            409: ErrorSerializer,
            416: OpenApiResponse(description="The range asked for is outside the file"),
        },
        summary="Play a video in one quality: low (240p), standard, or sound only (items 4.06, 4.07)",
    )
    @action(detail=True, methods=["get"], url_path=r"play/(?P<quality>low|standard|audio)")
    def play(self, request, item=None, quality=None):
        video = self._video()
        rendition = video.renditions.filter(quality=quality).first()
        if rendition is None:
            if video.status != Video.Status.READY:
                return Response(NOT_READY, status=409)
            return Response({"code": "no_copy", "detail": "There is no copy in that quality."}, status=404)
        if request.headers.get("Range", "bytes=0-").startswith("bytes=0-"):
            self._watched(video)  # the start of the video, not a seek within it
        return stream(request, rendition.file, PLAY_TYPES.get(quality, "video/mp4"))

    def _watched(self, video: Video) -> None:
        """Starting a video completes it for a student, as opening a page does (item 2.16)."""
        person = person_of(self.request.user)
        site = video.item.module.site
        if for_offline(self.request) or person is None:
            return
        if site_role(self.request.user, site) != Membership.SiteRole.STUDENT:
            return
        completion, created = record_progress(person, video.item, ItemCompletion.How.VIEWED)
        if created:
            record(self.request, "create", completion, after=snapshot(completion))

    @extend_schema(
        responses={(200, "image/jpeg"): OpenApiTypes.BINARY, 404: ErrorSerializer},
        summary="The poster frame: a still shown before the video plays",
    )
    @action(detail=True, methods=["get"])
    def poster(self, request, item=None):
        video = self._video()
        if not video.poster:
            return Response({"code": "no_poster", "detail": "The video has no poster frame yet."}, status=404)
        return stream(request, video.poster, "image/jpeg")

    @extend_schema(
        request=None,
        responses={
            202: VideoInfoSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
        summary="Prepare the video again, after it could not be prepared (teaching staff)",
    )
    @action(detail=True, methods=["post"])
    def convert(self, request, item=None):
        video = self._taught()
        if not video.original:
            return Response(
                {
                    "code": "no_original",
                    "detail": "The file that was put up is gone. Put the video up again.",
                },
                status=409,
            )
        if video.status in (Video.Status.WAITING, Video.Status.CONVERTING):
            return Response({"code": "in_hand", "detail": "The video is already being prepared."}, status=409)
        from video.tasks import convert_video

        with transaction.atomic():
            before = snapshot(video)
            video.status, video.failure, video.updated_by = Video.Status.WAITING, "", request.user
            video.save()
            record(request, "update", video, before=before, after=snapshot(video))
            _later(convert_video, video_id=video.id)
        return Response(self._info(video), status=202)

    @extend_schema(
        request={"multipart/form-data": CaptionUploadSerializer},
        responses={
            201: VideoInfoSerializer,
            400: OpenApiTypes.OBJECT,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
        summary="Put up a WebVTT captions file; it replaces the captions in that language",
    )
    @action(detail=True, methods=["post"], url_path="captions")
    def upload_captions(self, request, item=None):
        video = self._taught()
        data = CaptionUploadSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        sent = data.validated_data
        try:
            cues = captions.parse(sent["file"].read(captions.MAX_BYTES + 1))
        except captions.CaptionError as error:
            return Response({"file": [str(error)]}, status=status.HTTP_400_BAD_REQUEST)
        self._save_track(video, sent["language"], sent.get("label"), cues, CaptionTrack.Source.UPLOADED)
        return Response(self._info(video), status=status.HTTP_201_CREATED)

    def _save_track(self, video: Video, language: str, label: str | None, cues, source: str) -> CaptionTrack:
        with transaction.atomic():
            track = CaptionTrack.objects.filter(video=video, language=language).first()
            before = snapshot(track) if track else None
            if track is None:
                track = CaptionTrack(video=video, language=language, created_by=self.request.user)
            track.label = label or track.label or transcribe.LANGUAGES.get(language, language)
            if track.label.endswith(" (automatic)") and source != CaptionTrack.Source.TRANSCRIBED:
                track.label = track.label.removesuffix(" (automatic)")
            track.text, track.source, track.updated_by = captions.write(cues), source, self.request.user
            track.save()
            record(
                self.request, "update" if before else "create", track, before=before, after=snapshot(track)
            )
        return track

    def _track(self, video: Video, language: str) -> CaptionTrack:
        return get_object_or_404(CaptionTrack, video=video, language=language)

    @extend_schema(
        methods=["GET"],
        responses={(200, "text/vtt"): OpenApiTypes.STR, 404: ErrorSerializer},
        summary="Captions in one language, as WebVTT for the player",
    )
    @extend_schema(
        methods=["DELETE"],
        responses={204: None, 403: ErrorSerializer, 404: ErrorSerializer},
        summary="Remove the captions in one language (teaching staff)",
    )
    @action(detail=True, methods=["get", "delete"], url_path=rf"captions/(?P<language>{LANGUAGE})")
    def captions_file(self, request, item=None, language=None):
        if request.method == "DELETE":
            video = self._taught()
            track = self._track(video, language)
            with transaction.atomic():
                before, entity_id = snapshot(track), track.pk
                track.delete()
                record(request, "delete", track, before=before, entity_id=entity_id)
            return Response(status=204)
        track = self._track(self._video(), language)
        response = HttpResponse(track.text, content_type="text/vtt; charset=utf-8")
        response["Cache-Control"] = "private, max-age=300"
        return response

    @extend_schema(
        methods=["GET"],
        responses={200: CuesSerializer, 404: ErrorSerializer},
        summary="Captions in one language as cues, for correcting them in the browser",
    )
    @extend_schema(
        methods=["PUT"],
        request=CuesSerializer,
        responses={200: CuesSerializer, 400: OpenApiTypes.OBJECT, 403: ErrorSerializer, 404: ErrorSerializer},
        summary="Save captions written or corrected in the browser (teaching staff); creates them if new",
    )
    @action(detail=True, methods=["get", "put"], url_path=rf"captions/(?P<language>{LANGUAGE})/cues")
    def cues(self, request, item=None, language=None):
        if request.method == "PUT":
            video = self._taught()
            data = CuesSerializer(data=request.data)
            data.is_valid(raise_exception=True)
            try:
                cues = captions.from_rows(data.validated_data["cues"])
            except captions.CaptionError as error:
                return Response({"cues": [str(error)]}, status=status.HTTP_400_BAD_REQUEST)
            track = self._save_track(
                video, language, data.validated_data.get("label"), cues, CaptionTrack.Source.EDITED
            )
        else:
            track = self._track(self._video(), language)
        return Response({"label": track.label, "cues": [c.as_dict() for c in captions.parse(track.text)]})

    @extend_schema(
        request=TranscribeSerializer,
        responses={
            202: VideoInfoSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
        summary="Write captions automatically on GSA's own server (off unless the LMS is set up for it)",
        description="Runs a speech-to-text program (whisper.cpp) on the LMS server through the job worker. "
        "The sound never leaves the server. The lecturer then corrects the captions.",
    )
    @action(detail=True, methods=["post"])
    def transcribe(self, request, item=None):
        video = self._taught()
        if not transcribe.available():
            return Response(
                {"code": "not_available", "detail": "Automatic captions are not switched on for this LMS."},
                status=409,
            )
        data = TranscribeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        language = data.validated_data["language"]
        if video.status != Video.Status.READY:
            return Response(NOT_READY, status=409)
        if video.transcription in (Video.Transcription.WAITING, Video.Transcription.WORKING):
            return Response({"code": "in_hand", "detail": "Captions are already being written."}, status=409)
        if video.captions.filter(language=language).exclude(source=CaptionTrack.Source.TRANSCRIBED).exists():
            return Response(
                {
                    "code": "captions_exist",
                    "detail": "This video already has captions in that language. Correct them, or remove "
                    "them first.",
                },
                status=409,
            )
        from video.tasks import transcribe_video

        with transaction.atomic():
            before = snapshot(video)
            video.transcription, video.transcription_failure = Video.Transcription.WAITING, ""
            video.updated_by = request.user
            video.save()
            record(request, "update", video, before=before, after=snapshot(video))
            _later(transcribe_video, video_id=video.id, language=language)
        return Response(self._info(video), status=202)


router = DefaultRouter()
router.register("videos", VideoViewSet, basename="video")
urlpatterns = router.urls
