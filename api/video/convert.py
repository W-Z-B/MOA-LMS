"""Preparing a lecture video for a weak line (items 4.06, 4.07; ADR 0015).

FFmpeg, built with LGPL components only (api/Dockerfile), runs as a separate program: never linked into
the product, never given a network address. From the one file the lecturer put up it makes

- a low copy, at most 240 lines high, about 300 kbit/s in all: the one phones play first and the one kept
  for offline reading (item 4.03);
- a standard copy, at most VIDEO_STANDARD_HEIGHT lines (480 by default; 720 if GSA's line allows);
- a copy with sound only, AAC at 64 kbit/s, mono (item 4.07: under 128 kbit/s);
- a poster frame, a JPEG still shown before the video plays.

A copy is never made taller than the original. Each copy's size is counted against the site's storage
allowance. The original is then removed unless VIDEO_KEEP_ORIGINAL is set.
"""

import json
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.db import transaction
from django.utils import timezone

from video.models import Rendition, Video

log = logging.getLogger(__name__)

# quality -> (most lines, video kbit/s, sound kbit/s); the standard copy's lines are VIDEO_STANDARD_HEIGHT.
VIDEO_COPIES = {
    Rendition.Quality.LOW: (240, 250, 48),
    Rendition.Quality.STANDARD: (None, 900, 96),
}
AUDIO_KBPS = 64


class ConversionError(Exception):
    """Why a video could not be prepared, in words for the lecturer."""


@dataclass(frozen=True)
class Probe:
    duration: float
    width: int
    height: int
    has_audio: bool


def run(args: list[str], timeout: int) -> subprocess.CompletedProcess:
    """Run FFmpeg or FFprobe, never through a shell. A missing program or a timeout is a ConversionError."""
    try:
        # A fixed program with arguments the LMS builds itself: no shell, nothing a person typed.
        done = subprocess.run(args, capture_output=True, timeout=timeout, check=False)  # noqa: S603
    except FileNotFoundError as error:
        raise ConversionError(
            "The video converter is not installed on the server. Ask the LMS administrator to install it."
        ) from error
    except subprocess.TimeoutExpired as error:
        raise ConversionError("Preparing the video took too long. Try a shorter recording.") from error
    if done.returncode != 0:
        log.warning(
            "%s failed: %s", Path(args[0]).name, (done.stderr or b"")[-2000:].decode("utf-8", "replace")
        )
    return done


def probe(path: Path) -> Probe:
    """What FFprobe reads in a file: its length, its picture's size and whether it has sound."""
    args = [settings.FFPROBE_PATH, "-v", "error", "-print_format", "json", "-show_format", "-show_streams"]
    done = run([*args, str(path)], timeout=120)
    try:
        info = json.loads(done.stdout or b"{}")
    except ValueError:
        info = {}
    streams = info.get("streams") or []
    picture = next((s for s in streams if s.get("codec_type") == "video"), None)
    if done.returncode != 0 or picture is None:
        raise ConversionError(
            "This file is not a video the converter can read. Save it as MP4 and try again."
        )
    try:
        duration = float((info.get("format") or {}).get("duration") or picture.get("duration") or 0)
    except ValueError:
        duration = 0.0
    return Probe(
        duration=duration,
        width=int(picture.get("width") or 0),
        height=int(picture.get("height") or 0),
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
    )


