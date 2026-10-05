"""Observation checklists marked in the field (item 3.12) and their place in coursework."""

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from audit.models import AuditLog
from notifications.models import Notification
from practicals.conftest import now_iso, photo
from practicals.models import Observation, PracticalAssessor, PracticalTask
from practicals.services import coursework_items


@pytest.mark.django_db
def test_an_observation_is_marked_in_the_field_and_seen_by_the_student_only_once_released(
    task, criteria, passing, student, lecturer, client_for
):
    teacher, learner = client_for(lecturer.user), client_for(student.user)
    body = {
        "student": student.id,
        "observed_at": now_iso(minutes=-20),
        "latitude": "6.801234",
        "longitude": "-58.155678",
        "location_text": "Plot 7, Mon Repos farm",
        "comments": "Worked steadily.",
        "results": json.dumps(passing),
        "photos": [photo(), photo("bed.jpg")],
    }
    made = teacher.post(f"/api/v1/practical-tasks/{task.id}/observations/", body, format="multipart")
    assert made.status_code == 201, made.json()
    seen = made.json()
    assert seen["attempt"] == 1 and seen["assessor_name"] == "Asha Persaud"
    assert seen["score"] == {"earned": 6, "possible": 7} and seen["critical_passed"] is True
    assert seen["latitude"] == "6.801234" and len(seen["photos"]) == 2 and not seen["is_released"]
    observation = Observation.objects.get()
    assert observation.recorded_at > observation.observed_at  # the phone's time and the server's, both kept
    assert observation.photos.first().file.name.startswith("practicals/")
    assert "plot" not in observation.photos.first().file.name

    # Not released: the student does not see it at all.
    assert learner.get("/api/v1/observations/").json()["count"] == 0
    assert learner.get(f"/api/v1/observations/{observation.id}/").status_code == 404
    assert learner.get(seen["photos"][0]["download_url"]).status_code == 404

    released = teacher.post(f"/api/v1/observations/{observation.id}/release/")
    assert released.status_code == 200 and released.json()["is_released"] is True
    mine = learner.get("/api/v1/observations/").json()["results"]
    assert len(mine) == 1 and mine[0]["results"][1]["comment"] == "Fine tilth"
    download = learner.get(seen["photos"][0]["download_url"])
    assert download.status_code == 200 and "plot 7.jpg" in download["Content-Disposition"]
    assert Notification.objects.filter(
        recipient=student.user, title__startswith="Practical observed"
    ).exists()
    assert set(AuditLog.objects.filter(entity="practicals.observation").values_list("action", flat=True)) == {
        "observe",
        "release",
    }


@pytest.mark.django_db
def test_an_observation_is_refused_unless_the_checklist_is_whole_and_right(
    task, criteria, passing, student, lecturer, client_for, observe, make_person, site
):
    missing = observe(task, student, passing[:2])
    assert missing.status_code == 400 and "Missing: Tools cleaned" in missing.json()["results"][0]
    too_high = [*passing[:1], {"criterion": criteria[1].id, "score": 6}, passing[2]]
    assert "from 0 to 5" in observe(task, student, too_high).json()["results"][0]
    no_verdict = [{"criterion": criteria[0].id}, *passing[1:]]
    assert "passed or not" in observe(task, student, no_verdict).json()["results"][0]
    twice = [*passing, passing[0]]
    assert "given twice" in observe(task, student, twice).json()["results"][0]
    other = PracticalTask.objects.create(site=site, title="Other", is_published=True)
    stranger = other.criteria.create(text="x")
    unknown = [*passing, {"criterion": stranger.id, "passed": True}]
    assert "not on this task" in observe(task, student, unknown).json()["results"][0]
    half_place = observe(task, student, passing, latitude="6.8")
    assert half_place.json()["latitude"] == ["Send both latitude and longitude, or neither."]
    outsider = make_person("student", "26ESQ0009", "Not", "Enrolled", "student")
    assert "does not exist" in observe(task, outsider, passing).json()["student"][0]
    disguised = client_for(lecturer.user).post(
        f"/api/v1/practical-tasks/{task.id}/observations/",
        {
            "student": student.id,
            "observed_at": now_iso(),
            "results": json.dumps(passing),
            "photos": [SimpleUploadedFile("plot.jpg", b"<html>x</html>")],
        },
        format="multipart",
    )
    assert disguised.status_code == 400 and "do not match its name" in disguised.json()["photos"][0]
    PracticalTask.objects.filter(pk=task.pk).update(is_published=False)
    assert observe(task, student, passing).json()["code"] == "not_open"
    assert not Observation.objects.exists()


