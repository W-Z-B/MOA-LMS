"""The similarity check as a background job: one job for each hand-in (item 3.20)."""

import logging

from procrastinate.contrib.django import app

log = logging.getLogger(__name__)


@app.task(name="similarity.check_attempt", queue="similarity")
def check_attempt(attempt_id: int) -> str:
    """Check one hand-in. A later hand-in for the same submission replaces it; an attempt that is not the
    submission's latest any more is skipped, so a queue that runs late does no harm."""
    from assessments.models import SubmissionAttempt
    from similarity.services import check_safely

    attempt = SubmissionAttempt.objects.select_related("submission__assignment").filter(pk=attempt_id).first()
    if attempt is None:
        return "gone"
    latest = attempt.submission.attempts.order_by("-number").values_list("pk", flat=True).first()
    if latest != attempt.pk:
        return "superseded"
    document = check_safely(attempt)
    log.info("similarity.check_attempt %s: %s", attempt_id, document.status if document else "off")
    return document.status if document else "off"
