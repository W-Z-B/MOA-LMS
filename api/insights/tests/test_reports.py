"""Items 6.03, 6.04 and 6.06: reports for heads of department, the Registrar, HR and the Ministry, scoped by
their role grants, with small groups hidden and a spreadsheet-safe export."""

from datetime import date, timedelta

import pytest
from django.utils import timezone

from assessments.models import SrmsTransfer
from audit.models import AuditLog
from courses.models import Completion, ContentItem, CourseSite, Membership, Module
from iam.models import Role, RoleScope
from insights.models import SiteProfile
from insights.tests.conftest import hand_in
from people.models import PersonRef
from staffdev.models import RequiredTraining, TrainingAssignment

pytestmark = pytest.mark.django_db


def grant(user, code, *, campus="", unit=""):
    RoleScope.objects.create(user=user, role=Role.objects.get(code=code), campus_code=campus, unit_code=unit)
    return user


def people(prefix, count, *, kind="student", campus="MRP", unit=""):
    return [
        PersonRef.objects.create(
            kind=kind,
            external_id=f"{prefix}{n:03d}",
            first_name="Person",
            last_name=f"{prefix}{n}",
            campus_code=campus,
            unit_code=unit,
        )
        for n in range(count)
    ]


@pytest.fixture
def big_site(make_person):
    """A second course at Essequibo with eight students, content, marking and coursework in the SRMS."""
    teacher = make_person("staff", "E0300", "Dev", "Narine", "lecturer")
    teacher.unit_code = "LIVESTOCK"
    teacher.save()
    site = CourseSite.objects.create(
        code="ANS201-2026-27-S1-ESQ",
        title="ANS201 Animal Science",
        term_code="2026-27-S1",
        campus_code="ESQ",
        source="srms",
        is_published=True,
    )
    SiteProfile.objects.create(site=site, course_code="ANS201", programme_codes=["DIP-AH"])
    Membership.objects.create(site=site, person=teacher, role="lecturer")
    module = Module.objects.create(site=site, title="Week 1")
    ContentItem.objects.create(module=module, title="Breeds")
    from assessments.models import Assignment

    work = Assignment.objects.create(
        site=site, title="=HYPERLINK(1)", due_at=timezone.now(), max_mark=10, is_published=True
    )
    for n, student in enumerate(people("26ESQ", 8, campus="ESQ")):
        Membership.objects.create(site=site, person=student, role="student")
        submission = hand_in(work, student, mark=7, when=timezone.now() - timedelta(days=3 + n))
        SrmsTransfer.objects.create(
            site=site,
            student=student,
            percent=70,
            outcome="accepted" if n else "unknown",
            sent_at=timezone.now(),
        )
        assert submission.mark
    crop = CourseSite.objects.create(
        code="CRP110-2026-27-S1-MRP", title="CRP110 Crop Protection", campus_code="MRP", is_published=True
    )
    for student in people("26CRP", 5):
        Membership.objects.create(site=crop, person=student, role="student")
    return site


def test_the_registrar_reads_every_course_with_small_classes_hidden(site, big_site, make_user, client_for):
    registrar = grant(make_user("registrar.one"), "registrar")

    data = client_for(registrar).get("/api/v1/reports/courses/").json()

    rows = {row["code"]: row for row in data["sites"]}
    agr = rows[site.code]  # two students: figures about them are hidden
    assert agr["hidden"] is True and agr["students"] is None and agr["handed_in"] is None
    assert agr["no_content"] is True and agr["items"] == 0  # not about people: shown
    ans = rows[big_site.code]
    assert ans["hidden"] is False and ans["students"] == 8 and ans["handed_in"] == 8 and ans["marked"] == 8
    assert ans["srms_sent"] == 8 and ans["srms_accepted"] == 7 and ans["srms_unknown"] == 1
    assert ans["turnaround_days"] is not None and ans["programmes"] == ["DIP-AH"]
    groups = {(g["campus_code"], g["programme"]): g for g in data["groups"]}
    assert groups[("ESQ", "DIP-AH")]["sites"] == 1 and groups[("ESQ", "DIP-AH")]["students"] == 8
    # The five on CRP110 are hidden too, or the two on AGR101 could be worked out from the total.
    assert rows["CRP110-2026-27-S1-MRP"]["hidden"] is True
    assert groups[("MRP", "Programme not known")]["students"] == 7
    assert data["total"]["students"] == 15 and data["total"]["sites_without_content"] == 2
    assert data["choices"]["campuses"] == ["ESQ", "MRP"]
    assert data["choices"]["programmes"] == ["DIP-AH", "Programme not known"]
    assert AuditLog.objects.filter(action="report_viewed", actor=registrar).exists()


