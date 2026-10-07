"""The term life-cycle (item 7.12): open, closed to submissions, read-only for appeals, archived.

A site follows the term named by its term_code. Its phase is worked out from the calendar whenever it is
asked for, so a site closes at the exact moment its grace runs out, whether or not the nightly job has run:

- open: before the end of the term's close date (a site whose code is not in the calendar is always open);
- grace: within TERM_GRACE_DAYS (or the term's own grace) after the close date, still taking work;
- closed: read-only, kept for appeals; only a course administrator or an administrator may change it;
- archived: a read-only export has been kept (terms.models.SiteArchive) and no one changes it any more.

The nightly job (run) records each term's close, tells the teaching staff, and archives the sites of terms
closed for longer than the retention schedule's period for course sites (privacy rule "course-sites").
Archiving destroys nothing: records go only through the schedule's disposal runs, approved by two people.
"""

import hashlib
import json
import logging
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.apps import apps
from django.conf import settings
from django.core.files import File
from django.db import models, transaction
from django.db.models.fields.files import FieldFile
from django.utils import timezone

from audit.services import record, snapshot

log = logging.getLogger(__name__)

OPEN, GRACE, CLOSED, ARCHIVED = "open", "grace", "closed", "archived"
LOCKED = (CLOSED, ARCHIVED)
ARCHIVE_RULE = "course-sites"


def grace_days(term) -> int:
    return settings.TERM_GRACE_DAYS if term.grace_days is None else term.grace_days


def closes_at(term) -> datetime:
    """The moment work stops being taken without grace: the end of the close date, local time."""
    return timezone.make_aware(datetime.combine(term.closes_on + timedelta(days=1), time.min))


def locks_at(term) -> datetime:
    """The moment the term's sites become read-only: the close date's end plus the grace."""
    return closes_at(term) + timedelta(days=grace_days(term))


def archive_months() -> int:
    from privacy.models import RetentionRule

    months = RetentionRule.objects.filter(code=ARCHIVE_RULE).values_list("keep_months", flat=True).first()
    return settings.TERM_ARCHIVE_MONTHS if months is None else months


def archive_due_on(term, months: int | None = None) -> date:
    from privacy.retention import months_after

    return months_after(timezone.localdate(locks_at(term)), archive_months() if months is None else months)


def term_phase(term, now: datetime | None = None) -> str:
    """The term as a whole: upcoming, teaching, ended (still taking work), grace, closed or archived."""
    now = now or timezone.now()
    today = timezone.localdate(now)
    if term.archived_at is not None:
        return ARCHIVED
    if now >= locks_at(term):
        return CLOSED
    if now >= closes_at(term):
        return GRACE
    if today < term.starts_on:
        return "upcoming"
    if today <= term.ends_on:
        return "teaching"
    return "ended"


@dataclass
class SitePhase:
    phase: str
    term: object | None

    @property
    def locked(self) -> bool:
        return self.phase in LOCKED


def phase_from(term, archived: bool, now: datetime | None = None) -> SitePhase:
    """A site's phase from its term (None when not in the calendar) and whether it has been archived."""
    if archived:
        return SitePhase(ARCHIVED, term)
    if term is None:
        return SitePhase(OPEN, None)
    phase = term_phase(term, now)
    return SitePhase(phase if phase in (GRACE, CLOSED) else OPEN, term)


def site_phase(site, now: datetime | None = None) -> SitePhase:
    from terms.models import SiteArchive, Term

    term = Term.objects.filter(code=site.term_code).first() if site.term_code else None
    return phase_from(term, SiteArchive.objects.filter(site_id=site.pk).exists(), now)


def explain(site, phase: SitePhase) -> str:
    """The sentence a person sees when a closed site refuses a change."""
    if phase.phase == ARCHIVED:
        return (
            f"{site.code} has been archived: its read-only record is kept and nothing on it can be changed."
        )
    day = timezone.localdate(locks_at(phase.term) - timedelta(days=1)).strftime("%d/%m/%Y")
    return (
        f"{site.code} took its last work on {day} and is kept read-only for appeals. "
        "A course administrator can make a change if one is needed."
    )


# --- which records belong to a site -------------------------------------------------------------------------


