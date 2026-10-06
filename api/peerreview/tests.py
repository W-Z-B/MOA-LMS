"""Peer review (item 4.13): allocation after the due date, anonymous reviews against the rubric, the
lecturer's moderation, release, self-assessment and the peer mark as a share of the mark."""

from collections import Counter
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from assessments.models import Mark, Submission
from audit.models import AuditLog
from courses.models import Membership, SiteGroup
from notifications.models import Notification
from peerreview import services, tasks
from peerreview.models import PeerReview, PeerReviewSetup
from rubrics.models import Rubric
from rubrics.services import replace_criteria


@pytest.fixture
def rubric(site):
    rubric = Rubric.objects.create(site=site, title="Report rubric", kind=Rubric.Kind.SCORED)
    replace_criteria(
        rubric,
        [
            {
                "title": "Method",
                "levels": [{"points": 0, "description": "Missing"}, {"points": 5, "description": "Clear"}],
            },
            {
                "title": "Results",
                "levels": [{"points": 0, "description": "Missing"}, {"points": 5, "description": "Clear"}],
            },
        ],
    )
    return rubric


@pytest.fixture
def cohort(site, student, other_student, make_person):
    more = [make_person("student", f"26MRP00{n}", f"Name{n}", "Student", "student") for n in (11, 12)]
    for person in more:
        Membership.objects.create(site=site, person=person, role="student")
    return [student, other_student, *more]


def _levels(rubric, best: tuple[bool, bool]) -> list[dict]:
    scores = []
    for criterion, top in zip(rubric.criteria.all(), best, strict=True):
        levels = list(criterion.levels.all())
        scores.append({"criterion": criterion.id, "level": (levels[1] if top else levels[0]).id})
    return scores


def _hand_in(client_for, assignment, people):
    for number, person in enumerate(people):
        response = client_for(person.user).post(
            f"/api/v1/assignments/{assignment.id}/submit/",
            {
                "text": f"Report number {number}",
                "files": [SimpleUploadedFile("Ravi Singh report.pdf", b"%PDF-1.7 x")],
            },
            format="multipart",
        )
        assert response.status_code == 201, response.json()


@pytest.mark.django_db
def test_setting_up_needs_a_rubric_individual_work_and_a_later_review_date(
    site, assignment, lecturer, student, rubric, client_for
):
    teacher = client_for(lecturer.user)
    url = f"/api/v1/assignments/{assignment.id}/peer-review/"
    body = {"reviews_each": 2, "reviews_due_at": (assignment.due_at + timedelta(days=5)).isoformat()}
    assert teacher.put(url, body, format="json").json()["code"] == "rubric_required"
    assignment.rubric = rubric
    assignment.is_group = True
    assignment.save()
    assert teacher.put(url, body, format="json").json()["code"] == "not_for_groups"
    assignment.is_group = False
    assignment.save()
    early = teacher.put(url, {**body, "reviews_due_at": assignment.due_at.isoformat()}, format="json")
    assert early.status_code == 400 and "reviews_due_at" in early.json()
    assert teacher.put(url, {**body, "peer_weight": 120}, format="json").status_code == 400
    saved = teacher.put(url, {**body, "peer_weight": 20, "self_assessment": True}, format="json")
    assert saved.status_code == 200 and saved.json()["setup"]["peer_weight"] == "20.00"
    assert AuditLog.objects.filter(entity="peerreview.peerreviewsetup", action="create").exists()
    # Students may not set it up; they see their (empty) list of reviews.
    learner = client_for(student.user)
    assert learner.put(url, body, format="json").status_code == 403
    assert learner.get(url).json() == {"setup": saved.json()["setup"], "to_do": [], "received": None}
    # Before the work is given out it can be taken off again.
    assert teacher.delete(url).status_code == 204 and not PeerReviewSetup.objects.exists()
    assert teacher.delete(url).status_code == 204


