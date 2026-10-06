"""Lecture video (items 4.06, 4.07): put up once, prepared by FFmpeg, played in the quality the student
chooses, captioned, copied with its course, and counted against the storage allowance."""

import shutil
import subprocess
from pathlib import Path

import pytest
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile

from audit.models import AuditLog
from courses.models import ContentItem, ItemCompletion, Module
from video import convert, tasks
from video.models import CaptionTrack, Rendition, Video

FIXTURES = Path(__file__).parent / "fixtures"
LECTURE = (FIXTURES / "lecture.mp4").read_bytes()
POSTER = (FIXTURES / "poster.jpg").read_bytes()
VTT = b"WEBVTT\n\n00:00:00.000 --> 00:00:01.500\nWelcome to soils.\n"
has_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="FFmpeg is installed in the API image"
)


@pytest.fixture
def module(site):
    return Module.objects.create(site=site, title="Week 1", position=1)


@pytest.fixture
def teacher(lecturer, client_for):
    return client_for(lecturer.user)


@pytest.fixture
def learner(student, client_for):
    return client_for(student.user)


@pytest.fixture
def deferred(monkeypatch):
    """Jobs handed to the worker, instead of the worker."""
    jobs = []
    monkeypatch.setattr(tasks.convert_video, "defer", lambda **kw: jobs.append(("convert", kw)))
    monkeypatch.setattr(tasks.transcribe_video, "defer", lambda **kw: jobs.append(("transcribe", kw)))
    return jobs


def mp4(name="lecture.mp4", data=LECTURE):
    return SimpleUploadedFile(name, data, content_type="video/mp4")


def put_up(client, module, **extra):
    data = {"module": module.id, "title": "Soil profiles", "file": mp4(), "licence": "gsa_own", **extra}
    return client.post("/api/v1/videos/", data, format="multipart")


def ready_video(module, *, title="Soil profiles", published=True) -> Video:
    """A video as the worker leaves it: the copies, a poster frame and no original."""
    item = ContentItem.objects.create(
        module=module, kind="video", title=title, is_published=published, file_size=0
    )
    video = Video.objects.create(item=item, status=Video.Status.READY, duration_seconds=2)
    for quality, height in (("low", 240), ("standard", 480), ("audio", None)):
        rendition = Rendition(video=video, quality=quality, size=len(LECTURE), height=height, width=None)
        rendition.file.save(f"{quality}.mp4", ContentFile(LECTURE), save=False)
        rendition.save()
    video.poster.save("poster.jpg", ContentFile(POSTER), save=False)
    video.poster_size = len(POSTER)
    video.save()
    convert.count(video)
    return video


# Putting a video up