@pytest.mark.django_db
def test_students_and_staff_of_other_sites_cannot_observe(
    task, passing, student, other_student, client_for, observe, make_person
):
    assert observe(task, other_student, passing, client=client_for(student.user)).status_code == 403
    elsewhere = make_person("staff", "E0002", "Bibi", "Khan", "lecturer")
    assert observe(task, student, passing, client=client_for(elsewhere.user)).status_code == 404
    assert not Observation.objects.exists()


@pytest.mark.django_db
def test_re_assessment_keeps_every_attempt_and_released_ones_are_final(
    task, passing, failing, student, lecturer, client_for, observe
):
    teacher = client_for(lecturer.user)
    first = observe(task, student, failing).json()
    assert first["critical_passed"] is False and first["score"] == {"earned": 3, "possible": 7}

    # Before release the assessor may correct it; the audit keeps what it was.
    corrected = teacher.patch(
        f"/api/v1/observations/{first['id']}/", {"comments": "Re-measured the bed."}, format="json"
    )
    assert corrected.status_code == 200
    update = AuditLog.objects.get(entity="practicals.observation", action="update")
    assert update.before["comments"] == "" and update.after["comments"] == "Re-measured the bed."

    teacher.post(f"/api/v1/observations/{first['id']}/release/")
    locked = teacher.patch(f"/api/v1/observations/{first['id']}/", {"comments": "x"}, format="json")
    assert locked.status_code == 409 and locked.json()["code"] == "released"
    assert teacher.delete(f"/api/v1/observations/{first['id']}/").json()["code"] == "released"
    assert (
        teacher.post(f"/api/v1/observations/{first['id']}/photos/", {"photos": [photo()]}).status_code == 409
    )

    second = observe(task, student, passing)
    assert second.status_code == 201 and second.json()["attempt"] == 2
    third = observe(task, student, passing)
    assert third.status_code == 409 and third.json()["code"] == "no_attempts_left"
    assert list(Observation.objects.values_list("attempt", flat=True)) == [1, 2]

    roster = teacher.get(f"/api/v1/practical-tasks/{task.id}/students/").json()
    mine = next(r for r in roster if r["person_id"] == student.id)
    assert mine["attempts"] == 2 and mine["attempts_left"] == 0 and mine["latest"]["attempt"] == 2


@pytest.mark.django_db
def test_a_named_field_assessor_observes_but_only_teaching_staff_release(
    task, passing, student, field_assessor, lecturer, client_for, observe, site
):
    assessor = client_for(field_assessor.user)
    made = observe(task, student, passing, client=assessor)
    assert made.status_code == 201 and made.json()["assessor_name"] == "Mark Bovell"
    assert assessor.get(f"/api/v1/observations/{made.json()['id']}/").status_code == 200
    assert assessor.post(f"/api/v1/observations/{made.json()['id']}/release/").status_code == 403
    assert assessor.post(f"/api/v1/practical-tasks/{task.id}/release/").status_code == 403
    # Naming someone an assessor does not make them teaching staff: they cannot set tasks up.
    refused = assessor.post("/api/v1/practical-tasks/", {"site": site.id, "title": "x"}, format="json")
    assert refused.status_code in (400, 403)
    assert PracticalTask.objects.count() == 1

    # Only the site's teaching staff name assessors; once removed, the site's tasks are unknown to them.
    teacher = client_for(lecturer.user)
    listed = teacher.get(f"/api/v1/practical-assessors/?site={site.id}").json()["results"]
    assert listed[0]["employee_no"] == "E0100"
    PracticalAssessor.objects.update(is_active=False)
    assert observe(task, student, passing, client=assessor).status_code == 404

    released = teacher.post(f"/api/v1/practical-tasks/{task.id}/release/")
    assert released.json() == {"released": 1}


