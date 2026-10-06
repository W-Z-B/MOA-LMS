"""A video copied with its item, to a new term (item 2.18) or as a duplicate (item 2.15): every copy, the
poster and the captions are stored again, so removing one course's video never takes another's."""

from django.core.files import File

from video.models import CaptionTrack, Rendition, Video


def _copy_file(source, target, name: str) -> None:
    with source.open("rb") as handle:
        target.save(name, File(handle), save=False)


def copy_video(source_item, target_item, user) -> Video | None:
    """Copy source_item's video onto target_item. Returns the new video, or None when there is none."""
    video = Video.objects.filter(item=source_item).first()
    if video is None:
        return None
    copy = Video(
        item=target_item,
        original_name=video.original_name,
        original_size=video.original_size,
        status=video.status,
        failure=video.failure,
        duration_seconds=video.duration_seconds,
        poster_size=video.poster_size,
        converted_at=video.converted_at,
        created_by=user,
        updated_by=user,
    )
    if video.original:
        _copy_file(video.original, copy.original, video.original_name or "video.mp4")
    if video.poster:
        _copy_file(video.poster, copy.poster, "poster.jpg")
    copy.save()
    for rendition in video.renditions.all():
        new = Rendition(
            video=copy,
            quality=rendition.quality,
            size=rendition.size,
            width=rendition.width,
            height=rendition.height,
            bitrate_kbps=rendition.bitrate_kbps,
        )
        _copy_file(rendition.file, new.file, rendition.file.name.rsplit("/", 1)[-1])
        new.save()
    for track in video.captions.all():
        CaptionTrack.objects.create(
            video=copy,
            language=track.language,
            label=track.label,
            text=track.text,
            source=track.source,
            created_by=user,
            updated_by=user,
        )
    if copy.status != Video.Status.READY and copy.original:
        # Not prepared yet where it came from: the copy is prepared on its own.
        from django.db import transaction

        from video.tasks import convert_video

        copy.status, copy.failure = Video.Status.WAITING, ""
        copy.save(update_fields=["status", "failure"])
        transaction.on_commit(lambda: convert_video.defer(video_id=copy.id))
    return copy
