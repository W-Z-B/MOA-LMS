"""Items 2.07 to 2.09: To do, everything waiting for one person, only what they may act on."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

NOW = timezone.now


def _assignment(site, title, days, **extra):
    from assessments.models import Assignment

    fields = {"max_mark": 50, "weight": 1, "is_published": True} | extra
    return Assignment.objects.create(site=site, title=title, due_at=NOW() + timedelta(days=days), **fields)


def _logbook(site, student, status="pending", **extra):
    from practicals.models import LogbookEntry

    return LogbookEntry.objects.create(
        site=site,
        student=student,
        work_date=timezone.localdate() - timedelta(days=2),
        unit_type="crop_plot",
        task="Weeded plot 7",
        hours=2,
        client_recorded_at=NOW(),
        status=status,
        **extra,
    )


@pytest.mark.django_db
def test_to_do_refuses_anyone_not_signed_in():
    response = APIClient().get("/api/v1/to-do/")
    assert response.status_code == 403 and response.json()["code"] == "not_authenticated"


@pytest.mark.django_db
def test_teaching_staff_see_marking_oldest_first_overdue_past_the_marking_days(
    client_for, settings, lecturer, student, other_student, site, assignment
):
    from assessments.models import Mark, Submission

    Submission.objects.create(
        assignment=assignment, student=student, submitted_at=NOW() - timedelta(days=20), text="Done."
    )
    marked = Submission.objects.create(
        assignment=assignment, student=other_student, submitted_at=NOW() - timedelta(days=30), text="Done."
    )
    Mark.objects.create(submission=marked, mark=Decimal("40"))
    _logbook(site, student)

    items = client_for(lecturer.user).get("/api/v1/to-do/").json()
    assert [(i["kind"], i["kind_name"], i["overdue"]) for i in items] == [
        ("submission", "Work to mark", True),
        ("logbook", "Logbook entries to sign off", False),
    ]
    first = items[0]
    assert first["title"] == "Soil sampling report: 1 to mark" and first["waited_days"] == 20
    assert first["due_at"] is None and first["site_title"] == site.title
    assert first["link"] == f"/sites/{site.id}/assignments"
    settings.MARKING_DAYS = 30
    assert client_for(lecturer.user).get("/api/v1/to-do/").json()[0]["overdue"] is False
    # The students see none of it.
    assert [i["kind"] for i in client_for(other_student.user).get("/api/v1/to-do/").json()] == []


@pytest.mark.django_db
def test_course_administrators_see_takedowns_and_corrections_but_not_their_own(
    client_for, make_person, student, site
):
    from courses.models import ContentItem, Module, TakedownRequest
    from privacy.models import CorrectionRequest

    admin = make_person("staff", "E0050", "Grace", "Hope", "course_admin")
    item = ContentItem.objects.create(
        module=Module.objects.create(site=site, title="Week 1"), title="Chapter 3"
    )
    takedown = TakedownRequest.objects.create(item=item, reason="Copied from a textbook without leave. " * 4)
    TakedownRequest.objects.filter(pk=takedown.pk).update(created_at=NOW() - timedelta(days=8))
    TakedownRequest.objects.create(item=item, reason="Done", status="restored")
    today = timezone.localdate()
    CorrectionRequest.objects.create(
        person=student, subject="mark", wrong="38", should_be="40", due_by=today - timedelta(days=1)
    )
    CorrectionRequest.objects.create(
        person=admin, subject="personal", wrong="Grase", should_be="Grace", due_by=today + timedelta(days=9)
    )

    items = client_for(admin.user).get("/api/v1/to-do/").json()
    assert [(i["kind"], i["overdue"]) for i in items] == [("takedown", True), ("correction", True)]
    assert items[0]["title"].startswith("Chapter 3: Copied from a textbook") and items[0]["title"].endswith(
        "…"
    )
    assert len(items[0]["title"]) <= len("Chapter 3: ") + 80
    assert items[0]["link"] == f"/sites/{site.id}" and items[0]["waited_days"] == 8
    assert (
        items[1]["title"] == "Ravi Singh: my marks or feedback" and items[1]["link"] == "/admin/corrections"
    )
    # A student who asked sees nothing to decide.
    assert client_for(student.user).get("/api/v1/to-do/").json() == []


@pytest.mark.django_db
def test_disposals_wait_for_a_second_keeper_of_records(client_for, make_user):
    from privacy.models import DisposalRun, RetentionRule

    proposer = make_user("dpo.one", "dpo")
    second = make_user("sys.admin", "administrator")
    rule = RetentionRule.objects.create(code="old-logs", name="Old sign-in records", keep_months=12)
    run = DisposalRun.objects.create(rule=rule, created_by=proposer)
    DisposalRun.objects.filter(pk=run.pk).update(created_at=NOW() - timedelta(days=7))

    items = client_for(second).get("/api/v1/to-do/").json()
    assert [(i["kind"], i["title"], i["overdue"]) for i in items] == [
        ("disposal", "Records due under: Old sign-in records", True)
    ]
    assert items[0]["link"] == "/admin/retention"
    assert client_for(proposer).get("/api/v1/to-do/").json() == []  # nobody approves their own
    assert client_for(make_user("course.admin", "course_admin")).get("/api/v1/to-do/").json() == []


@pytest.mark.django_db
def test_students_see_work_due_and_logbook_entries_returned_by_date(
    client_for, student, other_student, site, assignment
):
    late = _assignment(site, "Late allowed", -3)
    _assignment(site, "Late refused", -2, allow_late=False)
    soon = _assignment(site, "Plot diagram", 1)
    returned = _logbook(site, student, status="returned", reviewed_at=NOW() - timedelta(days=1))
    _logbook(site, other_student, status="returned", reviewed_at=NOW())
    _logbook(site, student)  # waiting for sign-off: the lecturer's, not the student's

    items = client_for(student.user).get("/api/v1/to-do/").json()
    assert [(i["kind"], i["title"], i["overdue"]) for i in items] == [
        ("assignment", "Late allowed", True),
        ("logbook_returned", f"{returned.work_date:%d/%m/%Y}: Weeded plot 7", False),
        ("assignment", "Plot diagram", False),
        ("assignment", "Soil sampling report", False),
    ]
    assert items[0]["kind_name"] == "Work due" and items[0]["waited_days"] == 3
    assert items[0]["link"] == f"/sites/{site.id}/assignments" and items[0]["site_title"] == site.title
    assert items[2]["due_at"] == items[2]["since"] and items[2]["waited_days"] == 0
    assert items[1]["link"] == f"/sites/{site.id}/logbook" and items[1]["due_at"] is None
    assert late.id and soon.id
    # Home counts the same list.
    assert client_for(student.user).get("/api/v1/home/").json()["waiting"] == 4


@pytest.mark.django_db
def test_to_do_shows_only_the_callers_own_items(
    client_for, make_person, student, other_student, site, assignment
):
    """Another student's hand-in does not clear mine, and a lecturer who does not teach the site sees none of
    its marking; a student never sees marking at all."""
    from assessments.models import Submission
    from courses.models import CourseSite, Membership

    Submission.objects.create(assignment=assignment, student=other_student, text="Mine", submitted_at=NOW())
    _logbook(site, other_student)
    mine = client_for(student.user).get("/api/v1/to-do/").json()
    assert [(i["kind"], i["title"]) for i in mine] == [("assignment", assignment.title)]
    theirs = client_for(other_student.user).get("/api/v1/to-do/").json()
    assert theirs == []

    elsewhere = make_person("staff", "E0555", "Rohan", "Baksh", "lecturer")
    own = CourseSite.objects.create(code="LIV101-2026", title="Livestock", is_published=True)
    Membership.objects.create(site=own, person=elsewhere, role="lecturer")
    assert client_for(elsewhere.user).get("/api/v1/to-do/").json() == []
