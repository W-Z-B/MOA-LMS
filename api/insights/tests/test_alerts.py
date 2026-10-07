"""Item 6.05: early alerts by visible rules (decision D5): the evidence is shown, a person decides, and the
student never sees an alert as a label."""

from datetime import timedelta

import pytest
from django.utils import timezone

from audit.models import AuditLog
from courses.models import ItemCompletion, Membership
from insights import alerts
from insights.models import Alert, AlertRule
from insights.tests.conftest import hand_in
from messaging.models import Conversation, Participant
from notifications.models import Notification

pytestmark = pytest.mark.django_db


def rule(kind):
    return AlertRule.objects.get(kind=kind)


def only(*kinds):
    AlertRule.objects.exclude(kind__in=kinds).update(is_active=False)


@pytest.fixture
def missed(site, make_assignment, other_student):
    """Two pieces of work past their due date that Ravi did not hand in; Devi handed both in."""
    work = [make_assignment("Soil report", days=-3), make_assignment("Field notes", days=-1)]
    for assignment in work:
        hand_in(assignment, other_student, mark=30)
    return work


def test_missed_work_raises_one_alert_with_its_evidence_and_tells_the_lecturer(
    site, lecturer, student, other_student, missed, client_for
):
    only("missed_work")

    assert alerts.nightly() == {"sites": 1, "raised": 1}
    assert alerts.nightly()["raised"] == 0  # the same evidence never raises a second alert

    alert = Alert.objects.get()
    assert (alert.student, alert.kind, alert.state) == (student, "missed_work", "open")
    assert alert.summary.startswith("2 pieces of work missed")
    assert {e["what"].split(":")[0] for e in alert.evidence} == {"Soil report", "Field notes"}
    assert AuditLog.objects.filter(entity="insights.alert", action="create", subject=student.id).exists()
    note = Notification.objects.get(recipient=lecturer.user)
    assert note.link == f"/sites/{site.id}/insights" and "1 new early alert" in note.title
    assert not Notification.objects.filter(recipient=student.user).exists()  # nothing goes to the student

    listed = client_for(lecturer.user).get(f"/api/v1/sites/{site.id}/alerts/").json()
    assert [a["student_name"] for a in listed] == ["Ravi Singh"] and len(listed[0]["evidence"]) == 2
    rows = client_for(lecturer.user).get(f"/api/v1/sites/{site.id}/progress/").json()
    assert next(r for r in rows if r["person_id"] == student.id)["open_alerts"] == 1


def test_the_threshold_and_window_are_respected(site, student, other_student, make_assignment):
    only("missed_work")
    make_assignment("Long ago", days=-60)
    make_assignment("Recent", days=-2)
    assert alerts.nightly()["raised"] == 0  # one missed within 28 days; the rule wants two
    AlertRule.objects.filter(kind="missed_work").update(window_days=90)
    assert alerts.nightly()["raised"] == 2


def test_falling_marks_compare_the_latest_two_with_the_earlier_ones(site, student, make_assignment):
    only("falling_marks")
    for days, mark in ((-40, 45), (-30, 44), (-10, 30), (-5, 25)):  # 89%, 88%, then 60%, 50%
        hand_in(make_assignment(f"Work {days}", days=days), student, mark=mark)

    alerts.nightly()

    alert = Alert.objects.get(kind="falling_marks")
    assert "34.0 percentage points" in alert.summary
    assert alert.evidence[0]["what"].startswith("Earlier marks averaged 89.0%")
    assert [e["what"] for e in alert.evidence[1:]] == ["Work -10: 60.00%", "Work -5: 50.00%"]


def test_falling_marks_need_enough_marks_and_a_recent_one(site, student, make_assignment):
    only("falling_marks")
    for days, mark in ((-90, 45), (-80, 45), (-70, 10), (-60, 10)):
        hand_in(make_assignment(f"Old {days}", days=days), student, mark=mark)
    assert alerts.nightly()["raised"] == 0  # the latest mark is older than the window
    AlertRule.objects.filter(kind="falling_marks").update(window_days=120)
    assert alerts.nightly()["raised"] == 1


def test_no_visits_counts_from_the_last_recorded_activity_or_from_joining(
    site, student, other_student, pages
):
    only("no_visits")
    Membership.objects.filter(site=site).update(created_at=timezone.now() - timedelta(days=40))
    ItemCompletion.objects.create(
        person=student, item=pages[0], completed_at=timezone.now() - timedelta(days=2), how="viewed"
    )

    alerts.nightly()

    alert = Alert.objects.get()
    assert alert.student == other_student and alert.kind == "no_visits"
    assert alert.evidence[0]["what"] == "Nothing recorded on the course since joining it 40 days ago"


