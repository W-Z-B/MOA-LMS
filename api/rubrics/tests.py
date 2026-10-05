"""Rubrics and marking guides (items 3.09, 3.10): who keeps them, marking with them, their lock once used."""

import pytest

from assessments.models import Mark, Submission
from audit.models import AuditLog
from rubrics.models import Rubric

SCORED = {
    "title": "Field report",
    "kind": "scored",
    "criteria": [
        {
            "title": "Method",
            "levels": [
                {"points": 0, "description": "Missing"},
                {"points": 2, "description": "Partly clear"},
                {"points": 4, "description": "Clear and repeatable"},
            ],
        },
        {
            "title": "Results",
            "levels": [{"points": 0, "description": "None"}, {"points": 6, "description": "Complete"}],
        },
    ],
}


def hand_in(client, assignment):
    response = client.post(
        f"/api/v1/assignments/{assignment.id}/submit/", {"text": "My report"}, format="json"
    )
    assert response.status_code == 201
    return response.json()["id"]


@pytest.mark.django_db
def test_a_scored_rubric_fills_the_mark_and_is_shown_to_students(
    site, assignment, student, lecturer, client_for
):
    teacher, learner = client_for(lecturer.user), client_for(student.user)
    made = teacher.post("/api/v1/rubrics/", {**SCORED, "site": site.id}, format="json")
    assert made.status_code == 201, made.json()
    rubric = made.json()
    assert rubric["max_points"] == "10.00" and len(rubric["criteria"][0]["levels"]) == 3
    assert learner.post("/api/v1/rubrics/", {**SCORED, "site": site.id}, format="json").status_code == 403
    attached = teacher.patch(f"/api/v1/assignments/{assignment.id}/", {"rubric": rubric["id"]}, format="json")
    assert attached.status_code == 200
    shown = learner.get(f"/api/v1/assignments/{assignment.id}/").json()["rubric_detail"]
    assert shown["criteria"][0]["levels"][2]["description"] == "Clear and repeatable"

    submission = hand_in(learner, assignment)
    method, results = rubric["criteria"]
    url = f"/api/v1/submissions/{submission}/rubric-mark/"
    missing = teacher.post(
        url, {"scores": [{"criterion": method["id"], "level": method["levels"][2]["id"]}]}, format="json"
    )
    assert missing.status_code == 400 and "Results" in str(missing.json())
    wrong_level = teacher.post(
        url,
        {
            "scores": [
                {"criterion": method["id"], "level": results["levels"][0]["id"]},
                {"criterion": results["id"], "level": results["levels"][1]["id"]},
            ]
        },
        format="json",
    )
    assert wrong_level.status_code == 400
    twice = teacher.post(
        url,
        {"scores": [{"criterion": method["id"], "level": method["levels"][0]["id"]}] * 2},
        format="json",
    )
    assert twice.status_code == 400
    stranger = teacher.post(url, {"scores": [{"criterion": 999999, "level": 1}]}, format="json")
    assert stranger.status_code == 400
    marked = teacher.post(
        url,
        {
            "scores": [
                {"criterion": method["id"], "level": method["levels"][1]["id"], "comment": "Say how deep"},
                {"criterion": results["id"], "level": results["levels"][1]["id"]},
            ],
            "feedback": "Good results.",
            "is_released": True,
        },
        format="json",
    )
    assert marked.status_code == 200, marked.json()
    # 8 of 10 points, scaled to the assignment's 50 marks.
    assert marked.json()["mark"]["mark"] == "40.00" and marked.json()["mark"]["source"] == "rubric"
    own = learner.get(f"/api/v1/assignments/{assignment.id}/").json()["my_submission"]["mark"]
    assert own["rubric_scores"][0]["comment"] == "Say how deep"

    # Once marks were given with it, the rubric cannot change or go.
    assert teacher.get(f"/api/v1/rubrics/{rubric['id']}/").json()["in_use"] is True
    assert (
        teacher.patch(f"/api/v1/rubrics/{rubric['id']}/", {"title": "New"}, format="json").status_code == 403
    )
    assert teacher.delete(f"/api/v1/rubrics/{rubric['id']}/").status_code == 409
    assert AuditLog.objects.filter(entity="rubrics.rubric", action="create").exists()