def lines(limit: int, source: int) -> int:
    """A copy's height: never more than the source's, and even, as H.264 needs."""
    return max(2, (min(limit, source or limit) // 2) * 2)


def video_args(source: Path, target: Path, height: int, video_kbps: int, audio_kbps: int) -> list[str]:
    return [
        settings.FFMPEG_PATH,
        "-nostdin",
        "-y",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-vf",
        f"scale=-2:{height}",
        "-c:v",
        "libopenh264",
        "-b:v",
        f"{video_kbps}k",
        "-c:a",
        "aac",
        "-b:a",
        f"{audio_kbps}k",
        "-ac",
        "1" if audio_kbps < 64 else "2",
        "-movflags",
        "+faststart",
        str(target),
    ]


def audio_args(source: Path, target: Path) -> list[str]:
    return [
        settings.FFMPEG_PATH,
        "-nostdin",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-map",
        "0:a:0",
        "-c:a",
        "aac",
        "-b:a",
        f"{AUDIO_KBPS}k",
        "-ac",
        "1",
        "-movflags",
        "+faststart",
        str(target),
    ]


def poster_args(source: Path, target: Path, at: float, height: int) -> list[str]:
    return [
        settings.FFMPEG_PATH,
        "-nostdin",
        "-y",
        "-ss",
        f"{at:.2f}",
        "-i",
        str(source),
        "-frames:v",
        "1",
        "-vf",
        f"scale=-2:{height}",
        "-q:v",
        "5",
        str(target),
    ]


def _make(args: list[str], target: Path, what: str) -> None:
    done = run(args, timeout=settings.VIDEO_CONVERT_TIMEOUT_SECONDS)
    if done.returncode != 0 or not target.exists() or target.stat().st_size == 0:
        raise ConversionError(f"The {what} could not be made from this file. Save it as MP4 and try again.")


def _keep(video: Video, quality: str, path: Path, duration: float, info: Probe | None) -> Rendition:
    size = path.stat().st_size
    rendition = Rendition(
        video=video,
        quality=quality,
        size=size,
        width=info.width if info else None,
        height=info.height if info else None,
        bitrate_kbps=round(size * 8 / 1000 / duration) if duration else None,
    )
    with path.open("rb") as handle:
        rendition.file.save(f"{quality}{path.suffix}", File(handle), save=False)
    rendition.save()
    return rendition


def convert(video: Video) -> Video:
    """Make the copies and the poster frame. Marks the video ready, or failed with the reason in words."""
    video.status, video.failure = Video.Status.CONVERTING, ""
    video.save(update_fields=["status", "failure", "updated_at"])
    work = Path(tempfile.mkdtemp(prefix="gsa-video-"))
    try:
        if not video.original:
            raise ConversionError(
                "The file that was put up is no longer on the server. Put the video up again."
            )
        source = work / f"original{Path(video.original.name).suffix.lower() or '.mp4'}"
        with video.original.open("rb") as handle, source.open("wb") as out:
            shutil.copyfileobj(handle, out)
        info = probe(source)
        made: list[tuple[str, Path]] = []
        for quality, (limit, video_kbps, audio_kbps) in VIDEO_COPIES.items():
            height = lines(limit or settings.VIDEO_STANDARD_HEIGHT, info.height)
            target = work / f"{quality}.mp4"
            _make(video_args(source, target, height, video_kbps, audio_kbps), target, f"{quality} copy")
            made.append((quality, target))
        if info.has_audio:
            target = work / "audio.m4a"
            _make(audio_args(source, target), target, "copy with sound only")
            made.append((Rendition.Quality.AUDIO, target))
        poster = work / "poster.jpg"
        at = min(5.0, info.duration / 3) if info.duration else 0.0
        height = lines(settings.VIDEO_STANDARD_HEIGHT, info.height)
        _make(poster_args(source, poster, at, height), poster, "poster frame")
        copies = [(q, p, probe(p) if q != Rendition.Quality.AUDIO else None) for q, p in made]
        with transaction.atomic():
            for earlier in video.renditions.all():
                earlier.delete()  # its file goes once this commits (video.signals)
            for quality, path, copy_info in copies:
                _keep(video, quality, path, info.duration, copy_info)
            if video.poster:
                video.poster.delete(save=False)
            with poster.open("rb") as handle:
                video.poster.save("poster.jpg", File(handle), save=False)
            video.poster_size = poster.stat().st_size
            if not settings.VIDEO_KEEP_ORIGINAL:
                video.original.delete(save=False)
            video.duration_seconds = round(info.duration) if info.duration else None
            video.status, video.converted_at = Video.Status.READY, timezone.now()
            video.save()
            count(video)
    except ConversionError as error:
        video.status, video.failure = Video.Status.FAILED, str(error)
        video.save(update_fields=["status", "failure", "updated_at"])
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return video


def count(video: Video) -> None:
    """The item's size is everything the video keeps, so the storage allowance counts it (item 2.20)."""
    item = video.item
    item.file_size = video.total_size()
    item.save(update_fields=["file_size", "updated_at"])