def test_a_person_acknowledges_acts_or_dismisses_and_a_dismissal_stays(
    site, lecturer, student, missed, client_for
):
    only("missed_work")
    alerts.nightly()
    alert = Alert.objects.get(student=student)
    client = client_for(lecturer.user)

    assert client.post(f"/api/v1/alerts/{alert.id}/acknowledge/").json()["state"] == "acknowledged"
    assert client.post(f"/api/v1/alerts/{alert.id}/acknowledge/").status_code == 409
    assert client.post(f"/api/v1/alerts/{alert.id}/dismiss/", {}, format="json").status_code == 400
    answer = client.post(
        f"/api/v1/alerts/{alert.id}/dismiss/", {"reason": "Excused: in hospital"}, format="json"
    )
    assert answer.status_code == 200 and answer.json()["state"] == "dismissed"
    assert answer.json()["handled_by_name"] == "Asha Persaud"
    entry = AuditLog.objects.get(entity="insights.alert", action="alert_dismissed")
    assert entry.reason == "Excused: in hospital"
    assert client.post(f"/api/v1/alerts/{alert.id}/act/", {"note": "x"}, format="json").status_code == 409

    alerts.nightly()  # the same two missed pieces of work: still dismissed, nothing new
    assert Alert.objects.filter(student=student).count() == 1
    assert client.get(f"/api/v1/sites/{site.id}/alerts/").json() == []
    assert len(client.get(f"/api/v1/sites/{site.id}/alerts/?state=all").json()) == 1


def test_acting_records_the_message_written_to_the_student(site, lecturer, student, missed, client_for):
    only("missed_work")
    alerts.nightly()
    alert = Alert.objects.get(student=student)
    conversation = Conversation.objects.create(site=site, subject="Your missing work")
    Participant.objects.create(conversation=conversation, user=lecturer.user)
    client = client_for(lecturer.user)
    url = f"/api/v1/alerts/{alert.id}/act/"

    refused = client.post(url, {"note": "Wrote", "conversation": conversation.id}, format="json")
    assert refused.status_code == 400  # the student is not in that conversation
    Participant.objects.create(conversation=conversation, user=student.user)
    answer = client.post(url, {"note": "Wrote to Ravi", "conversation": conversation.id}, format="json")

    assert answer.status_code == 200
    assert answer.json()["state"] == "acted" and answer.json()["conversation"] == conversation.id


def test_students_never_see_alerts_and_others_cannot_handle_them(
    site, student, other_student, missed, make_person, client_for
):
    only("missed_work")
    alerts.nightly()
    alert = Alert.objects.get(student=student)
    assert client_for(student.user).get(f"/api/v1/sites/{site.id}/alerts/").status_code == 403
    for action in ("acknowledge", "act", "dismiss"):
        answer = client_for(student.user).post(f"/api/v1/alerts/{alert.id}/{action}/", {}, format="json")
        assert answer.status_code == 404
    mine = client_for(student.user).get(f"/api/v1/sites/{site.id}/my-progress/").json()
    assert "alert" not in str(mine).lower()
    stranger = make_person("staff", "E0777", "Other", "Lecturer", "lecturer")
    assert client_for(stranger.user).post(f"/api/v1/alerts/{alert.id}/acknowledge/").status_code == 404


def test_newer_evidence_replaces_that_of_an_alert_still_open(site, student, other_student, make_assignment):
    only("missed_work")
    make_assignment("First", days=-3)
    make_assignment("Second", days=-2)
    alerts.nightly()
    make_assignment("Third", days=-1)
    alerts.nightly()
    alert = Alert.objects.get(student=student)
    assert len(alert.evidence) == 3 and alert.summary.startswith("3 pieces")


def test_rules_are_read_by_teaching_staff_and_changed_by_course_administrators(
    site, lecturer, student, course_admin, client_for
):
    rules = client_for(lecturer.user).get("/api/v1/alert-rules/").json()
    assert {r["kind"] for r in rules} == {"missed_work", "falling_marks", "no_visits"}
    assert all(r["description"] for r in rules)
    missed_rule = rule("missed_work")
    url = f"/api/v1/alert-rules/{missed_rule.id}/"
    assert client_for(lecturer.user).patch(url, {"threshold": 3}, format="json").status_code == 403
    assert client_for(student.user).get("/api/v1/alert-rules/").status_code == 403
    admin = client_for(course_admin)
    assert admin.patch(url, {"threshold": 0}, format="json").status_code == 400
    assert admin.patch(url, {"window_days": 400}, format="json").status_code == 400
    answer = admin.patch(url, {"threshold": 3, "window_days": 14}, format="json")
    assert answer.status_code == 200 and "3 or more pieces of work" in answer.json()["description"]
    assert AuditLog.objects.filter(entity="insights.alertrule", action="update").exists()


def test_switched_off_rules_and_unpublished_or_staff_sites_raise_nothing(site, student, missed):
    AlertRule.objects.update(is_active=False)
    assert alerts.nightly()["raised"] == 0
    AlertRule.objects.update(is_active=True)
    site.kind = "staff_development"
    site.save()
    assert alerts.nightly() == {"sites": 0, "raised": 0}


def test_the_nightly_task_runs_the_check(site, student, missed):
    from insights.tasks import early_alerts

    only("missed_work")
    assert early_alerts()["raised"] == 1


def test_alerts_are_in_the_copy_produced_for_a_request_but_not_in_my_data(
    site, student, missed, make_user, client_for
):
    only("missed_work")
    alerts.nightly()
    dpo = make_user("dpo.one", "dpo")

    produced = client_for(dpo).get(f"/api/v1/privacy/people/{student.id}/record/").json()
    own = client_for(student.user).get("/api/v1/privacy/my-record/")

    raised = produced["person"]["early_alerts"]
    assert (
        raised[0]["rule"] == "Missed work"
        and raised[0]["decision"] == "New"
        and len(raised[0]["evidence"]) == 2
    )
    assert "early_alerts" not in str(own.content)