@pytest.mark.django_db
def test_teaching_staff_name_assessors_and_build_checklists(site, lecturer, student, make_person, client_for):
    teacher = client_for(lecturer.user)
    instructor = make_person("staff", "E0200", "Jo", "Field")
    named = teacher.post(
        "/api/v1/practical-assessors/", {"site": site.id, "person": instructor.id}, format="json"
    )
    assert named.status_code == 201
    assert (
        client_for(student.user)
        .post("/api/v1/practical-assessors/", {"site": site.id, "person": instructor.id}, format="json")
        .status_code
        == 403
    )
    created = teacher.post(
        "/api/v1/practical-tasks/",
        {"site": site.id, "title": "Vaccinate broilers", "unit_type": "livestock_unit", "weight": "1"},
        format="json",
    )
    assert created.status_code == 201 and created.json()["counts_in_coursework"] is True
    scored = teacher.post(
        "/api/v1/practical-criteria/",
        {"task": created.json()["id"], "text": "Dose", "kind": "scored", "max_score": 4, "pass_score": 5},
        format="json",
    )
    assert scored.json()["pass_score"] == ["Give a pass score from 1 to 4."]
    flag = teacher.post(
        "/api/v1/practical-criteria/",
        {"task": created.json()["id"], "text": "Needle disposed of safely", "is_critical": True},
        format="json",
    )
    assert flag.status_code == 201 and flag.json()["max_score"] == 1
    # Students see published tasks only.
    assert client_for(student.user).get(f"/api/v1/practical-tasks/{created.json()['id']}/").status_code == 404


@pytest.mark.django_db
def test_a_criterion_students_were_marked_against_cannot_be_rewritten(
    task, criteria, passing, student, lecturer, client_for, observe, followed
):
    teacher = client_for(lecturer.user)
    observe(task, student, passing)
    url = f"/api/v1/practical-criteria/{criteria[0].id}/"
    rewritten = teacher.patch(url, {"text": "Something else"}, format="json")
    assert rewritten.status_code == 409 and rewritten.json()["code"] == "in_use"
    pc = followed.units.get(code="U1").elements.get().criteria.get(code="PC1.1.1")
    mapped = teacher.patch(url, {"performance_criteria": [pc.id]}, format="json")
    assert mapped.status_code == 200 and mapped.json()["performance_criteria"] == [pc.id]
    assert AuditLog.objects.filter(action="map", entity="practicals.practicalcriterion").exists()
    assert teacher.delete(url).json()["code"] == "in_use"


@pytest.mark.django_db
def test_practical_tasks_with_a_weight_give_coursework_items(
    task, passing, failing, student, other_student, site, lecturer, client_for, observe
):
    PracticalTask.objects.create(site=site, title="Not counted", weight=0, is_published=True)
    # Nothing observed and not closed: pending.
    assert coursework_items(site, student) == [(Decimal("2.00"), None)]
    first = observe(task, student, failing).json()
    # Observed but unreleased: counts for staff, pending for the student's own view.
    assert coursework_items(site, student) == [(Decimal("2.00"), Decimal(3) / Decimal(7))]
    assert coursework_items(site, student, released_only=True) == [(Decimal("2.00"), None)]
    client_for(lecturer.user).post(f"/api/v1/observations/{first['id']}/release/")
    observe(task, student, passing)  # a re-assessment, not yet released
    assert coursework_items(site, student, released_only=True) == [(Decimal("2.00"), Decimal(3) / Decimal(7))]
    assert coursework_items(site, student) == [(Decimal("2.00"), Decimal(6) / Decimal(7))]
    # The other student was never observed: pending until the task closes, then missed (0).
    assert coursework_items(site, other_student) == [(Decimal("2.00"), None)]
    PracticalTask.objects.filter(pk=task.pk).update(
        opens_at=timezone.now() - timedelta(days=9), closes_at=timezone.now() - timedelta(days=1)
    )
    assert coursework_items(site, other_student) == [(Decimal("2.00"), Decimal(0))]
