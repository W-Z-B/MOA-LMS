"""View base classes: role-checked, campus-scoped, audited CRUD."""

from django.db import transaction
from rest_framework import serializers, viewsets

from audit.services import record, snapshot
from iam.permissions import RolePermission

REASON_FIELD = "change_reason"


class AuditedModelViewSet(viewsets.ModelViewSet):
    """ModelViewSet whose writes set the acting user and produce an audit row in the same transaction.

    Subclasses declare `read_roles` and `write_roles` (tuples of role codes) for RolePermission.
    A request may say why it makes a change in a `change_reason` field of its body; the reason is kept
    on the audit row. Actions named in `reason_required_for` refuse a change that gives none.
    """

    permission_classes = [RolePermission]
    read_roles: tuple[str, ...] | None = None
    write_roles: tuple[str, ...] | None = None
    reason_required_for: tuple[str, ...] = ()

    def change_reason(self) -> str:
        data = getattr(self.request, "data", None)
        reason = str((data.get(REASON_FIELD) if hasattr(data, "get") else "") or "").strip()[:300]
        if not reason and self.action in self.reason_required_for:
            raise serializers.ValidationError({REASON_FIELD: ["Say why this is being changed."]})
        return reason

    @transaction.atomic
    def perform_create(self, serializer):
        reason = self.change_reason()
        instance = serializer.save(created_by=self.request.user, updated_by=self.request.user)
        record(self.request, "create", instance, before=None, after=snapshot(instance), reason=reason)

    @transaction.atomic
    def perform_update(self, serializer):
        reason = self.change_reason()
        before = snapshot(serializer.instance)
        instance = serializer.save(updated_by=self.request.user)
        record(self.request, "update", instance, before=before, after=snapshot(instance), reason=reason)

    @transaction.atomic
    def perform_destroy(self, instance):
        reason = self.change_reason()
        before = snapshot(instance)
        entity_id = instance.pk
        instance.delete()
        record(
            self.request, "delete", instance, before=before, after=None, entity_id=entity_id, reason=reason
        )
