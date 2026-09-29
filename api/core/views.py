"""View base classes: role-checked, campus-scoped, audited CRUD."""

from django.db import transaction
from rest_framework import viewsets

from audit.services import record, snapshot
from iam.permissions import RolePermission


class AuditedModelViewSet(viewsets.ModelViewSet):
    """ModelViewSet whose writes set the acting user and produce an audit row in the same transaction.

    Subclasses declare `read_roles` and `write_roles` (tuples of role codes) for RolePermission.
    """

    permission_classes = [RolePermission]
    read_roles: tuple[str, ...] | None = None
    write_roles: tuple[str, ...] | None = None

    @transaction.atomic
    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user, updated_by=self.request.user)
        record(self.request, "create", instance, before=None, after=snapshot(instance))

    @transaction.atomic
    def perform_update(self, serializer):
        before = snapshot(serializer.instance)
        instance = serializer.save(updated_by=self.request.user)
        record(self.request, "update", instance, before=before, after=snapshot(instance))

    @transaction.atomic
    def perform_destroy(self, instance):
        before = snapshot(instance)
        entity_id = instance.pk
        instance.delete()
        record(self.request, "delete", instance, before=before, after=None, entity_id=entity_id)