def test_filters_by_campus_programme_and_term(site, big_site, make_user, client_for):
    client = client_for(grant(make_user("registrar.one"), "registrar"))
    by_campus = client.get("/api/v1/reports/courses/?campus=MRP").json()["sites"]
    assert [row["code"] for row in by_campus] == [site.code, "CRP110-2026-27-S1-MRP"]
    by_programme = client.get("/api/v1/reports/courses/?programme=DIP-AH").json()["sites"]
    assert [row["code"] for row in by_programme] == [big_site.code]
    unknown = client.get("/api/v1/reports/courses/?programme=Programme not known").json()["sites"]
    assert [row["code"] for row in unknown] == [site.code, "CRP110-2026-27-S1-MRP"]
    assert client.get("/api/v1/reports/courses/?term=1999").json()["sites"] == []


def test_a_campus_registrar_and_a_head_of_department_read_only_their_own(
    site, big_site, make_user, client_for
):
    campus = client_for(grant(make_user("registrar.esq"), "registrar", campus="ESQ"))
    assert [r["code"] for r in campus.get("/api/v1/reports/courses/").json()["sites"]] == [big_site.code]
    head = client_for(grant(make_user("head.livestock"), "head_of_department", unit="LIVESTOCK"))
    assert [r["code"] for r in head.get("/api/v1/reports/courses/").json()["sites"]] == [big_site.code]
    no_unit = client_for(grant(make_user("head.none"), "head_of_department"))
    assert no_unit.get("/api/v1/reports/courses/").status_code == 403


def test_reports_are_refused_to_lecturers_and_students(site, lecturer, student, client_for):
    for user in (lecturer.user, student.user):
        for path in ("courses", "courses/export", "staff-development", "staff-development/export"):
            answer = client_for(user).get(f"/api/v1/reports/{path}/")
            assert answer.status_code == 403 and answer.json()["code"] == "permission_denied", path


def test_the_courses_export_is_spreadsheet_safe_hides_small_groups_and_is_audited(
    site, big_site, course_admin, client_for
):
    answer = client_for(course_admin).get("/api/v1/reports/courses/export/")

    assert answer.status_code == 200 and answer["Content-Type"].startswith("text/csv")
    assert answer["X-Content-Type-Options"] == "nosniff"
    text = b"".join(answer.streaming_content).decode("utf-8")
    assert text.startswith("﻿Site,Title")
    agr = next(line for line in text.splitlines() if line.startswith(site.code))
    assert ",hidden," in agr and agr.count("hidden") == 10
    ans = next(line for line in text.splitlines() if line.startswith(big_site.code))
    assert ",8," in ans and "DIP-AH" in ans
    entry = AuditLog.objects.get(action="report_exported", actor=course_admin)
    assert entry.after["rows"] == 3


def test_formula_cells_are_quoted_in_exports():
    from insights.reports import cell

    assert cell("=HYPERLINK(1)") == "'=HYPERLINK(1)"
    assert cell("-1") == "'-1" and cell("AGR101") == "AGR101" and cell(None) == ""


