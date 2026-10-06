"""How a lecture video is described with its content item (ContentItemSerializer.video) and on its own."""

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers

from video import transcribe
from video.models import CaptionTrack, Rendition, Video

QUALITY_ORDER = [Rendition.Quality.LOW, Rendition.Quality.STANDARD, Rendition.Quality.AUDIO]


class QualitySerializer(serializers.Serializer):
    quality = serializers.ChoiceField(choices=Rendition.Quality.choices)
    label = serializers.CharField()
    size = serializers.IntegerField(help_text="Bytes: what playing it all, or keeping it offline, costs")
    width = serializers.IntegerField(allow_null=True)
    height = serializers.IntegerField(allow_null=True)
    bitrate_kbps = serializers.IntegerField(allow_null=True)
    url = serializers.CharField(help_text="Streams the copy; supports Range requests for seeking")


class CaptionSerializer(serializers.Serializer):
    language = serializers.CharField()
    label = serializers.CharField()
    source = serializers.ChoiceField(choices=CaptionTrack.Source.choices)
    url = serializers.CharField(help_text="The captions as a WebVTT file, for the player's track")


class VideoInfoSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Video.Status.choices)
    status_label = serializers.CharField()
    failure = serializers.CharField(
        allow_null=True, help_text="Why it could not be prepared; teaching staff only"
    )
    duration_seconds = serializers.IntegerField(allow_null=True)
    qualities = QualitySerializer(many=True, help_text="Lowest first: phones play the first by default")
    poster_url = serializers.CharField(allow_null=True)
    poster_size = serializers.IntegerField()
    captions = CaptionSerializer(many=True)
    transcription = serializers.ChoiceField(
        choices=Video.Transcription.choices, allow_null=True, help_text="Teaching staff only"
    )
    transcription_failure = serializers.CharField(allow_null=True)
    can_transcribe = serializers.BooleanField(
        help_text="Whether automatic captions can be asked for: by teaching staff, when "
        "VIDEO_TRANSCRIBE_COMMAND is set"
    )


def describe(item, *, teaching: bool) -> dict | None:
    """The video of a content item as VideoInfoSerializer describes it, or None when it has none."""
    try:
        video: Video = item.video
    except ObjectDoesNotExist:
        return None
    base = f"/api/v1/videos/{item.id}"
    renditions = {r.quality: r for r in video.renditions.all()}
    qualities = [
        {
            "quality": quality,
            "label": _label(renditions[quality]),
            "size": renditions[quality].size,
            "width": renditions[quality].width,
            "height": renditions[quality].height,
            "bitrate_kbps": renditions[quality].bitrate_kbps,
            "url": f"{base}/play/{quality}/",
        }
        for quality in QUALITY_ORDER
        if quality in renditions
    ]
    return {
        "status": video.status,
        "status_label": video.get_status_display(),
        "failure": (video.failure or None) if teaching else None,
        "duration_seconds": video.duration_seconds,
        "qualities": qualities,
        "poster_url": f"{base}/poster/" if video.poster else None,
        "poster_size": video.poster_size,
        "captions": [
            {
                "language": track.language,
                "label": track.label,
                "source": track.source,
                "url": f"{base}/captions/{track.language}/",
            }
            for track in video.captions.all()
        ],
        "transcription": video.transcription if teaching else None,
        "transcription_failure": (video.transcription_failure or None) if teaching else None,
        "can_transcribe": teaching and transcribe.available(),
    }


def _label(rendition: Rendition) -> str:
    if rendition.quality == Rendition.Quality.AUDIO:
        return "Sound only"
    lines = f" ({rendition.height}p)" if rendition.height else ""
    return f"{'Low' if rendition.quality == Rendition.Quality.LOW else 'Standard'}{lines}"
