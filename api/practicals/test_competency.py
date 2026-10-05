"""Competency records beside marks (item 3.13, decision D8): frameworks imported, criteria mapped, and
each unit confirmed competent or not yet competent by an assessor, never by the system alone."""

import copy

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from assessments.models import Submission
from audit.models import AuditLog
from practicals.conftest import FRAMEWORK
from practicals.models import (
    AssignmentCompetencyMap,
    CompetencyFramework,
    CompetencyResult,
    PerformanceCriterion,
    SiteFramework,
)

CSV = (
    "unit_code,unit_title,element_code,element_title,criterion_code,criterion_text\n"
    "U1,Rear broilers,E1,Brood chicks,PC1,Brooder is at the right temperature\n"
    "U1,Rear broilers,E1,Brood chicks,PC2,Litter is dry\n"
    "U2,Keep records,E2,Record mortality,PC3,Deaths are recorded daily\n"
)


@pytest.mark.django_db
def test_course_administrators_import_frameworks_from_json_or_csv(course_admin, lecturer, client_for):
    admin = client_for(course_admin)
    made = admin.post("/api/v1/competency-frameworks/import/", FRAMEWORK, format="json")
    assert made.status_code == 201
    units = made.json()["units"]
    assert [u["code"] for u in units] == ["U1", "U2"] and len(units[0]["elements"][0]["criteria"]) == 2
    again = admin.post("/api/v1/competency-frameworks/import/", FRAMEWORK, format="json")
    assert again.status_code == 400 and "already here" in again.json()["version"][0]
    newer = admin.post(
        "/api/v1/competency-frameworks/import/", {**FRAMEWORK, "version": "2025.1"}, format="json"
    )
    assert newer.status_code == 201

    csv = admin.post(
        "/api/v1/competency-frameworks/import/",
        {
            "code": "LIV-POULTRY-L1",
            "title": "Poultry",
            "csv": SimpleUploadedFile("poultry.csv", CSV.encode()),
        },
        format="multipart",
    )
    assert csv.status_code == 201, csv.json()
    assert [len(u["elements"][0]["criteria"]) for u in csv.json()["units"]] == [2, 1]
    bad = admin.post(
        "/api/v1/competency-frameworks/import/",
        {"code": "X", "title": "X", "csv": SimpleUploadedFile("x.csv", b"unit,title\nU1,x\n")},
        format="multipart",
    )
    assert bad.status_code == 400 and "first row must be" in bad.json()["csv"][0]
    empty = copy.deepcopy(FRAMEWORK) | {"code": "EMPTY", "units": []}
    assert admin.post("/api/v1/competency-frameworks/import/", empty, format="json").status_code == 400

    refused = client_for(lecturer.user).post(
        "/api/v1/competency-frameworks/import/", {**FRAMEWORK, "code": "Z"}, format="json"
    )
    assert refused.status_code == 403
    assert CompetencyFramework.objects.count() == 3
    assert AuditLog.objects.filter(action="import").count() == 3
    # Everyone signed in can read them.
    assert client_for(lecturer.user).get("/api/v1/competency-frameworks/").json()["count"] == 3


@pytest.mark.django_db
def test_a_site_follows_a_framework_and_maps_criteria_and_assignments_to_it(
    site, framework, task, criteria, assignment, lecturer, student, client_for, make_person
):
    teacher = client_for(lecturer.user)
    pc = PerformanceCriterion.objects.get(code="PC1.1.1")
    # Not yet followed by the site: mapping is refused.
    early = teacher.patch(
        f"/api/v1/practical-criteria/{criteria[0].id}/", {"performance_criteria": [pc.id]}, format="json"
    )
    assert (
        early.status_code == 400
        and "not in a framework this site follows" in early.json()["performance_criteria"][0]
    )
    assert (
        client_for(student.user)
        .post("/api/v1/site-frameworks/", {"site": site.id, "framework": framework.id}, format="json")
        .status_code
        == 403
    )
    follows = teacher.post(
        "/api/v1/site-frameworks/", {"site": site.id, "framework": framework.id}, format="json"
    )
    assert follows.status_code == 201
    mapped = teacher.patch(
        f"/api/v1/practical-criteria/{criteria[0].id}/", {"performance_criteria": [pc.id]}, format="json"
    )
    assert mapped.status_code == 200

    by_assignment = teacher.post(
        "/api/v1/competency-maps/",
        {"assignment": assignment.id, "performance_criterion": pc.id},
        format="json",
    )
    assert by_assignment.status_code == 201 and by_assignment.json()["site"] == site.id
    assert AssignmentCompetencyMap.objects.get().assignment_id == assignment.id
    # An assignment on a site the lecturer cannot open reads exactly as one that is not there.
    elsewhere = make_person("staff", "E0002", "Bibi", "Khan", "lecturer")
    theirs = client_for(elsewhere.user).post(
        "/api/v1/competency-maps/",
        {"assignment": assignment.id, "performance_criterion": pc.id},
        format="json",
    )
    assert theirs.status_code == 400 and "does not exist" in theirs.json()["assignment"][0]
    assert (
        client_for(student.user)
        .post(
            "/api/v1/competency-maps/",
            {"assignment": assignment.id, "performance_criterion": pc.id},
            format="json",
        )
        .status_code
        == 403
    )


