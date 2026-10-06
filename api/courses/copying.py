"""Copying a course's content from an earlier term, and every date on a site in one place (item 2.18).

A copy takes modules, items (files as new stored copies), release dates and assignments. It never takes
people, groups, submissions, marks, completions or announcements, nor items under review or withdrawn
after a takedown request. Every date copied can be moved by the same number of days, so last term's
course opens with this term's dates.

The date manager lists every dated thing on a site (when modules and items are shown, when assignments
open and are due) and changes many of them at once, or moves all of them by a number of days.
"""

from datetime import date, datetime, timedelta

from django.core.files import File
from django.db import transaction
from django.utils import timezone

from assessments.models import Assignment
from audit.services import record, snapshot
from courses import richtext, storage
from courses.models import ContentItem, CourseSite, ItemCompletion, Module
from courses.release import taken_down
from video.copying import copy_video

# (kind, field) -> model; the fields the date manager may change.
DATED = {
    ("module", "available_from"): Module,
    ("item", "available_from"): ContentItem,
    ("assignment", "opens_at"): Assignment,
    ("assignment", "due_at"): Assignment,
}
REQUIRED = {("assignment", "due_at")}


def _of_site(model, site: CourseSite):
    if model is Module:
        return Module.objects.filter(site=site)
    if model is ContentItem:
        return ContentItem.objects.filter(module__site=site)
    return Assignment.objects.filter(site=site)


def dated_things(site: CourseSite) -> list[dict]:
    """Every date on the site that can be changed, in date order with the undated last."""
    rows = []
    for (kind, name), model in DATED.items():
        for obj in _of_site(model, site).order_by("id"):
            rows.append(
                {"kind": kind, "id": obj.id, "title": obj.title, "field": name, "value": getattr(obj, name)}
            )
    far = datetime.max.replace(tzinfo=timezone.get_current_timezone())
    return sorted(rows, key=lambda r: (r["value"] is None, r["value"] or far, r["kind"], r["id"]))


def earliest(site: CourseSite) -> datetime | None:
    values = [row["value"] for row in dated_things(site) if row["value"] is not None]
    return min(values) if values else None


def offset_to(site: CourseSite, start: date) -> timedelta:
    """The shift that moves the site's earliest date onto `start`, in whole days."""
    first = earliest(site)
    if first is None:
        return timedelta(0)
    return timedelta(days=(start - timezone.localtime(first).date()).days)


def _check_assignment(assignment: Assignment) -> str | None:
    if assignment.opens_at and assignment.opens_at >= assignment.due_at:
        return f"“{assignment.title}” would open after it is due."
    return None


@transaction.atomic
def update_dates(site: CourseSite, changes: list[dict], request) -> int:
    """Apply [{kind, id, field, value}] to the site's records. All or nothing; raises ValueError with the
    reason for the first change that cannot be made."""
    touched: dict[tuple, tuple] = {}
    for number, change in enumerate(changes, start=1):
        key = (change["kind"], change["field"])
        model = DATED.get(key)
        if model is None:
            raise ValueError(f"Change {number}: a {change['kind']} has no date called {change['field']}.")
        if change["value"] is None and key in REQUIRED:
            raise ValueError(f"Change {number}: an assignment must have a due date.")
        obj_key = (model, change["id"])
        if obj_key not in touched:
            obj = _of_site(model, site).filter(pk=change["id"]).first()
            if obj is None:
                raise ValueError(f"Change {number}: there is no such {change['kind']} on this course.")
            touched[obj_key] = (obj, snapshot(obj))
        setattr(touched[obj_key][0], change["field"], change["value"])
    for obj, before in touched.values():
        if isinstance(obj, Assignment):
            problem = _check_assignment(obj)
            if problem:
                raise ValueError(problem)
        obj.updated_by = request.user
        obj.save()
        record(request, "update", obj, before=before, after=snapshot(obj))
    return len(touched)


@transaction.atomic
def shift_dates(site: CourseSite, offset: timedelta, request) -> int:
    """Move every date on the site by `offset`. Returns the number of records changed."""
    changed = 0
    if not offset:
        return 0
    for model in (Module, ContentItem, Assignment):
        names = [name for (_, name), m in DATED.items() if m is model]
        for obj in _of_site(model, site):
            before = snapshot(obj)
            moved = False
            for name in names:
                value = getattr(obj, name)
                if value is not None:
                    setattr(obj, name, value + offset)
                    moved = True
            if moved:
                obj.updated_by = request.user
                obj.save()
                record(request, "update", obj, before=before, after=snapshot(obj))
                changed += 1
    return changed


