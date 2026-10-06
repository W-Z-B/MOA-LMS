"""Insert-only audit log. A database trigger (migration 0002) refuses UPDATE and DELETE, and every row is
chained to the one before it by a keyed fingerprint (audit.chain), so a row changed or removed by someone
who switched the trigger off still shows."""

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone


class AuditLog(models.Model):
    # Set when the row is made, not by the database, because the fingerprint covers it.
    at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_entries",
    )
    action = models.CharField(max_length=40)  # create, update, delete, reveal, transition, login, ...
    entity = models.CharField(max_length=80, db_index=True)  # app_label.modelname
    entity_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    # The person (people.PersonRef) the record is about, so one person's history reads in one place.
    subject = models.BigIntegerField(null=True, blank=True, db_index=True)
    reason = models.CharField(max_length=300, blank=True, help_text="Why the change was made, as given")
    chain = models.CharField(
        max_length=64,
        editable=False,
        default="",
        help_text="Keyed fingerprint of this row and the one before",
    )

    class Meta:
        ordering = ["-at"]

    def __str__(self) -> str:
        return f"{self.at:%Y-%m-%d %H:%M} {self.action} {self.entity}#{self.entity_id}"

    def save(self, *args, **kwargs):
        """Rows are only ever added: each one under the chain lock, linked to the newest row before it."""
        from audit import chain

        if not self._state.adding:
            raise ValueError("Audit entries are never changed.")
        with transaction.atomic(using=kwargs.get("using")):
            chain.lock()
            self.chain = chain.link(chain.head(), self)
            super().save(*args, **kwargs)


class AuditCheck(models.Model):
    """One walk of the audit chain: how many entries fit, the newest, and the first that did not (item 1.17).

    The newest entry and its fingerprint are kept so that the next check notices entries removed from the end.
    """

    checked_at = models.DateTimeField(auto_now_add=True)
    checked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    rows = models.PositiveIntegerField()
    intact = models.BooleanField()
    last_id = models.BigIntegerField(null=True, blank=True)
    last_chain = models.CharField(max_length=64, blank=True)
    first_broken_id = models.BigIntegerField(null=True, blank=True)
    detail = models.TextField(blank=True)

    class Meta:
        ordering = ["-checked_at", "-id"]

    def __str__(self) -> str:
        return f"Audit check {self.checked_at:%Y-%m-%d %H:%M}: {'intact' if self.intact else 'broken'}"