def _site_path(model, depth: int = 3) -> str | None:
    """The lookup from a model to its course site through forward foreign keys ("assignment__site"), or
    None when the model does not belong to one. The field called "site" is preferred at each step."""
    from courses.models import CourseSite

    if model is CourseSite:
        return ""
    frontier: list[tuple[type, str]] = [(model, "")]
    for _ in range(depth):
        following: list[tuple[type, str]] = []
        for current, path in frontier:
            fields = [
                f
                for f in current._meta.concrete_fields
                if isinstance(f, models.ForeignKey) and f.related_model is not None
            ]
            fields.sort(key=lambda f: f.name != "site")
            for field in fields:
                step = f"{path}__{field.name}" if path else field.name
                if field.related_model is CourseSite:
                    return step
                if field.related_model._meta.app_label in {"auth", "people", "iam", "contenttypes"}:
                    continue
                following.append((field.related_model, step))
        frontier = following
    return None


# Records that belong to a site but are not its work or content, so a closed site still takes them: following
# a forum, the public check of a certificate, and private messages (an appeal is often raised by message).
NOT_GUARDED = {
    "forums.subscription",
    "certificates.certificatecheck",
    "messaging.conversation",
    "messaging.message",
    "messaging.participant",
}


def site_models() -> dict[str, str]:
    """Every model that belongs to a course site, with its lookup to the site (label -> path)."""
    found = {}
    for model in apps.get_models():
        label = model._meta.label_lower
        if label in NOT_GUARDED or label == "terms.sitearchive":
            continue
        path = _site_path(model)
        if path is not None:
            found[label] = path
    return found


def site_id_of(instance, path: str) -> int | None:
    """The id of the site a record belongs to, following the path one step at a time."""
    if path == "":
        return instance.pk
    target = instance
    steps = path.split("__")
    for step in steps[:-1]:
        target = getattr(target, step, None)
        if target is None:
            return None
    return getattr(target, f"{steps[-1]}_id", None)


# --- the nightly job ----------------------------------------------------------------------------------------


def _sites_of(term):
    from courses.models import CourseSite

    return CourseSite.objects.filter(term_code=term.code)


def close_term(term, now: datetime) -> int:
    """Record that the term's sites are closed, once, and tell their teaching staff."""
    from courses.models import Membership
    from notifications.services import notify

    sites = list(_sites_of(term))
    with transaction.atomic():
        term.closed_at = now
        term.save(update_fields=["closed_at", "updated_at"])
        record(
            None,
            "closed",
            term,
            after={"sites": [s.code for s in sites], "locked_at": locks_at(term).isoformat()},
            reason="Term life-cycle: the close date and its grace have passed",
        )
    for site in sites:
        teachers = [
            m.person.user
            for m in Membership.objects.filter(
                site=site, is_active=True, role__in=["lecturer", "assistant"]
            ).select_related("person__user")
            if m.person.user_id
        ]
        notify(
            teachers,
            title=f"{site.code} is now closed",
            body=(
                "The term has ended: the site takes no more work and is kept read-only for appeals. "
                "Ask a course administrator if a change is needed."
            ),
            link=f"/sites/{site.pk}",
            dedupe_key=f"term-closed:{site.pk}",
        )
    return len(sites)


def _people(site) -> list[dict]:
    return [
        {
            "person": m.person_id,
            "number": m.person.external_id,
            "name": m.person.full_name,
            "role": m.role,
            "active": m.is_active,
        }
        for m in site.memberships.select_related("person").order_by("role", "person__external_id")
    ]


def build_archive(site, *, by=None):
    """Write the site's read-only export: every record that belongs to it, as the audit log sees records
    (encrypted values masked), and every stored file, in one zip file with a manifest. Returns the archive."""
    from terms.models import SiteArchive

    rows: dict[str, list[dict]] = {}
    stored: list[FieldFile] = []
    for label, path in sorted(site_models().items()):
        model = apps.get_model(label)
        qs = model.objects.filter(pk=site.pk) if path == "" else model.objects.filter(**{path: site.pk})
        file_fields = [f.name for f in model._meta.concrete_fields if isinstance(f, models.FileField)]
        found = []
        for obj in qs.order_by("pk").iterator():
            found.append(snapshot(obj))
            stored.extend(getattr(obj, name) for name in file_fields if getattr(obj, name))
        if found:
            rows[label] = found
    buffer = tempfile.TemporaryFile()  # on disk, not in memory: a site's files can be large
    copied, missing = 0, []
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        for field_file in stored:
            try:
                with field_file.storage.open(field_file.name, "rb") as source:
                    with bundle.open(f"files/{field_file.name}", "w", force_zip64=True) as target:
                        shutil.copyfileobj(source, target)
                copied += 1
            except FileNotFoundError:
                missing.append(field_file.name)
        manifest = {
            "site": {"id": site.pk, "code": site.code, "title": site.title, "term_code": site.term_code},
            "made_at": timezone.now().isoformat(),
            "people": _people(site),
            "counts": {label: len(found) for label, found in rows.items()},
            "files_copied": copied,
            "files_missing": missing,
            "note": (
                "Read-only export kept when the term was archived (GSA LMS item 7.12). Records are as the "
                "audit log shows them: encrypted values are masked. Files are under files/."
            ),
        }
        bundle.writestr("manifest.json", json.dumps(manifest, indent=2, default=str))
        bundle.writestr("records.json", json.dumps(rows, indent=1, default=str))
    digest, size = hashlib.sha256(), buffer.tell()
    buffer.seek(0)
    for chunk in iter(lambda: buffer.read(1 << 20), b""):
        digest.update(chunk)
    buffer.seek(0)
    archive = SiteArchive(
        site=site,
        term_code=site.term_code,
        size=size,
        sha256=digest.hexdigest(),
        records=sum(len(found) for found in rows.values()),
        files=copied,
        made_by=by,
    )
    with buffer:
        archive.file.save(f"{site.code}-{timezone.localdate():%Y%m%d}.zip", File(buffer), save=False)
    with transaction.atomic():
        archive.save()
        record(
            None,
            "archived",
            site,
            after={
                "archive": archive.pk,
                "sha256": archive.sha256,
                "records": archive.records,
                "files": copied,
            },
            reason="Term life-cycle: the retention period for course sites has passed",
        )
    return archive