@pytest.mark.django_db
def test_competent_needs_every_critical_criterion_passed_in_a_released_observation(
    task, passing, failing, mapped, student, lecturer, client_for, observe, site
):
    teacher, learner = client_for(lecturer.user), client_for(student.user)
    result = {"site": site.id, "student": student.id, "unit": mapped.id, "status": "competent"}

    failed = observe(task, student, failing).json()
    teacher.post(f"/api/v1/observations/{failed['id']}/release/")
    sheet = teacher.get(f"/api/v1/sites/{site.id}/competency/?student={student.id}").json()
    cell = next(u for u in sheet["rows"][0]["units"] if u["unit_code"] == "U1")
    assert (
        cell["suggested"] == "not_yet_competent"
        and cell["missing_critical"][0]["text"] == "Bed formed to 1.2 m"
    )

    refused = teacher.post(
        "/api/v1/competency-results/", {**result, "evidence_observations": [failed["id"]]}, format="json"
    )
    assert refused.status_code == 409 and refused.json()["code"] == "criteria_not_met"
    assert "Bed formed to 1.2 m" in refused.json()["detail"]
    nyc = teacher.post(
        "/api/v1/competency-results/",
        {**result, "status": "not_yet_competent", "comments": "Re-assess the bed width."},
        format="json",
    )
    assert nyc.status_code == 201 and nyc.json()["assessor_name"] == "Asha Persaud"

    # A pass not yet released does not count.
    passed = observe(task, student, passing).json()
    assert (
        teacher.post("/api/v1/competency-results/", result, format="json").json()["code"]
        == "criteria_not_met"
    )
    teacher.post(f"/api/v1/observations/{passed['id']}/release/")
    sheet = teacher.get(f"/api/v1/sites/{site.id}/competency/?student={student.id}").json()
    assert next(u for u in sheet["rows"][0]["units"] if u["unit_code"] == "U1")["suggested"] == "competent"

    # The assessor confirms, with evidence; the system never records it by itself.
    assert CompetencyResult.objects.get().status == "not_yet_competent"
    no_evidence = teacher.post("/api/v1/competency-results/", result, format="json")
    assert no_evidence.status_code == 400 and "evidence_observations" in no_evidence.json()
    confirmed = teacher.post(
        "/api/v1/competency-results/", {**result, "evidence_observations": [passed["id"]]}, format="json"
    )
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "competent"
    assert CompetencyResult.objects.count() == 1
    change = AuditLog.objects.filter(action="competency_result").order_by("-id").first()
    assert change.before["status"] == "not_yet_competent" and change.after["status"] == "competent"
    assert change.after["evidence_observations"] == [passed["id"]]

    # The student sees their own result, without the working towards it; nobody else's.
    own = learner.get(f"/api/v1/sites/{site.id}/competency/").json()
    cell = next(u for u in own["rows"][0]["units"] if u["unit_code"] == "U1")
    assert cell["result"]["status"] == "competent" and "suggested" not in cell
    assert learner.get("/api/v1/competency-results/").json()["count"] == 1
    assert learner.post("/api/v1/competency-results/", result, format="json").status_code == 403


@pytest.mark.django_db
def test_evidence_must_be_the_students_own_on_the_site(
    task, passing, mapped, student, other_student, assignment, lecturer, client_for, observe, site
):
    teacher = client_for(lecturer.user)
    theirs = observe(task, other_student, passing).json()
    teacher.post(f"/api/v1/observations/{theirs['id']}/release/")
    result = {"site": site.id, "student": student.id, "unit": mapped.id, "status": "not_yet_competent"}
    wrong = teacher.post(
        "/api/v1/competency-results/", {**result, "evidence_observations": [theirs["id"]]}, format="json"
    )
    assert wrong.status_code == 400 and "not a released observation of this student" in str(wrong.json())
    work = Submission.objects.create(
        assignment=assignment, student=other_student, text="x", submitted_at=timezone.now()
    )
    wrong = teacher.post(
        "/api/v1/competency-results/", {**result, "evidence_submissions": [work.id]}, format="json"
    )
    assert wrong.status_code == 400 and "evidence_submissions" in wrong.json()
    own = Submission.objects.create(
        assignment=assignment, student=student, text="x", submitted_at=timezone.now()
    )
    fine = teacher.post(
        "/api/v1/competency-results/", {**result, "evidence_submissions": [own.id]}, format="json"
    )
    assert fine.status_code == 201 and fine.json()["evidence_submissions"] == [own.id]


@pytest.mark.django_db
def test_only_assessors_of_the_site_record_results(
    task, mapped, student, field_assessor, client_for, make_person, site, framework
):
    result = {"site": site.id, "student": student.id, "unit": mapped.id, "status": "not_yet_competent"}
    by_assessor = client_for(field_assessor.user).post("/api/v1/competency-results/", result, format="json")
    assert by_assessor.status_code == 201 and by_assessor.json()["assessor_name"] == "Mark Bovell"
    elsewhere = make_person("staff", "E0002", "Bibi", "Khan", "lecturer")
    unknown = client_for(elsewhere.user).post("/api/v1/competency-results/", result, format="json")
    assert unknown.status_code == 400 and "does not exist" in unknown.json()["site"][0]
    # A unit of a framework the site does not follow is refused.
    SiteFramework.objects.all().delete()
    refused = client_for(field_assessor.user).post("/api/v1/competency-results/", result, format="json")
    assert refused.status_code == 400 and "framework the site follows" in refused.json()["unit"][0]