@pytest.mark.django_db
def test_a_marking_guide_and_a_descriptive_rubric(site, assignment, student, lecturer, client_for):
    teacher, learner = client_for(lecturer.user), client_for(student.user)
    no_max = teacher.post(
        "/api/v1/rubrics/",
        {"site": site.id, "title": "Guide", "kind": "guide", "criteria": [{"title": "Analysis"}]},
        format="json",
    )
    assert no_max.status_code == 400
    guide = teacher.post(
        "/api/v1/rubrics/",
        {
            "site": site.id,
            "title": "Guide",
            "kind": "guide",
            "criteria": [
                {"title": "Analysis", "description": "Uses the soil data", "max_points": "15"},
                {"title": "Presentation", "max_points": "5"},
            ],
        },
        format="json",
    ).json()
    teacher.patch(f"/api/v1/assignments/{assignment.id}/", {"rubric": guide["id"]}, format="json")
    submission = hand_in(learner, assignment)
    url = f"/api/v1/submissions/{submission}/rubric-mark/"
    analysis, presentation = guide["criteria"]
    over = teacher.post(
        url,
        {
            "scores": [
                {"criterion": analysis["id"], "points": "16"},
                {"criterion": presentation["id"], "points": "5"},
            ]
        },
        format="json",
    )
    assert over.status_code == 400
    blank = teacher.post(
        url,
        {"scores": [{"criterion": analysis["id"]}, {"criterion": presentation["id"], "points": "5"}]},
        format="json",
    )
    assert blank.status_code == 400
    marked = teacher.post(
        url,
        {
            "scores": [
                {"criterion": analysis["id"], "points": "12"},
                {"criterion": presentation["id"], "points": "4"},
            ]
        },
        format="json",
    )
    assert marked.json()["mark"]["mark"] == "40.00"  # 16 of 20, scaled to 50

    descriptive = teacher.post(
        "/api/v1/rubrics/",
        {
            "site": site.id,
            "title": "Descriptive",
            "kind": "descriptive",
            "criteria": [{"title": "Safety", "levels": [{"description": "Unsafe"}, {"description": "Safe"}]}],
        },
        format="json",
    ).json()
    assert descriptive["max_points"] == "0.00"
    Submission.objects.all().delete()
    teacher.patch(f"/api/v1/assignments/{assignment.id}/", {"rubric": descriptive["id"]}, format="json")
    submission = hand_in(learner, assignment)
    url = f"/api/v1/submissions/{submission}/rubric-mark/"
    safety = descriptive["criteria"][0]
    scores = {"scores": [{"criterion": safety["id"], "level": safety["levels"][1]["id"]}]}
    assert teacher.post(url, scores, format="json").status_code == 400  # the marker gives the mark
    marked = teacher.post(url, {**scores, "mark": "33"}, format="json").json()
    assert marked["mark"]["mark"] == "33.00" and marked["mark"]["rubric_scores"][0]["points"] is None
    assert Mark.objects.get().source == "manual"
    teacher.patch(f"/api/v1/assignments/{assignment.id}/", {"rubric": None}, format="json")
    assert teacher.post(url, scores, format="json").json()["code"] == "no_rubric"


@pytest.mark.django_db
def test_the_gsa_library_is_kept_by_course_administrators_and_copied_to_sites(
    site, assignment, lecturer, course_admin, client_for, make_person
):
    admin, teacher = client_for(course_admin), client_for(lecturer.user)
    assert teacher.post("/api/v1/rubrics/", SCORED, format="json").status_code == 403
    library = admin.post("/api/v1/rubrics/", SCORED, format="json")
    assert library.status_code == 201 and library.json()["site"] is None
    listed = teacher.get("/api/v1/rubrics/?library=1").json()["results"]
    assert [r["title"] for r in listed] == ["Field report"]
    # A library rubric is not attached directly; it is copied to the site first.
    direct = teacher.patch(
        f"/api/v1/assignments/{assignment.id}/", {"rubric": library.json()["id"]}, format="json"
    )
    assert direct.status_code == 400
    copy = teacher.post(f"/api/v1/rubrics/{library.json()['id']}/copy/", {"site": site.id}, format="json")
    assert copy.status_code == 201 and copy.json()["copied_from"] == library.json()["id"]
    assert copy.json()["max_points"] == "10.00"
    assert teacher.get(f"/api/v1/rubrics/?site={site.id}").json()["count"] == 1
    assert (
        teacher.patch(
            f"/api/v1/assignments/{assignment.id}/", {"rubric": copy.json()["id"]}, format="json"
        ).status_code
        == 200
    )
    # The library can change without changing the copy.
    changed = admin.patch(
        f"/api/v1/rubrics/{library.json()['id']}/",
        {
            "title": "Field report 2026",
            "criteria": [{"title": "Only", "levels": [{"points": 1, "description": "x"}]}],
        },
        format="json",
    )
    assert changed.status_code == 200 and changed.json()["max_points"] == "1.00"
    assert Rubric.objects.get(pk=copy.json()["id"]).max_points() == 10
    assert (
        admin.patch(f"/api/v1/rubrics/{library.json()['id']}/", {"criteria": []}, format="json").status_code
        == 400
    )
    moved = teacher.patch(f"/api/v1/rubrics/{copy.json()['id']}/", {"site": None}, format="json")
    assert moved.status_code == 400
    assert (
        teacher.patch(f"/api/v1/rubrics/{library.json()['id']}/", {"title": "x"}, format="json").status_code
        == 403
    )
    # Someone who teaches nowhere does not see the library.
    outsider = make_person("staff", "E0100", "No", "Teaching")
    assert client_for(outsider.user).get("/api/v1/rubrics/").json()["count"] == 0
    teacher.patch(f"/api/v1/assignments/{assignment.id}/", {"rubric": None}, format="json")
    assert teacher.delete(f"/api/v1/rubrics/{copy.json()['id']}/").status_code == 204
    assert admin.delete(f"/api/v1/rubrics/{library.json()['id']}/").status_code == 204