def archive_term(term, now: datetime) -> int:
    from terms.models import SiteArchive

    made = 0
    for site in _sites_of(term).exclude(pk__in=SiteArchive.objects.values("site_id")):
        build_archive(site)
        made += 1
    term.archived_at = now
    term.save(update_fields=["archived_at", "updated_at"])
    record(None, "archived", term, after={"sites_archived": made}, reason="Term life-cycle")
    return made


def run(now: datetime | None = None) -> dict:
    """Every night: take the calendar from the SRMS when it offers one, close the terms whose grace has run
    out, and archive the terms closed for longer than the retention period."""
    from terms.models import Term

    now = now or timezone.now()
    result = {"synced": None, "closed": 0, "archived_sites": 0}
    if settings.TERMS_FROM_SRMS:
        result["synced"] = sync_from_srms()
    months = archive_months()
    for term in Term.objects.filter(closed_at__isnull=True):
        if now >= locks_at(term):
            close_term(term, now)
            result["closed"] += 1
    for term in Term.objects.filter(closed_at__isnull=False, archived_at__isnull=True):
        if timezone.localdate(now) >= archive_due_on(term, months):
            result["archived_sites"] += archive_term(term, now)
    log.info("terms.lifecycle %s", result)
    return result


def sync_from_srms() -> dict:
    """The term calendar from the SRMS's integration API (/api/v1/integration/terms/), when GSA turns
    TERMS_FROM_SRMS on and the SRMS offers it. The SRMS gives the code, name and teaching dates; the close
    date defaults to TERM_CLOSE_AFTER_DAYS after the end of teaching, and a close date or grace a course
    administrator has set in the LMS is kept."""
    from integration.client import IntegrationError, pages
    from terms.models import Term

    counts = {"created": 0, "updated": 0, "failed": False}
    try:
        rows = list(pages(settings.SRMS_API_URL, settings.SRMS_API_KEY, "/api/v1/integration/terms/"))
    except IntegrationError:
        log.exception("terms.sync_from_srms failed")
        counts["failed"] = True
        return counts
    for row in rows:
        starts, ends = date.fromisoformat(row["starts"]), date.fromisoformat(row["ends"])
        term = Term.objects.filter(code=row["code"]).first()
        if term is None:
            term = Term.objects.create(
                code=row["code"],
                name=row.get("name") or row["code"],
                starts_on=starts,
                ends_on=ends,
                closes_on=ends + timedelta(days=settings.TERM_CLOSE_AFTER_DAYS),
                source=Term.Source.SRMS,
            )
            record(None, "create", term, after=snapshot(term), reason="Term calendar from the SRMS")
            counts["created"] += 1
            continue
        changed = (term.name, term.starts_on, term.ends_on) != (row.get("name") or term.name, starts, ends)
        if changed and term.closed_at is None:
            before = snapshot(term)
            term.name, term.starts_on, term.ends_on = row.get("name") or term.name, starts, ends
            term.closes_on = max(term.closes_on, ends)
            term.source = Term.Source.SRMS
            term.save()
            record(
                None,
                "update",
                term,
                before=before,
                after=snapshot(term),
                reason="Term calendar from the SRMS",
            )
            counts["updated"] += 1
    return counts
