"""Insert-only audit log. A database trigger (migration 0002) refuses UPDATE and DELETE."""

from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    at = models.DateTimeField(auto_now_add=True, db_index=True)
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

    class Meta:
        ordering = ["-at"]

    def __str__(self) -> str:
        return f"{self.at:%Y-%m-%d %H:%M} {self.action} {self.entity}#{self.entity_id}"