class CopyRefused(Exception):
    pass


def _plus(value, offset):
    return value + offset if value is not None else None


@transaction.atomic
def copy_content(source: CourseSite, target: CourseSite, offset: timedelta, request, replace=False) -> dict:
    """Copy the source's modules, items and assignments into the target, every date moved by `offset`."""
    if source.pk == target.pk:
        raise CopyRefused("Choose a different course to copy from.")
    if target.modules.exists():
        if not replace:
            raise CopyRefused(
                "This course already has content. Copy into it only if its present content may be "
                "replaced (send replace_existing)."
            )
        if ItemCompletion.objects.filter(item__module__site=target).exists():
            raise CopyRefused(
                "Students have already worked through this course's content, so it cannot be replaced."
            )
        for module in target.modules.all():
            before, entity_id = snapshot(module), module.pk
            module.delete()
            record(request, "delete", module, before=before, entity_id=entity_id)
    items = list(
        ContentItem.objects.filter(module__site=source).select_related("module").order_by("module", "id")
    )
    # Material taken down, or waiting for a takedown decision, does not travel to a new term.
    left_out = [item.title for item in items if taken_down(item)]
    items = [item for item in items if not taken_down(item)]
    storage.require_room(
        target, sum(i.file_size for i in items if i.file or i.kind == ContentItem.Kind.VIDEO)
    )

    user = request.user
    modules: dict[int, Module] = {}
    copies: dict[int, ContentItem] = {}
    missing: list[str] = []
    for module in source.modules.all():
        modules[module.id] = Module.objects.create(
            site=target,
            title=module.title,
            position=module.position,
            available_from=_plus(module.available_from, offset),
            created_by=user,
            updated_by=user,
        )
    for item in items:
        copy = ContentItem(
            module=modules[item.module_id],
            kind=item.kind,
            title=item.title,
            body=item.body,
            url=item.url,
            position=item.position,
            is_published=item.is_published,
            available_from=_plus(item.available_from, offset),
            licence=item.licence,
            open_licence=item.open_licence,
            source=item.source,
            created_by=user,
            updated_by=user,
        )
        if item.file:
            try:
                with item.file.open("rb") as handle:
                    copy.file.save(item.original_name or item.file.name, File(handle), save=False)
                copy.original_name, copy.file_size = item.original_name, item.file_size
            except FileNotFoundError:
                missing.append(item.title)
        if item.kind == ContentItem.Kind.VIDEO:
            copy.file_size = item.file_size  # the video's copies, poster and captions (item 4.06)
        copy.save()
        if item.kind == ContentItem.Kind.PACKAGE:
            from packages.services import copy_package  # items 5.12, 5.13: the package's settings too

            copy_package(item, copy)
        if item.kind == ContentItem.Kind.VIDEO:
            try:
                copy_video(item, copy, user)
            except FileNotFoundError:
                missing.append(item.title)
        copies[item.id] = copy
    mapping = {old: new.id for old, new in copies.items()}
    for item in items:
        copy = copies[item.id]
        if item.requires_item_id in copies:
            copy.requires_item = copies[item.requires_item_id]
        if item.body:
            copy.body = richtext.replace_image_ids(item.body, mapping)
        copy.save()
        record(request, "create", copy, after={**snapshot(copy), "copied_from": item.id})
    for module in source.modules.all():
        if module.requires_item_id in copies:
            modules[module.id].requires_item = copies[module.requires_item_id]
            modules[module.id].save(update_fields=["requires_item"])
        record(
            request,
            "create",
            modules[module.id],
            after={**snapshot(modules[module.id]), "copied_from": module.id},
        )

    assignments = 0
    existing = set(target.assignments.values_list("title", flat=True))
    for work in source.assignments.all():
        if work.title in existing:
            continue
        copy = Assignment.objects.create(
            site=target,
            title=work.title,
            instructions=work.instructions,
            opens_at=_plus(work.opens_at, offset),
            due_at=work.due_at + offset,
            max_mark=work.max_mark,
            weight=work.weight,
            allow_late=work.allow_late,
            is_published=work.is_published,
            created_by=user,
            updated_by=user,
        )
        record(request, "create", copy, after={**snapshot(copy), "copied_from": work.id})
        assignments += 1
    summary = {
        "modules": len(modules),
        "items": len(copies),
        "assignments": assignments,
        "offset_days": offset.days,
        "missing_files": missing,
        "left_out": left_out,
    }
    record(request, "copy", target, after={"from": source.id, **summary})
    return summary
