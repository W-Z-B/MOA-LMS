"""Helpers that write audit rows. Called inside the caller's transaction."""

import datetime
import decimal
import uuid

from django.db import models
from django.db.models.fields.files import FieldFile

from audit.models import AuditLog
from core.crypto import fingerprint
from core.fields import EncryptedTextField
from core.net import client_ip

MASK = "***"


def _plain(value):
    if isinstance(value, datetime.datetime | datetime.date | datetime.time):
        return value.isoformat()
    if isinstance(value, decimal.Decimal | uuid.UUID):
        return str(value)
    if isinstance(value, FieldFile):  # an empty file field has a name of '' and no url
        return value.name or None
    return value


def masked(value) -> str | None:
    """How a sensitive value appears in the log: never the value, but a fingerprint that changes with it."""
    if not value:
        return None
    return f"{MASK}{fingerprint(str(value))}"


def snapshot(instance) -> dict:
    """JSON-safe copy of a model instance. Encrypted fields are masked, never logged in clear."""
    data = {}
    for field in instance._meta.concrete_fields:
        value = field.value_from_object(instance)
        if isinstance(field, EncryptedTextField):
            data[field.name] = masked(value)
        elif isinstance(field, models.BinaryField):
            data[field.name] = MASK if value else None
        else:
            data[field.name] = _plain(value)
    return data


def subject_of(instance) -> int | None:
    """The person (people.PersonRef) a record is about: the person, a student's work, or a membership."""
    label = instance._meta.label_lower
    if label == "people.personref":
        return instance.pk
    if label == "assessments.submission":
        return instance.student_id
    if label == "assessments.mark":
        return instance.submission.student_id
    if label == "insights.alert":  # an early alert is about the student (item 6.05)
        return instance.student_id
    if hasattr(instance, "person_id"):  # memberships, completions, correction requests
        return instance.person_id
    if label == "auth.user":  # sign-ins and account changes belong to the person's history too
        try:
            return instance.person.pk
        except Exception:  # noqa: BLE001 - an account with no person record
            return None
    return None


def _actor(request):
    user = getattr(request, "user", None)
    actor = user if user is not None and getattr(user, "is_authenticated", False) else None
    # A service key stands in for request.user without being a person: it is never stored as the actor.
    if actor is not None and getattr(actor, "pk", None) is None:
        actor = None
    return actor


def record_event(request, action: str, entity: str, *, after=None, reason: str = "") -> AuditLog:
    """An entry about the system rather than about one record: an export of the log, a check of its chain."""
    return AuditLog.objects.create(
        actor=_actor(request),
        action=action,
        entity=entity,
        after=after,
        source_ip=client_ip(request),
        reason=(reason or "")[:300],
    )


def record(
    request, action: str, instance, *, before=None, after=None, entity_id=None, reason: str = ""
) -> AuditLog:
    return AuditLog.objects.create(
        actor=_actor(request),
        action=action,
        entity=instance._meta.label_lower,
        entity_id=entity_id if entity_id is not None else instance.pk,
        before=before,
        after=after,
        source_ip=client_ip(request),
        subject=subject_of(instance),
        reason=(reason or "")[:300],
    )
