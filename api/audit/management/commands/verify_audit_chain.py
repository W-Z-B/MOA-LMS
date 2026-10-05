"""Check every audit entry against its chained fingerprint: `python manage.py verify_audit_chain`.

Exits with an error when the chain is broken, so it can run from a script or a monitor.
"""

from django.core.management.base import BaseCommand, CommandError

from audit.chain import verify


class Command(BaseCommand):
    help = "Check that no audit entry has been changed or removed (item 1.17)."

    def handle(self, *args, **options):
        check = verify()
        if not check.intact:
            raise CommandError(check.detail)
        self.stdout.write(
            self.style.SUCCESS(f"Audit log intact: {check.rows} entries, the newest is {check.last_id}.")
        )
