"""Every change made in the Django admin reaches the chained audit log (ASVS 7.1.3, 4.3.3).

LmsAdminSite.register (iam/admin_site.py) mixes AuditedAdmin into every model admin, Django's own User and
Group admins included, so no table can be changed there without an entry: who, from where, the record
before and after (encrypted fields, password hashes and key hashes masked by audit.services.snapshot), and
"Django admin" as the reason. Inline rows and many-to-many choices (an account's groups and permissions)
are recorded too, and so is anything saved by a form of the admin's own, such as the password form.

Models are imported inside the methods: this module is loaded with the admin site, before the app
registry is ready.
"""

from django.contrib import admin

REASON = "Django admin"


def _key(obj) -> tuple[str, object]:
    return obj._meta.label_lower, obj.pk


def _done(request) -> set:
    """The records this request has already audited, so a later hook does not record them twice."""
    if not hasattr(request, "_admin_audited"):
        request._admin_audited = set()
    return request._admin_audited


def _choices(obj) -> dict:
    """Many-to-many choices (an account's groups and permissions) as sorted lists of ids."""
    if obj.pk is None:
        return {}
    return {
        field.name: sorted(getattr(obj, field.name).values_list("pk", flat=True))
        for field in obj._meta.many_to_many
    }


def _stored(obj):
    return type(obj)._default_manager.filter(pk=obj.pk).first() if obj.pk is not None else None


class AuditedAdmin(admin.ModelAdmin):
    """A model admin whose adds, changes and removals are audited. Subclasses may rename the actions."""

    added, changed, removed = "create", "update", "delete"

    def _record(self, request, action, obj, *, before=None, after=None, entity_id=None):
        from audit.services import record

        record(request, action, obj, before=before, after=after, entity_id=entity_id, reason=REASON)
        _done(request).add(_key(obj) if entity_id is None else (obj._meta.label_lower, entity_id))

    def save_model(self, request, obj, form, change):
        from audit.services import snapshot

        stored = _stored(obj) if change else None
        before = snapshot(stored) if stored is not None else None
        if not hasattr(request, "_admin_choices"):
            request._admin_choices = {}
        request._admin_choices[obj._meta.label_lower] = _choices(stored) if stored is not None else {}
        super().save_model(request, obj, form, change)
        self._record(request, self.changed if change else self.added, obj, before=before, after=snapshot(obj))

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance
        if not obj._meta.many_to_many or obj.pk is None:
            return
        after = _choices(obj)
        before = getattr(request, "_admin_choices", {}).get(obj._meta.label_lower) or {k: [] for k in after}
        if after != before:
            self._record(request, self.changed, obj, before=before, after=after)

    def save_formset(self, request, form, formset, change):
        """Rows edited inline on another record's page (a module's items, a user's roles)."""
        from audit.services import snapshot

        earlier, removed = {}, {}
        for inline in formset.initial_forms:
            stored = _stored(inline.instance)
            if stored is not None:
                earlier[stored.pk] = snapshot(stored)
                removed[id(inline.instance)] = stored.pk
        super().save_formset(request, form, formset, change)
        for obj in formset.new_objects:
            self._record(request, "create", obj, after=snapshot(obj))
        for obj, _fields in formset.changed_objects:
            self._record(request, "update", obj, before=earlier.get(obj.pk), after=snapshot(obj))
        for obj in formset.deleted_objects:  # deleting clears obj.pk: the id was kept before the save
            pk = removed.get(id(obj), obj.pk)
            self._record(request, "delete", obj, before=earlier.get(pk), entity_id=pk)

    def log_addition(self, request, obj, message):
        entry = super().log_addition(request, obj, message)
        self._fallback(request, obj, self.added)
        return entry

    def log_change(self, request, obj, message):
        entry = super().log_change(request, obj, message)
        self._fallback(request, obj, self.changed)
        return entry

    def _fallback(self, request, obj, action):
        """A save the hooks above did not see (the admin's password form saves the account itself)."""
        from audit.services import snapshot

        if _key(obj) not in _done(request):
            self._record(request, action, obj, after=snapshot(obj))

    def delete_model(self, request, obj):
        from audit.services import snapshot

        before, pk = snapshot(obj), obj.pk
        super().delete_model(request, obj)
        self._record(request, self.removed, obj, before=before, entity_id=pk)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            self.delete_model(request, obj)


def audited(admin_class: type[admin.ModelAdmin] | None) -> type[admin.ModelAdmin]:
    """The admin class with AuditedAdmin mixed in front, unless it already has it."""
    admin_class = admin_class or admin.ModelAdmin
    if issubclass(admin_class, AuditedAdmin):
        return admin_class
    return type(admin_class.__name__, (AuditedAdmin, admin_class), {"__module__": admin_class.__module__})
