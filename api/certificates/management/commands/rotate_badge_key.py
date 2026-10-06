"""Retire the key that signs Open Badges credentials and make a new one (item 5.10, docs/SETUP.md).

The retired key stays published in the issuer profile and the JWKS, so credentials it signed still check.
Run it when the key may have been exposed, or on the schedule GSA sets.
"""

from django.core.management.base import BaseCommand

from audit.models import AuditLog
from certificates import badges


class Command(BaseCommand):
    help = "Retire the Open Badges signing key and make a new one; earlier credentials still check."

    def handle(self, *args, **options):
        key = badges.rotate()
        AuditLog.objects.create(
            action="badge_key_rotated",
            entity="certificates.signingkey",
            entity_id=key.pk,
            after={"kid": key.kid},
        )
        self.stdout.write(f"Badges are now signed with {key.kid}. Earlier keys stay published for checking.")