@pytest.mark.django_db
def test_a_lecturer_puts_a_video_up_once_and_the_worker_is_asked_to_prepare_it(
    teacher, module, deferred, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        created = put_up(teacher, module)
    assert created.status_code == 201, created.content
    body = created.json()
    assert body["kind"] == "video"
    assert body["video"]["status"] == "waiting" and body["video"]["qualities"] == []
    assert body["file_size"] == len(LECTURE)  # the original counts until its copies replace it
    assert body["storage"]["used_bytes"] == len(LECTURE)
    video = Video.objects.get(item_id=body["id"])
    assert video.original_name == "lecture.mp4" and video.original_size == len(LECTURE)
    assert "video/" in video.original.name and "lecture" not in video.original.name  # random stored name
    assert deferred == [("convert", {"video_id": video.id})]
    assert AuditLog.objects.filter(entity="video.video", action="create", entity_id=video.id).exists()
    assert AuditLog.objects.filter(
        entity="courses.contentitem", action="create", entity_id=body["id"]
    ).exists()


@pytest.mark.django_db
def test_only_teaching_staff_put_videos_up_and_only_real_videos(teacher, learner, module, deferred, settings):
    assert put_up(learner, module).status_code == 403
    assert put_up(teacher, module, file=mp4("notes.pdf")).status_code == 400
    wrong = put_up(teacher, module, file=mp4("lecture.mp4", b"%PDF-1.7 not a video at all"))
    assert wrong.status_code == 400 and "do not match" in str(wrong.json())
    no_licence = teacher.post(
        "/api/v1/videos/", {"module": module.id, "title": "x", "file": mp4()}, format="multipart"
    )
    assert no_licence.status_code == 400 and "licence" in no_licence.json()
    settings.UPLOAD_LIMIT_VIDEO_MB = 0
    assert "larger than 0 MB" in str(put_up(teacher, module).json())
    settings.UPLOAD_LIMIT_VIDEO_MB = 1024
    settings.SITE_STORAGE_ALLOWANCE_MB = 0
    full = put_up(teacher, module)
    assert full.status_code == 400 and "storage allowance" in full.json()["file"][0]
    # A video item comes only with its file, through its own form.
    page = teacher.post(
        "/api/v1/content/", {"module": module.id, "kind": "video", "title": "x", "licence": "gsa_own"}
    )
    assert page.status_code == 400 and "own form" in str(page.json())
    assert not Video.objects.exists() and deferred == []


# Preparing it (FFmpeg)


@has_ffmpeg
@pytest.mark.django_db
def test_ffmpeg_makes_a_low_a_standard_and_a_sound_only_copy_and_a_poster(teacher, module, deferred):
    created = put_up(teacher, module)
    video = Video.objects.get(item_id=created.json()["id"])
    original = video.original.name
    assert tasks.convert_video(video_id=video.id) == "ready"
    video.refresh_from_db()
    copies = {r.quality: r for r in video.renditions.all()}
    assert set(copies) == {"low", "standard", "audio"}
    assert copies["low"].height == 240 and copies["standard"].height == 240  # never taller than the source
    assert copies["audio"].bitrate_kbps < 128  # item 4.07
    assert video.poster and video.poster_size > 0 and video.duration_seconds == 2
    assert not video.original and not video.original.storage.exists(original)  # the copies replace it
    item = video.item
    item.refresh_from_db()
    assert item.file_size == video.total_size() == sum(r.size for r in copies.values()) + video.poster_size
    head = convert.run(
        [convert.settings.FFPROBE_PATH, "-v", "error", "-show_entries", "stream=codec_name", "-of", "csv=p=0",
         copies["low"].file.path],
        timeout=60,
    )  # fmt: skip
    assert head.stdout.split() == [b"h264", b"aac"]
    # The lecturer hears it is ready.
    from notifications.models import Notification

    assert Notification.objects.filter(title="Ready: Soil profiles", link=f"/sites/{module.site_id}").exists()


@pytest.mark.django_db
def test_without_the_converter_or_with_a_file_it_cannot_read_the_video_fails_in_words(
    teacher, module, deferred, settings, monkeypatch
):
    video = Video.objects.get(item_id=put_up(teacher, module).json()["id"])
    settings.FFPROBE_PATH = "/nowhere/ffprobe"
    assert tasks.convert_video(video_id=video.id) == "failed"
    video.refresh_from_db()
    assert video.failure.startswith("The video converter is not installed")
    assert video.original  # kept, so it can be prepared again

    def not_a_video(args, capture_output, timeout, check):
        return subprocess.CompletedProcess(args, 1, stdout=b"{}", stderr=b"Invalid data found")

    monkeypatch.setattr(convert.subprocess, "run", not_a_video)
    convert.convert(video)
    assert video.status == "failed" and "not a video the converter can read" in video.failure

    def too_long(args, capture_output, timeout, check):
        raise subprocess.TimeoutExpired(args, timeout)

    monkeypatch.setattr(convert.subprocess, "run", too_long)
    assert "took too long" in convert.convert(video).failure
    assert tasks.convert_video(video_id=999999) == "gone"


@pytest.mark.django_db
def test_a_copy_that_cannot_be_made_fails_the_video(teacher, module, deferred, monkeypatch):
    video = Video.objects.get(item_id=put_up(teacher, module).json()["id"])
    probe = (
        b'{"format": {"duration": "2.0"}, "streams": [{"codec_type": "video", "width": 320, "height": 240}]}'
    )

    def ffmpeg(args, capture_output, timeout, check):
        if "ffprobe" in args[0]:
            return subprocess.CompletedProcess(args, 0, stdout=probe, stderr=b"")
        return subprocess.CompletedProcess(args, 1, stdout=b"", stderr=b"Unknown encoder 'libopenh264'")

    monkeypatch.setattr(convert.subprocess, "run", ffmpeg)
    convert.convert(video)
    assert video.status == "failed" and video.failure.startswith("The low copy could not be made")


@pytest.mark.django_db
def test_without_sound_there_is_no_sound_only_copy(teacher, module, deferred, monkeypatch, settings):
    video = Video.objects.get(item_id=put_up(teacher, module).json()["id"])
    settings.VIDEO_KEEP_ORIGINAL = True
    probe = (
        b'{"format": {"duration": "9"}, "streams": [{"codec_type": "video", "width": 1280, "height": 721}]}'
    )
    made = []

    def ffmpeg(args, capture_output, timeout, check):
        if "ffprobe" in args[0]:
            return subprocess.CompletedProcess(args, 0, stdout=probe, stderr=b"")
        made.append(args)
        Path(args[-1]).write_bytes(b"made")
        return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(convert.subprocess, "run", ffmpeg)
    convert.convert(video)
    assert video.status == "ready", video.failure
    assert set(video.renditions.values_list("quality", flat=True)) == {"low", "standard"}
    scales = [a[a.index("-vf") + 1] for a in made]
    assert scales == ["scale=-2:240", "scale=-2:480", "scale=-2:480"]  # low, standard, poster
    assert all("-nostdin" in a and not any(str(x).startswith("http") for x in a) for a in made)
    assert video.original  # VIDEO_KEEP_ORIGINAL
    assert video.item.file_size == video.total_size() == len(LECTURE) + 3 * 4


@pytest.mark.django_db
def test_teaching_staff_can_ask_again_after_a_failure(
    teacher, learner, module, deferred, django_capture_on_commit_callbacks
):
    video = Video.objects.get(item_id=put_up(teacher, module).json()["id"])
    url = f"/api/v1/videos/{video.item_id}/convert/"
    assert teacher.post(url).status_code == 409  # already waiting
    video.status = Video.Status.FAILED
    video.save()
    assert learner.post(url).status_code in (403, 404)
    with django_capture_on_commit_callbacks(execute=True):
        again = teacher.post(url)
    assert again.status_code == 202 and again.json()["status"] == "waiting"
    assert deferred[-1] == ("convert", {"video_id": video.id})
    video.original.delete()
    video.status = Video.Status.FAILED
    video.save()
    assert teacher.post(url).json()["code"] == "no_original"


# Playing it


@pytest.mark.django_db
def test_a_student_plays_the_quality_they_choose_and_starting_it_completes_it(learner, student, module):
    video = ready_video(module)
    listed = learner.get(f"/api/v1/sites/{module.site_id}/contents/").json()["modules"][0]["items"][0]
    info = listed["video"]
    assert [q["quality"] for q in info["qualities"]] == ["low", "standard", "audio"]  # lowest first
    assert info["qualities"][0]["label"] == "Low (240p)" and info["qualities"][2]["label"] == "Sound only"
    assert info["failure"] is None and info["transcription"] is None and info["can_transcribe"] is False
    assert listed["file_size"] == 3 * len(LECTURE) + len(POSTER)
    low = learner.get(info["qualities"][0]["url"])
    assert low.status_code == 200 and low["Content-Type"] == "video/mp4" and low["Accept-Ranges"] == "bytes"
    assert b"".join(low.streaming_content) == LECTURE
    assert ItemCompletion.objects.filter(person=student, item=video.item, how="viewed").exists()
    assert learner.get(info["qualities"][2]["url"])["Content-Type"] == "audio/mp4"
    assert learner.get(info["poster_url"])["Content-Type"] == "image/jpeg"
    assert learner.get(f"/api/v1/videos/{video.item_id}/").json()["status"] == "ready"


@pytest.mark.django_db
def test_seeking_fetches_only_the_part_asked_for(learner, module):
    video = ready_video(module)
    url = f"/api/v1/videos/{video.item_id}/play/standard/"
    part = learner.get(url, HTTP_RANGE="bytes=100-199")
    assert part.status_code == 206 and part["Content-Range"] == f"bytes 100-199/{len(LECTURE)}"
    assert b"".join(part.streaming_content) == LECTURE[100:200]
    tail = learner.get(url, HTTP_RANGE="bytes=-10")
    assert b"".join(tail.streaming_content) == LECTURE[-10:]
    rest = learner.get(url, HTTP_RANGE=f"bytes={len(LECTURE) - 5}-")
    assert rest["Content-Length"] == "5"
    beyond = learner.get(url, HTTP_RANGE=f"bytes={len(LECTURE)}-")
    assert beyond.status_code == 416 and beyond["Content-Range"] == f"bytes */{len(LECTURE)}"


@pytest.mark.django_db
def test_drafts_unprepared_videos_and_offline_copies(learner, teacher, student, module, deferred):
    draft = ready_video(module, title="Draft", published=False)
    assert learner.get(f"/api/v1/videos/{draft.item_id}/play/low/").status_code == 404
    assert teacher.get(f"/api/v1/videos/{draft.item_id}/play/low/").status_code == 200
    waiting = Video.objects.get(item_id=put_up(teacher, module).json()["id"])
    refused = learner.get(f"/api/v1/videos/{waiting.item_id}/play/low/")
    assert refused.status_code == 409 and refused.json()["code"] == "not_ready"
    assert learner.get(f"/api/v1/videos/{waiting.item_id}/poster/").status_code == 404
    ready = ready_video(module, title="Ready")
    ready.renditions.filter(quality="audio").delete()
    assert learner.get(f"/api/v1/videos/{ready.item_id}/play/audio/").json()["code"] == "no_copy"
    kept = learner.get(f"/api/v1/videos/{ready.item_id}/play/low/?offline=1")
    assert kept.status_code == 200
    assert not ItemCompletion.objects.filter(person=student, item=ready.item).exists()


# Captions


@pytest.mark.django_db
def test_a_lecturer_puts_captions_up_and_students_get_them_for_the_player(teacher, learner, module):
    video = ready_video(module)
    url = f"/api/v1/videos/{video.item_id}/captions/"
    upload = {"file": SimpleUploadedFile("soils.vtt", VTT), "language": "en"}
    assert learner.post(url, upload, format="multipart").status_code == 403
    upload["file"].seek(0)
    created = teacher.post(url, upload, format="multipart")
    assert created.status_code == 201, created.content
    assert created.json()["captions"] == [
        {"language": "en", "label": "English", "source": "uploaded", "url": f"{url}en/"}
    ]
    track = learner.get(f"{url}en/")
    assert track["Content-Type"] == "text/vtt; charset=utf-8" and b"Welcome to soils." in track.content
    bad = teacher.post(url, {"file": SimpleUploadedFile("x.vtt", b"not captions")}, format="multipart")
    assert bad.status_code == 400 and "WEBVTT" in bad.json()["file"][0]
    assert AuditLog.objects.filter(entity="video.captiontrack", action="create").count() == 1


@pytest.mark.django_db
def test_captions_are_corrected_in_the_browser_cue_by_cue(teacher, learner, module):
    video = ready_video(module)
    url = f"/api/v1/videos/{video.item_id}/captions/es/cues/"
    assert teacher.get(url).status_code == 404
    rows = {"label": "Spanish", "cues": [{"start": 0, "end": 1.25, "text": "Bienvenidos"}]}
    assert learner.put(url, rows, format="json").status_code == 403
    saved = teacher.put(url, rows, format="json")
    assert saved.status_code == 200 and saved.json() == {
        "label": "Spanish",
        "cues": [{"start": 0.0, "end": 1.25, "text": "Bienvenidos"}],
    }
    assert CaptionTrack.objects.get(video=video, language="es").source == "edited"
    assert learner.get(url).json()["cues"][0]["text"] == "Bienvenidos"
    backwards = teacher.put(url, {"cues": [{"start": 4, "end": 2, "text": "x"}]}, format="json")
    assert backwards.status_code == 400 and "end after it starts" in backwards.json()["cues"][0]
    gone = teacher.delete(f"/api/v1/videos/{video.item_id}/captions/es/")
    assert gone.status_code == 204 and not video.captions.exists()
    assert AuditLog.objects.filter(entity="video.captiontrack", action="delete").exists()


@pytest.mark.django_db
def test_automatic_captions_are_off_unless_the_server_is_set_up_for_them(teacher, module, deferred):
    video = ready_video(module)
    refused = teacher.post(f"/api/v1/videos/{video.item_id}/transcribe/", {"language": "en"}, format="json")
    assert refused.status_code == 409 and refused.json()["code"] == "not_available"
    assert deferred == []


@pytest.mark.django_db
def test_automatic_captions_run_whisper_on_gsas_own_server(
    teacher, learner, module, deferred, settings, monkeypatch, django_capture_on_commit_callbacks
):
    settings.VIDEO_TRANSCRIBE_COMMAND = "/opt/whisper/whisper-cli -m /opt/whisper/ggml-base.en.bin -t 4"
    video = ready_video(module)
    url = f"/api/v1/videos/{video.item_id}/transcribe/"
    assert teacher.get(f"/api/v1/videos/{video.item_id}/").json()["can_transcribe"] is True
    assert learner.post(url, {}, format="json").status_code == 403
    with django_capture_on_commit_callbacks(execute=True):
        asked = teacher.post(url, {"language": "en"}, format="json")
    assert asked.status_code == 202 and asked.json()["transcription"] == "waiting"
    assert deferred == [("transcribe", {"video_id": video.id, "language": "en"})]
    assert teacher.post(url, {}, format="json").json()["code"] == "in_hand"
    ran = []

    def programs(args, capture_output, timeout, check):
        ran.append(args)
        if args[0] == settings.FFMPEG_PATH:
            Path(args[-1]).write_bytes(b"RIFF")
        else:
            base = args[args.index("-of") + 1]
            Path(f"{base}.vtt").write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\n Soil is alive.\n")
        return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(convert.subprocess, "run", programs)
    assert tasks.transcribe_video(video_id=video.id, language="en") == "done"
    whisper = ran[1]
    assert whisper[:6] == ["/opt/whisper/whisper-cli", "-m", "/opt/whisper/ggml-base.en.bin", "-t", "4", "-l"]
    assert "-ovtt" in whisper and whisper[whisper.index("-f") + 1].endswith("sound.wav")
    assert ran[0][ran[0].index("-ar") + 1] == "16000"
    assert not any("http" in str(part) for args in ran for part in args)  # nothing leaves the server
    track = CaptionTrack.objects.get(video=video, language="en")
    assert track.source == "transcribed" and track.label == "English (automatic)"
    assert "Soil is alive." in track.text
    # Correcting it makes it the lecturer's; asking again would not overwrite it.
    teacher.put(
        f"/api/v1/videos/{video.item_id}/captions/en/cues/",
        {"cues": [{"start": 0, "end": 1, "text": "Soil lives."}]},
        format="json",
    )
    track.refresh_from_db()
    assert track.source == "edited" and track.label == "English"
    video.refresh_from_db()
    assert teacher.post(url, {"language": "en"}, format="json").json()["code"] == "captions_exist"
    assert tasks.transcribe_video(video_id=999999) == "gone"


@pytest.mark.django_db
def test_automatic_captions_fail_in_words(teacher, module, deferred, settings, monkeypatch):
    video = ready_video(module)
    assert tasks.transcribe_video(video_id=video.id) == "failed"  # switched off since it was asked
    settings.VIDEO_TRANSCRIBE_COMMAND = "whisper-cli -m model.bin"

    def silent(args, capture_output, timeout, check):
        if args[0] == settings.FFMPEG_PATH:
            Path(args[-1]).write_bytes(b"RIFF")
            return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")
        return subprocess.CompletedProcess(args, 1, stdout=b"", stderr=b"model not found")

    monkeypatch.setattr(convert.subprocess, "run", silent)
    assert tasks.transcribe_video(video_id=video.id) == "failed"
    video.refresh_from_db()
    assert "Put a captions file up instead" in video.transcription_failure
    video.renditions.all().delete()
    assert tasks.transcribe_video(video_id=video.id) == "failed"
    video.refresh_from_db()
    assert video.transcription_failure == "The video has no sound to write captions from."
    waiting = ready_video(module, title="Waiting")
    waiting.status = Video.Status.CONVERTING
    waiting.save()
    asked = teacher.post(f"/api/v1/videos/{waiting.item_id}/transcribe/", {}, format="json")
    assert asked.json()["code"] == "not_ready"


# Copies of the course, and housekeeping


@pytest.mark.django_db
def test_a_duplicated_video_is_stored_again_with_its_captions(teacher, module):
    video = ready_video(module)
    CaptionTrack.objects.create(video=video, text=VTT.decode())
    copied = teacher.post(f"/api/v1/content/{video.item_id}/duplicate/")
    assert copied.status_code == 201, copied.content
    copy = Video.objects.get(item_id=copied.json()["id"])
    assert copy.status == "ready" and copy.captions.count() == 1 and copy.renditions.count() == 3
    assert {r.file.name for r in copy.renditions.all()}.isdisjoint(
        {r.file.name for r in video.renditions.all()}
    )
    assert copied.json()["file_size"] == video.item.file_size
    assert copied.json()["storage"]["used_bytes"] == 2 * video.item.file_size


@pytest.mark.django_db
def test_a_new_term_copies_the_video_and_prepares_one_still_waiting(
    teacher, lecturer, module, deferred, django_capture_on_commit_callbacks
):
    from courses.models import CourseSite, Membership

    ready_video(module)
    with django_capture_on_commit_callbacks(execute=True):
        put_up(teacher, module)
    target = CourseSite.objects.create(code="AGR101-NEXT", title="Next term", is_published=True)
    Membership.objects.create(site=target, person=lecturer, role="lecturer")
    with django_capture_on_commit_callbacks(execute=True):
        done = teacher.post(
            f"/api/v1/sites/{target.id}/copy-from/", {"source": module.site_id}, format="json"
        )
    assert done.status_code == 200, done.content
    copies = Video.objects.filter(item__module__site=target)
    assert sorted(copies.values_list("status", flat=True)) == ["ready", "waiting"]
    waiting = copies.get(status="waiting")
    assert waiting.original and ("convert", {"video_id": waiting.id}) in deferred


@pytest.mark.django_db
def test_removing_a_video_removes_its_files(teacher, module, django_capture_on_commit_callbacks):
    video = ready_video(module)
    names = [r.file.name for r in video.renditions.all()] + [video.poster.name]
    storage = video.poster.storage
    with django_capture_on_commit_callbacks(execute=True):
        assert teacher.delete(f"/api/v1/content/{video.item_id}/").status_code == 204
    assert not any(storage.exists(name) for name in names)
