"""Completion is checked as soon as anything that counts towards it happens (item 5.03): an item completed, a
quiz attempt finished or marked, a mark given or released. The check runs once the change is saved, and
only for sites with a catalogue entry; the nightly sweep catches anything missed.

A new student is also put on the orientation course at their first sign-in (staffdev.orientation)."""

import logging

from django.contrib.auth.signals import user_logged_in
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from assessments.models import Mark
from courses.models import ItemCompletion
from quizzes.models import Attempt

log = logging.getLogger(__name__)


def _check_later(site_id: int, person_id: int) -> None:
    def check():
        from people.models import PersonRef
        from staffdev.completion import evaluate
        from staffdev.models import CatalogueEntry

        entry = CatalogueEntry.objects.filter(site_id=site_id).select_related("site").first()
        person = PersonRef.objects.filter(pk=person_id).first()
        if entry is None or person is None:
            return
        try:
            evaluate(entry, person)
        except Exception:  # noqa: BLE001 - the learner's own action is saved; the nightly sweep tries again
            log.exception("completion check failed for site %s, person %s", site_id, person_id)

    transaction.on_commit(check)


@receiver(post_save, sender=ItemCompletion)
def item_completed(sender, instance: ItemCompletion, created: bool, **kwargs):
    if created:
        _check_later(instance.item.module.site_id, instance.person_id)


@receiver(post_save, sender=Attempt)
def attempt_saved(sender, instance: Attempt, **kwargs):
    if instance.state == Attempt.State.FINISHED:
        _check_later(instance.quiz.site_id, instance.student_id)


@receiver(post_save, sender=Mark)
def mark_saved(sender, instance: Mark, **kwargs):
    if instance.is_released:
        submission = instance.submission
        _check_later(submission.assignment.site_id, submission.student_id)


@receiver(user_logged_in)
def orientation_at_first_sign_in(sender, request, user, **kwargs):
    """A new student is put on the orientation course when they first sign in (item 7.16)."""
    from staffdev.orientation import enrol_new_student

    try:
        with transaction.atomic():
            enrol_new_student(getattr(user, "person", None), request=request)
    except Exception:  # noqa: BLE001 - signing in must never fail because of the orientation course
        log.exception("orientation enrolment failed for user %s", user.pk)