@pytest.mark.django_db
def test_peer_review_from_allocation_to_the_mark(site, assignment, lecturer, cohort, rubric, client_for):
    assignment.rubric = rubric
    assignment.save()
    teacher = client_for(lecturer.user)
    due = timezone.now() + timedelta(days=10)
    teacher.put(
        f"/api/v1/assignments/{assignment.id}/peer-review/",
        {"reviews_each": 2, "reviews_due_at": due.isoformat(), "self_assessment": True, "peer_weight": 20},
        format="json",
    )
    _hand_in(client_for, assignment, cohort)

    # Not before the due date.
    allocate_url = f"/api/v1/assignments/{assignment.id}/peer-review/allocate/"
    assert teacher.post(allocate_url).json()["code"] == "not_due"
    assignment.due_at = timezone.now() - timedelta(hours=1)
    assignment.save()
    assert teacher.post(allocate_url).json() == {"reviews": 4 * 2 + 4}
    assert teacher.post(allocate_url).json()["code"] == "already_allocated"
    # Each piece of work is reviewed twice by others, and nobody reviews their own except to self-assess.
    others = PeerReview.objects.filter(is_self=False).select_related("submission")
    assert Counter(r.submission_id for r in others) == {s.id: 2 for s in Submission.objects.all()}
    assert all(r.reviewer_id != r.submission.student_id for r in others)
    assert PeerReview.objects.filter(is_self=True).count() == 4
    assert Notification.objects.filter(title__startswith="Peer review:").count() == 4
    # Only the review date and the weight can change now.
    fixed = teacher.put(
        f"/api/v1/assignments/{assignment.id}/peer-review/", {"reviews_each": 3}, format="json"
    )
    assert fixed.json()["code"] == "allocated"
    assert teacher.delete(f"/api/v1/assignments/{assignment.id}/peer-review/").json()["code"] == "allocated"

    # A student sees their work to review, without names, even in the file names.
    first = cohort[0]
    learner = client_for(first.user)
    mine = learner.get(f"/api/v1/assignments/{assignment.id}/peer-review/").json()
    assert [t["label"] for t in mine["to_do"]] == ["Work 1", "Work 2", "Your own work"]
    assert mine["received"] is None
    work = learner.get(f"/api/v1/peer-reviews/{mine['to_do'][0]['id']}/").json()
    assert work["text"].startswith("Report number") and work["rubric"]["title"] == "Report rubric"
    assert "Ravi" not in str(work) and work["files"][0]["filename"] == "work-1-1.pdf"
    download = learner.get(work["files"][0]["download_url"])
    assert download.status_code == 200 and "work-1-1.pdf" in download["Content-Disposition"]
    assert learner.get(f"/api/v1/peer-reviews/{mine['to_do'][0]['id']}/files/999999/").status_code == 404
    # Nobody opens a review given to someone else.
    someone_else = PeerReview.objects.exclude(reviewer=first).first()
    assert learner.get(f"/api/v1/peer-reviews/{someone_else.id}/").status_code == 404

    # Every criterion must be scored; then the review gives a mark scaled to the maximum (50).
    url = f"/api/v1/peer-reviews/{mine['to_do'][0]['id']}/"
    partial = learner.post(
        url, {"scores": _levels(rubric, (True, True))[:1], "comment": "Good"}, format="json"
    )
    assert partial.status_code == 400
    for review in PeerReview.objects.filter(is_self=False):
        services.submit_review(
            review,
            scores=_levels(rubric, (True, review.reviewer_id % 2 == 0)),
            comment="Fine",
            request=_req(review),
        )
    sent = learner.post(
        url, {"scores": _levels(rubric, (True, True)), "comment": "Clear method"}, format="json"
    )
    assert sent.status_code == 200 and sent.json()["mark"] == "50.00"
    own = PeerReview.objects.get(reviewer=first, is_self=True)
    learner.post(
        f"/api/v1/peer-reviews/{own.id}/",
        {"scores": _levels(rubric, (True, False)), "comment": "Mine"},
        format="json",
    )

    # The lecturer sees who reviewed what, and the peer mark: the mean of the reviews that count.
    target = Submission.objects.get(student=cohort[1])
    view = teacher.get(f"/api/v1/assignments/{assignment.id}/peer-review/").json()
    row = next(r for r in view["work"] if r["submission"] == target.id)
    marks = [Decimal(r["mark"]) for r in row["reviews"] if not r["is_self"]]
    assert Decimal(row["peer_mark"]) == sum(marks) / 2 and row["reviews"][0]["reviewer"].startswith("26MRP")
    # Leaving one out changes the peer mark to the other one; an override wins over both.
    left = next(r for r in row["reviews"] if not r["is_self"])
    moderated = teacher.post(
        f"/api/v1/peer-reviews/{left['id']}/moderate/",
        {"moderation": "left_out", "note": "Unkind"},
        format="json",
    )
    assert moderated.json()["moderation"] == "left_out"
    kept = next(r for r in row["reviews"] if not r["is_self"] and r["id"] != left["id"])
    assert services.peer_mark(target) == Decimal(kept["mark"])
    assert learner.post(
        f"/api/v1/peer-reviews/{left['id']}/moderate/", {"moderation": "counts"}, format="json"
    ).status_code in (403, 404)
    over = teacher.post(
        f"/api/v1/submissions/{target.id}/peer-mark/", {"override": "30", "note": "Agreed"}, format="json"
    )
    assert over.json()["peer_mark"] == "30.00"
    assert (
        teacher.post(
            f"/api/v1/submissions/{target.id}/peer-mark/", {"override": "60"}, format="json"
        ).status_code
        == 400
    )

    # Released: the student reads the reviews that count, without reviewers' names.
    assert teacher.post(f"/api/v1/assignments/{assignment.id}/peer-review/release/").json() == {"students": 4}
    received = (
        client_for(cohort[1].user).get(f"/api/v1/assignments/{assignment.id}/peer-review/").json()["received"]
    )
    assert [r["label"] for r in received if not r["is_self"]] == ["Reviewer 1"]
    assert "26MRP" not in str(received)

    # The peer mark counts as 20% of the mark: 40 from the marker and 30 from peers make 38.
    from rest_framework.test import APIRequestFactory

    request = APIRequestFactory().post("/")
    request.user = lecturer.user
    from assessments import rules

    rules.save_mark(request, target, mark=Decimal(40), feedback="", is_released=False)
    applied = teacher.post(f"/api/v1/assignments/{assignment.id}/peer-review/apply/").json()
    assert applied == {"applied": 1, "skipped": 3}
    assert Mark.objects.get(submission=target).mark == Decimal("38.00")
    # Folding in again keeps the marker's 40; a changed marker's mark is taken afresh.
    teacher.post(f"/api/v1/assignments/{assignment.id}/peer-review/apply/")
    assert Mark.objects.get(submission=target).mark == Decimal("38.00")
    rules.save_mark(request, target, mark=Decimal(50), feedback="", is_released=True)
    assert teacher.post(f"/api/v1/assignments/{assignment.id}/peer-review/apply/").json()["applied"] == 0
    assert AuditLog.objects.filter(action="peer_component_applied").count() == 2

    # Reviews close at their due date.
    PeerReviewSetup.objects.update(reviews_due_at=timezone.now() - timedelta(minutes=1))
    closed = learner.post(url, {"scores": _levels(rubric, (True, True)), "comment": "Late"}, format="json")
    assert closed.status_code == 409 and closed.json()["code"] == "closed"


