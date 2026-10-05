"""A person record that goes inactive closes the account at once (item 1.22): the account is switched off
and every session it has ends, so someone who has left the School or the course cannot sign in again."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from people.models import PersonRef


@receiver(post_save, sender=PersonRef)
def close_account_when_inactive(sender, instance: PersonRef, **kwargs):
    if instance.is_active or instance.user_id is None:
        return
    from iam.accounts import close_account

    close_account(instance, reason="The person record is no longer active")
