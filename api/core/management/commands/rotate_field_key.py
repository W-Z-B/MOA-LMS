"""Encrypt every stored encrypted value again with the newest key (ASVS 1.6.3, 6.2.4; core.crypto).

Run it after putting the new key first in FIELD_ENCRYPTION_KEYS (new,old). Every EncryptedTextField of every
model is read with whichever key opens it and written back encrypted with the newest key; a value already
on the newest key is left alone, so the command can be run again safely after an interruption. Each table
is done in its own transaction. The run is recorded in the audit log with how many values each field had
re-encrypted (never the values). With --check nothing is changed: it counts the values still on an old key.

Afterwards the old key opens nothing and can move to AUDIT_CHAIN_RETIRED_KEYS (docs/runbook.md).
"""

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from core import crypto
from core.fields import EncryptedTextField

BATCH = 500


def encrypted_fields():
    """(model, field) for every encrypted field in the system."""
    for model in apps.get_models():
        if model._meta.proxy or not model._meta.managed:
            continue
        for field in model._meta.concrete_fields:
            if isinstance(field, EncryptedTextField):
                yield model, field


class Command(BaseCommand):
    help = "Encrypt every stored encrypted value again with the newest key in FIELD_ENCRYPTION_KEYS."

    def add_arguments(self, parser):
        parser.add_argument(
            "--check", action="store_true", help="Count the values still on an old key; change nothing"
        )

    def handle(self, *args, check=False, **options):
        try:
            crypto.current_key()
        except Exception as error:  # noqa: BLE001 - ImproperlyConfigured, said plainly
            raise CommandError(str(error)) from error
        crypto._fernet.cache_clear()
        counts: dict[str, int] = {}
        for model, field in encrypted_fields():
            label = f"{model._meta.label_lower}.{field.name}"
            try:
                counts[label] = self._field(model, field, check=check)
            except ValueError as error:
                raise CommandError(
                    f"{label}: a stored value opens with none of the keys in FIELD_ENCRYPTION_KEYS ({error})."
                ) from error
        total = sum(counts.values())
        for label, count in counts.items():
            if count:
                self.stdout.write(f"{label}: {count}")
        if check:
            self.stdout.write(f"{total} value(s) still on an old key.")
            return
        from audit.services import record_event

        record_event(
            None,
            "field_key_rotated",
            "core.crypto",
            after={"re_encrypted": {k: v for k, v in counts.items() if v}, "keys_in_use": len(crypto.keys())},
            reason="Encrypted values moved to the newest key (rotate_field_key)",
        )
        self.stdout.write(self.style.SUCCESS(f"{total} value(s) encrypted again with the newest key."))

    @staticmethod
    def _field(model, field, *, check: bool) -> int:
        table = connection.ops.quote_name(model._meta.db_table)
        column = connection.ops.quote_name(field.column)
        pk = connection.ops.quote_name(model._meta.pk.column)
        changed = 0
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT {pk}, {column} FROM {table} WHERE {column} IS NOT NULL")  # noqa: S608
                rows = cursor.fetchall()
            for start in range(0, len(rows), BATCH):
                updates = []
                for key, token in rows[start : start + BATCH]:
                    if crypto.is_current(bytes(token)):
                        continue
                    plain = crypto.decrypt(bytes(token))  # ValueError when no key opens it
                    updates.append((crypto.encrypt(plain), key))
                changed += len(updates)
                if updates and not check:
                    with connection.cursor() as cursor:
                        cursor.executemany(
                            f"UPDATE {table} SET {column} = %s WHERE {pk} = %s",  # noqa: S608 - quoted names
                            updates,
                        )
        return changed