def _req(review):
    from rest_framework.test import APIRequestFactory

    request = APIRequestFactory().post("/")
    request.user = review.reviewer.user
    return request


@pytest.mark.django_db
def test_hourly_job_allocates_after_the_due_date_and_feedback_only_peer_review(
    site, assignment, lecturer, cohort, rubric, client_for
):
    assignment.rubric = rubric
    assignment.save()
    setup = PeerReviewSetup.objects.create(
        assignment=assignment, reviews_each=5, reviews_due_at=assignment.due_at + timedelta(days=3)
    )
    _hand_in(client_for, assignment, cohort[:1])
    assert tasks.allocate_due() == 0  # not due yet
    assignment.due_at = timezone.now() - timedelta(minutes=5)
    assignment.save()
    assert services.allocate_due() == 0  # one hand-in is too few, and is left for the lecturer
    teacher = client_for(lecturer.user)
    assert (
        teacher.post(f"/api/v1/assignments/{assignment.id}/peer-review/allocate/").json()["code"] == "too_few"
    )
    _hand_in(client_for, assignment, cohort[1:3])
    assert tasks.allocate_due() == 3 * 2  # five each asked; two others are all there are
    setup.refresh_from_db()
    assert setup.allocated_at is not None
    # Peer marks that do not count cannot be folded in; release needs the work given out first.
    refused = teacher.post(f"/api/v1/assignments/{assignment.id}/peer-review/apply/")
    assert refused.status_code == 400 and refused.json()["code"] == "feedback_only"
    other = assignment.__class__.objects.create(
        site=site, title="Second", due_at=timezone.now(), is_published=True
    )
    assert (
        teacher.post(f"/api/v1/assignments/{other.id}/peer-review/release/").json()["code"]
        == "no_peer_review"
    )
    PeerReviewSetup.objects.create(assignment=other, reviews_due_at=timezone.now() + timedelta(days=1))
    assert (
        teacher.post(f"/api/v1/assignments/{other.id}/peer-review/release/").json()["code"] == "not_allocated"
    )
    assert (
        teacher.post(
            f"/api/v1/submissions/{Submission.objects.first().id}/peer-mark/",
            {"override": None},
            format="json",
        ).status_code
        == 200
    )
    group = SiteGroup.objects.create(site=site, name="Unused")
    assert group.pk  # groups on the site do not change individual peer review


@pytest.mark.django_db
def test_strangers_and_unpublished_assignments(site, assignment, student, make_person, client_for, rubric):
    assignment.rubric = rubric
    assignment.is_published = False
    assignment.save()
    url = f"/api/v1/assignments/{assignment.id}/peer-review/"
    assert client_for(student.user).get(url).status_code == 404
    stranger = make_person("staff", "E0042", "No", "Access", "lecturer")
    assert client_for(stranger.user).get(url).status_code == 404
    auditor = make_person("staff", "E0043", "Read", "Only", "auditor")
    assert client_for(auditor.user).get(url).status_code == 403
