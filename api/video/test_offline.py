"""Keeping a module to read offline (item 4.03): what it takes is known before anything is kept, only what
the person may see is listed, and keeping it records no progress."""

from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from courses.models import ContentItem, ItemCompletion, Module
from video.models import CaptionTrack
from video.test_video import ready_video


@pytest.fixture
def module(site):
    return Module.objects.create(site=site, title="Week 1", position=1)


@pytest.fixture
def learner(student, client_for):
    return client_for(student.user)


def a_file(module, title, size=5000, **extra):
    item = ContentItem(
        module=module, kind="file", title=title, file_size=size, original_name="x.pdf", **extra
    )
    item.file.save("x.pdf", SimpleUploadedFile("x.pdf", b"%PDF-1.7 " + b"x" * size), save=False)
    item.save()
    return item


@pytest.mark.django_db
def test_the_space_a_module_takes_is_known_before_it_is_kept(learner, module):
    picture = a_file(module, "Soil horizon photo", size=2000)
    page = ContentItem.objects.create(
        module=module,
        kind="page",
        title="Soil horizons",
        body=f'<p>Layers.</p><img src="/api/v1/content/{picture.id}/download/" alt="Soil layers">',
    )
    handout = a_file(module, "Handout", size=7000)
    video = ready_video(module)
    CaptionTrack.objects.create(video=video, text="WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHi\n")
    ContentItem.objects.create(module=module, kind="link", title="Ministry guide", url="https://moa.gov.gy/")
    a_file(module, "Draft notes", is_published=False)
    ContentItem.objects.create(
        module=module, kind="page", title="Next week", available_from=timezone.now() + timedelta(days=7)
    )

    got = learner.get(f"/api/v1/offline/modules/{module.id}/")
    assert got.status_code == 200, got.content
    body = got.json()
    urls = {f["url"]: f for f in body["files"]}
    assert set(urls) == {
        "/auth/me/",
        f"/sites/{module.site_id}/contents/",
        f"/content/{page.id}/",
        f"/content/{picture.id}/download/",
        f"/content/{handout.id}/download/",
        f"/videos/{video.item_id}/",
        f"/videos/{video.item_id}/play/low/",  # the low copy only
        f"/videos/{video.item_id}/poster/",
        f"/videos/{video.item_id}/captions/en/",
    }
    assert urls[f"/content/{handout.id}/download/"]["size"] == 7000
    assert urls[f"/videos/{video.item_id}/play/low/"]["kind"] == "video"
    assert body["total_bytes"] == sum(f["size"] for f in body["files"])
    assert body["left_out"] == ["Ministry guide"]
    assert body["title"] == "Week 1" and body["site"] == module.site_id

    # Fetching them to keep records no progress.
    learner.get(f"/api/v1/content/{page.id}/?offline=1")
    learner.get(f"/api/v1/content/{handout.id}/download/?offline=1")
    assert not ItemCompletion.objects.exists()
    learner.get(f"/api/v1/content/{page.id}/")
    assert ItemCompletion.objects.filter(item=page).exists()


@pytest.mark.django_db
def test_a_video_not_ready_is_left_out_and_hidden_modules_cannot_be_kept(
    learner, module, client_for, make_person
):
    video = ready_video(module, title="Field walk")
    video.status = "converting"
    video.save()
    body = learner.get(f"/api/v1/offline/modules/{module.id}/").json()
    assert body["left_out"] == ["Field walk"]
    later = Module.objects.create(
        site=module.site, title="Week 9", position=2, available_from=timezone.now() + timedelta(days=30)
    )
    assert learner.get(f"/api/v1/offline/modules/{later.id}/").status_code == 404
    outsider = make_person("student", "26MRP0099", "Out", "Sider", "student")
    assert client_for(outsider.user).get(f"/api/v1/offline/modules/{module.id}/").status_code == 404
