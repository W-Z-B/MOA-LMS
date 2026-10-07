"""Captions written by speech recognition on GSA's own server (ADR 0015, point 3). Off by default.

When VIDEO_TRANSCRIBE_COMMAND is set, it names a whisper.cpp command-line program (MIT) installed on the
server with its model, for example

    VIDEO_TRANSCRIBE_COMMAND="/opt/whisper/whisper-cli -m /opt/whisper/ggml-base.en.bin -t 4"

The LMS adds the language, the sound file and where to write the captions
(`-l en -f <file.wav> -ovtt -of <name>`), and reads <name>.vtt back. The sound is made with the LMS's own
FFmpeg (16 kHz, mono) and never leaves the server: nothing here opens a network connection, and no outside
speech service is ever called. The lecturer then corrects the text in the browser.
"""

import shlex
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.db import transaction

from video import captions
from video.convert import ConversionError, run
from video.models import CaptionTrack, Rendition, Video

LANGUAGES = {"en": "English", "es": "Spanish", "pt": "Portuguese", "fr": "French", "nl": "Dutch"}


def available() -> bool:
    return bool((settings.VIDEO_TRANSCRIBE_COMMAND or "").strip())


def _sound_source(video: Video):
    """The smallest file with the lecture's sound: the sound-only copy, the low copy, or the original."""
    for quality in (Rendition.Quality.AUDIO, Rendition.Quality.LOW):
        rendition = video.renditions.filter(quality=quality).first()
        if rendition:
            return rendition.file
    return video.original or None


def transcribe(video: Video, language: str = "en") -> Video:
    """Write captions in `language` with the configured program. Marks the request done or failed."""
    video.transcription, video.transcription_failure = Video.Transcription.WORKING, ""
    video.save(update_fields=["transcription", "transcription_failure", "updated_at"])
    work = Path(tempfile.mkdtemp(prefix="gsa-captions-"))
    try:
        if not available():
            raise ConversionError("Automatic captions are not switched on for this LMS.")
        source_field = _sound_source(video)
        if not source_field:
            raise ConversionError("The video has no sound to write captions from.")
        source = work / f"source{Path(source_field.name).suffix}"
        with source_field.open("rb") as handle, source.open("wb") as out:
            shutil.copyfileobj(handle, out)
        sound = work / "sound.wav"
        made = run(
            [settings.FFMPEG_PATH, "-nostdin", "-y", "-i", str(source), "-vn", "-ac", "1", "-ar", "16000",
             "-c:a", "pcm_s16le", str(sound)],
            timeout=settings.VIDEO_CONVERT_TIMEOUT_SECONDS,
        )  # fmt: skip
        if made.returncode != 0 or not sound.exists():
            raise ConversionError("The sound could not be taken from the video.")
        base = work / "captions"
        command = [*shlex.split(settings.VIDEO_TRANSCRIBE_COMMAND), "-l", language, "-f", str(sound)]
        done = run([*command, "-ovtt", "-of", str(base)], timeout=settings.VIDEO_TRANSCRIBE_TIMEOUT_SECONDS)
        written = base.with_suffix(".vtt")
        if done.returncode != 0 or not written.exists():
            raise ConversionError("Speech recognition did not finish. Put a captions file up instead.")
        try:
            cues = captions.parse(written.read_bytes())
        except captions.CaptionError as error:
            raise ConversionError("Speech recognition found no speech to caption.") from error
        with transaction.atomic():
            CaptionTrack.objects.update_or_create(
                video=video,
                language=language,
                defaults={
                    "label": f"{LANGUAGES.get(language, language)} (automatic)",
                    "text": captions.write(cues),
                    "source": CaptionTrack.Source.TRANSCRIBED,
                },
            )
            video.transcription = Video.Transcription.DONE
            video.save(update_fields=["transcription", "updated_at"])
    except ConversionError as error:
        video.transcription, video.transcription_failure = Video.Transcription.FAILED, str(error)
        video.save(update_fields=["transcription", "transcription_failure", "updated_at"])
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return video