@pytest.fixture
def staff_units(db):
    """Six farm staff, five in the workshop and two in the library; two farm staff and one librarian completed
    a course, and one farm worker is overdue with required training."""
    farm = people("E05", 6, kind="staff", unit="FARM")
    library = people("E06", 2, kind="staff", unit="LIBRARY")
    people("E07", 5, kind="staff", unit="WORKSHOP")
    course = CourseSite.objects.create(code="SD-FIRE", title="Fire safety", kind="staff_development")
    for person in farm[:2] + library[:1]:
        Completion.objects.create(site=course, person=person, completed_on=date.today())
    requirement = RequiredTraining.objects.create(site=course, unit_code="FARM", due_days=30)
    for n, person in enumerate(farm):
        TrainingAssignment.objects.create(
            requirement=requirement,
            person=person,
            assigned_on=date.today() - timedelta(days=60),
            due_on=date.today() - timedelta(days=1) if n == 5 else date.today() + timedelta(days=5),
            completed_on=date.today() if n < 2 else None,
        )
    return farm, library


def test_staff_development_by_unit_with_small_units_hidden(staff_units, course_admin, client_for):
    data = client_for(course_admin).get("/api/v1/reports/staff-development/").json()

    units = {u["unit_code"]: u for u in data["units"]}
    farm = units["FARM"]
    assert (farm["staff"], farm["completions"], farm["required"], farm["required_done"], farm["overdue"]) == (
        6,
        2,
        6,
        2,
        1,
    )
    assert units["LIBRARY"]["hidden"] is True and units["LIBRARY"]["completions"] is None
    assert units["WORKSHOP"]["hidden"] is True  # or the library's figures follow from the total
    assert data["courses"] == [
        {
            "site": data["courses"][0]["site"],
            "title": "Fire safety",
            "code": "SD-FIRE",
            "completions": None,
            "hidden": True,
        }
    ]
    assert data["total"]["completions"] == 3 and data["total"]["overdue"] == 1
    assert AuditLog.objects.filter(action="report_viewed", entity="staffdev.trainingassignment").exists()


def test_a_head_of_department_reads_their_units_staff_only(staff_units, make_user, client_for):
    head = client_for(grant(make_user("head.farm"), "head_of_department", unit="FARM"))
    data = head.get("/api/v1/reports/staff-development/").json()
    assert [u["unit_code"] for u in data["units"]] == ["FARM"]
    assert data["total"]["staff"] == 6
    since = head.get(f"/api/v1/reports/staff-development/?since={date.today() + timedelta(days=1)}").json()
    assert since["total"]["completions"] == 0
    assert head.get("/api/v1/reports/staff-development/?since=yesterday").status_code == 400
    registrar = client_for(grant(make_user("registrar.one"), "registrar"))
    assert registrar.get("/api/v1/reports/staff-development/").status_code == 403


def test_the_staff_development_export(staff_units, make_user, client_for):
    auditor = client_for(grant(make_user("ministry.reader"), "auditor"))
    answer = auditor.get("/api/v1/reports/staff-development/export/?campus=MRP")
    text = b"".join(answer.streaming_content).decode("utf-8")
    lines = text.splitlines()
    assert (
        lines[0] == "﻿Unit,Staff,Completions,Required training assigned,Required training done,"
        "Required training overdue"
    )
    assert "FARM,6,2,6,2,1" in lines
    assert "LIBRARY,hidden,hidden,hidden,hidden,hidden" in lines
    assert "WORKSHOP,hidden,hidden,hidden,hidden,hidden" in lines
    assert AuditLog.objects.filter(action="report_exported", entity="staffdev.trainingassignment").exists()


def test_the_new_roles_are_seeded_and_need_an_authenticator_code(make_user):
    from iam.services import requires_mfa

    assert Role.objects.filter(code__in=["head_of_department", "registrar"]).count() == 2
    head = make_user("head.x", "head_of_department")
    assert requires_mfa(head)
