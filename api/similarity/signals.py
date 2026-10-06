"""Every hand-in queues its similarity check once it is saved (item 3.20)."""

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from assessments.models import SubmissionAttempt


def queue_check(attempt_id: int) -> None:
    from similarity.services import enabled
    from similarity.tasks import check_attempt

    if enabled():
        check_attempt.defer(attempt_id=attempt_id)


@receiver(post_save, sender=SubmissionAttempt)
def attempt_handed_in(sender, instance: SubmissionAttempt, created: bool, **kwargs):
    if created:
        transaction.on_commit(lambda: queue_check(instance.pk))
