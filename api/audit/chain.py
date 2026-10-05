"""Chained fingerprints over the audit log, so that a changed or removed row shows (item 1.17).

Every row carries `chain`: an HMAC-SHA256 of the row before it and of its own content, under a key
derived from FIELD_ENCRYPTION_KEY. The trigger of migration 0002 already refuses UPDATE and DELETE, but a
database superuser can switch it off. The key is not in the database, so whoever changes a row there cannot
work out the fingerprints that would hide it; walking the chain finds the first row that no longer fits.

Rows are written one at a time under a transaction-wide advisory lock, so ids, commit order and the order of
the chain are the same. A check also confirms that the newest row it saw last time is still there, so
removing the most recent rows shows too.
"""

import datetime
import hashlib
import hmac
import ipaddress
import json
import logging

from django.db import connection

from core.crypto import chain_key

log = logging.getLogger(__name__)
# Names the advisory lock that puts audit rows in a single line (any constant unique in the database).
CHAIN_LOCK = 4_202_610


def _address(value) -> str | None:
    """The same address however it was written: PostgreSQL keeps its own form of an IPv6 address."""
    if not value:
        return None
    try:
        return ipaddress.ip_address(value).packed.hex()
    except ValueError:
        return str(value)


def canonical(row) -> bytes:
    """The content of a row, in one fixed form. Changing this breaks every fingerprint already written."""
    at = row.at.astimezone(datetime.UTC).isoformat() if row.at else None
    content = [
        at,
        row.actor_id,
        row.action,
        row.entity,
        row.entity_id,
        row.before,
        row.after,
        _address(row.source_ip),
        row.subject,
        row.reason or "",
    ]
    return json.dumps(content, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def link(previous: str, row) -> str:
    return hmac.new(
        chain_key(), previous.encode("ascii") + b"\n" + canonical(row), hashlib.sha256
    ).hexdigest()


def lock() -> None:
    """Hold the chain until this transaction ends, so that the next row links to this one."""
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [CHAIN_LOCK])


def head() -> str:
    from audit.models import AuditLog

    return AuditLog.objects.order_by("-id").values_list("chain", flat=True).first() or ""


def walk() -> tuple[int, int | None, str, int | None]:
    """(rows that fit, id of the last of them, its fingerprint, id of the first row that does not fit)."""
    from audit.models import AuditLog

    previous, rows, last_id = "", 0, None
    fields = ("id", "at", "actor_id", "action", "entity", "entity_id", "before", "after", "source_ip")
    for row in AuditLog.objects.order_by("id").only(*fields, "subject", "reason", "chain").iterator(2000):
        if not hmac.compare_digest(link(previous, row), row.chain):
            return rows, last_id, previous, row.id
        previous, rows, last_id = row.chain, rows + 1, row.id
    return rows, last_id, previous, None


def verify(*, checked_by=None):
    """Walk the whole chain, compare it with the last good check, record the result and raise the alarm."""
    from audit.models import AuditCheck, AuditLog

    earlier = AuditCheck.objects.filter(intact=True).first()
    rows, last_id, last_chain, broken = walk()
    detail = ""
    if broken is not None:
        detail = (
            f"Entry {broken} no longer matches its fingerprint: it, or an entry just before it, "
            "was changed or removed."
        )
    elif earlier is not None and earlier.last_id is not None:
        then = AuditLog.objects.filter(pk=earlier.last_id).values_list("chain", flat=True).first()
        if then != earlier.last_chain:
            detail = (
                f"Entry {earlier.last_id}, the newest at the check of {earlier.checked_at:%d/%m/%Y %H:%M}, "
                "is missing or changed: entries were removed from the end of the log."
            )
    check = AuditCheck.objects.create(
        checked_by=checked_by,
        rows=rows,
        intact=not detail,
        last_id=last_id,
        last_chain=last_chain,
        first_broken_id=broken,
        detail=detail,
    )
    if check.intact:
        log.info("audit chain intact: %s entries, newest %s, fingerprint %s", rows, last_id, last_chain)
    else:
        log.error("audit chain broken: %s", detail)
        _raise_the_alarm(check)
    return check


def _raise_the_alarm(check) -> None:
    from iam.models import Role
    from notifications.models import Notification
    from notifications.services import notify, users_with_role

    recipients = set(users_with_role(Role.ADMINISTRATOR)) | set(users_with_role(Role.AUDITOR))
    notify(
        recipients,
        title="The audit log has been altered",
        body=f"{check.detail} Treat this as a security incident: keep the database as it is and record it.",
        link="/admin/audit",
        kind=Notification.Kind.ALERT,
        dedupe_key=f"audit-chain:{check.first_broken_id or check.last_id}",
    )
