"""Fixtures for the insight tests: marks, quiz answers and a rubric on the shared AGR101 site."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from assessments.models import Assignment, Mark, Submission, SubmissionAttempt
from courses.models import ContentItem, Module


def hand_in(assignment, student, *, mark=None, released=False, when=None, late=False):
    when = when or timezone.now()
    submission = Submission.objects.create(
        assignment=assignment, student=student, submitted_at=when, is_late=late
    )
    SubmissionAttempt.objects.create(
        submission=submission,
        number=1,
        submitted_by=student,
        submitted_at=when,
        receipt=f"R{submission.pk:06d}",
        content_hash="0" * 64,
    )
    if mark is not None:
        Mark.objects.create(submission=submission, mark=Decimal(str(mark)), is_released=released)
    return submission


@pytest.fixture
def make_assignment(site):
    def _make(title, *, days=-3, max_mark=50, **options):
        return Assignment.objects.create(
            site=site,
            title=title,
            due_at=timezone.now() + timedelta(days=days),
            max_mark=max_mark,
            is_published=True,
            **options,
        )

    return _make


@pytest.fixture
def pages(site):
    module = Module.objects.create(site=site, title="Week 1")
    return [
        ContentItem.objects.create(module=module, title="Soils", body="<p>Soil</p>", position=1),
        ContentItem.objects.create(module=module, title="Handout", kind="file", position=2),
    ]


@pytest.fixture
def auditor(make_user):
    return make_user("auditor.one", "auditor")
