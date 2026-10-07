"""Lecture video is prepared, and captions written, by the job worker (Procrastinate), never in a request."""

import logging

from procrastinate.contrib.django import app

log = logging.getLogger(__name__)


@app.task(name="video.convert", queue="video")
def convert_video(video_id: int) -> str:
    from video.convert import convert
    from video.models import Video

    video = Video.objects.filter(pk=video_id).select_related("item__module__site").first()
    if video is None:
        return "gone"
    video = convert(video)
    _tell(video)
    log.info("video.convert %s: %s", video_id, video.status)
    return video.status


@app.task(name="video.transcribe", queue="video")
def transcribe_video(video_id: int, language: str = "en") -> str:
    from video.models import Video
    from video.transcribe import transcribe

    video = Video.objects.filter(pk=video_id).first()
    if video is None:
        return "gone"
    video = transcribe(video, language)
    log.info("video.transcribe %s: %s", video_id, video.transcription)
    return video.transcription


def _tell(video) -> None:
    """The lecturer who put the video up hears when it is ready, or why it could not be prepared."""
    from notifications.services import notify
    from video.models import Video

    if video.created_by is None or video.status not in (Video.Status.READY, Video.Status.FAILED):
        return
    item = video.item
    ready = video.status == Video.Status.READY
    notify(
        [video.created_by],
        title=f"{'Ready' if ready else 'Not prepared'}: {item.title}",
        body="Students can now watch it." if ready else video.failure,
        link=f"/sites/{item.module.site_id}",
        dedupe_key=f"video:{video.id}:{video.status}:{int(video.updated_at.timestamp())}",
    )
