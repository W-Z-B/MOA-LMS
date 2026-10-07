"""The LMS's own store of xAPI statements (item 6.09), for its packaged content.

This is deliberately not a general learning record store. It keeps statements about the LMS's own packages:
- H5P exercises report through it (the player in the page passes on H5P's xAPI events);
- SCORM results are written into it by the LMS when a part is completed, passed or failed, or scored;
- teaching staff read the statements of their own courses, by activity, learner, attempt or date.

Rules that make it safe to accept statements from a learner's browser:
- a statement is accepted only for an attempt the learner holds (context.registration is the attempt's
  registration), and only about that package's activities (object.id is the package's activity id, or below
  it, as H5P sub-content is);
- the actor is never taken from the statement: the LMS writes the learner's account (their number at the
  LMS's address) and itself as the authority;
- statements cannot be voided, changed or fetched by id from outside, and there is no state, activity
  profile or agent profile API. A general LRS (for outside tools, cmi5 or a data warehouse) would be its
  own decision (ADR 0014).
"""

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from packages.models import ContentPackage, PackageAttempt, Statement
from packages.services import Refused, activity_iri, finish_changes, state_of

VERSION = "1.0.3"
MAX_STATEMENT_BYTES = 64 * 1024
MAX_BATCH = 50
ADL = "http://adlnet.gov/expapi/verbs/"
RESULT_VERBS = {f"{ADL}completed", f"{ADL}answered", f"{ADL}passed", f"{ADL}failed", f"{ADL}scored"}


def lms_agent() -> dict:
    return {"objectType": "Agent", "name": settings.CERTIFICATE_ORGANISATION, "account": {
        "homePage": settings.PUBLIC_URL, "name": "lms"}}  # fmt: skip


def actor_of(attempt: PackageAttempt) -> dict:
    """The learner as xAPI names them: their account at the LMS's address, never their name or email."""
    name = attempt.person.external_id if attempt.person else f"user-{attempt.user_id}"
    return {"objectType": "Agent", "account": {"homePage": settings.PUBLIC_URL, "name": name}}


def _when(value) -> datetime:
    parsed = parse_datetime(value) if isinstance(value, str) else None
    if parsed is None:
        return timezone.now()
    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed, UTC)


def _save(attempt: PackageAttempt, body: dict) -> Statement:
    """Keep a statement about the attempt, with the LMS's own actor, authority, id and times."""
    package = attempt.package
    now = timezone.now()
    statement_id = body.get("id")
    try:
        statement_id = uuid.UUID(str(statement_id)) if statement_id else uuid.uuid4()
    except ValueError as error:
        raise Refused("bad_statement", "A statement's id must be a UUID.", 400) from error
    if Statement.objects.filter(pk=statement_id).exists():
        raise Refused("duplicate_statement", "A statement with that id is already stored.", 409)
    context = dict(body.get("context") or {})
    context["registration"] = str(attempt.registration)
    timestamp = _when(body.get("timestamp"))
    kept = {
        **{k: v for k, v in body.items() if k in ("verb", "object", "result", "attachments")},
        "id": str(statement_id),
        "actor": actor_of(attempt),
        "authority": lms_agent(),
        "context": context,
        "timestamp": timestamp.isoformat(),
        "stored": now.isoformat(),
        "version": VERSION,
    }
    return Statement.objects.create(
        id=statement_id,
        site=package.site,
        package=package,
        attempt=attempt,
        person=attempt.person,
        verb=body["verb"]["id"][:300],
        activity=body["object"]["id"][:500],
        statement=kept,
        timestamp=timestamp,
    )


def check_shape(body, package: ContentPackage) -> None:
    if not isinstance(body, dict):
        raise Refused("bad_statement", "Each statement must be a JSON object.", 400)
    if len(json.dumps(body)) > MAX_STATEMENT_BYTES:
        raise Refused("bad_statement", "A statement may be at most 64 KB.", 400)
    verb, target = body.get("verb"), body.get("object")
    if not isinstance(verb, dict) or not isinstance(verb.get("id"), str) or ":" not in verb["id"]:
        raise Refused("bad_statement", "A statement needs a verb with an id (an IRI).", 400)
    if not isinstance(target, dict) or not isinstance(target.get("id"), str):
        raise Refused("bad_statement", "A statement needs an object with an id.", 400)
    base = activity_iri(package)
    if target.get("objectType", "Activity") != "Activity" or not (
        target["id"] == base or target["id"].startswith((f"{base}/", f"{base}?"))
    ):
        raise Refused(
            "foreign_activity",
            "The LMS keeps statements only about its own packages' activities.",
            400,
        )
    if "result" in body and not isinstance(body["result"], dict):
        raise Refused("bad_statement", "A statement's result must be a JSON object.", 400)


def attempt_for(body, person) -> PackageAttempt:
    """The attempt a statement belongs to, by its context.registration; it must be the sender's own."""
    registration = (body.get("context") or {}).get("registration") if isinstance(body, dict) else None
    try:
        registration = uuid.UUID(str(registration))
    except ValueError as error:
        raise Refused(
            "no_registration", "Give the attempt's registration in context.registration.", 400
        ) from error
    attempt = (
        PackageAttempt.objects.select_related("package__item__module__site", "person")
        .filter(registration=registration)
        .first()
    )
    if attempt is None or attempt.user_id is None or attempt.user_id != getattr(person, "pk", person):
        raise Refused("unknown_attempt", "No attempt of yours has that registration.", 400)
    return attempt


def _result_fraction(result: dict) -> Decimal | None:
    score = result.get("score")
    if not isinstance(score, dict):
        return None
    try:
        if score.get("scaled") is not None:
            return min(max(Decimal(str(score["scaled"])), Decimal(0)), Decimal(1))
        if score.get("raw") is not None and score.get("max"):
            low = Decimal(str(score.get("min") or 0))
            high = Decimal(str(score["max"]))
            if high > low:
                return min(max((Decimal(str(score["raw"])) - low) / (high - low), Decimal(0)), Decimal(1))
    except (ArithmeticError, ValueError):
        return None
    return None


def apply_h5p(request, attempt: PackageAttempt, body: dict) -> None:
    """A result about the H5P content as a whole (not one of its sub-contents) completes the attempt."""
    package = attempt.package
    if package.standard != ContentPackage.Standard.H5P or body["object"]["id"] != activity_iri(package):
        return
    result = body.get("result") or {}
    if body["verb"]["id"] not in RESULT_VERBS or not result:
        return
    before = state_of(attempt)
    fraction = _result_fraction(result)
    if fraction is not None:
        attempt.score = fraction.quantize(Decimal("0.0001"))
    if result.get("completion") is True or body["verb"]["id"] == f"{ADL}completed" or fraction is not None:
        attempt.completion = PackageAttempt.Completion.COMPLETED
    if result.get("success") is True:
        attempt.success = PackageAttempt.Success.PASSED
    elif result.get("success") is False:
        attempt.success = PackageAttempt.Success.FAILED
    attempt.runtime = {**attempt.runtime, "h5p": {**state_of(attempt), "verb": body["verb"]["id"]}}
    finish_changes(request, attempt, before)


def accept(request, bodies: list) -> list[str]:
    """Keep statements sent by a learner's player. All or nothing; returns their ids."""
    from django.db import transaction

    if not bodies:
        raise Refused("bad_statement", "Send a statement or a list of statements.", 400)
    if len(bodies) > MAX_BATCH:
        raise Refused("bad_statement", f"Send at most {MAX_BATCH} statements at once.", 400)
    ids = []
    with transaction.atomic():
        for body in bodies:
            attempt = attempt_for(body, request.user)
            check_shape(body, attempt.package)
            saved = _save(attempt, body)
            ids.append(str(saved.id))
            apply_h5p(request, attempt, body)
    return ids


def result_statement(attempt: PackageAttempt, before: dict, after: dict) -> None:
    """When a SCORM attempt is completed, passed, failed or newly scored, the LMS says so as a statement."""
    if attempt.package.standard == ContentPackage.Standard.H5P:
        return  # H5P sends its own statements
    if after["success"] != before["success"] and after["success"] in ("passed", "failed"):
        verb = after["success"]
    elif after["completion"] != before["completion"] and after["completion"] == "completed":
        verb = "completed"
    elif after["score"] != before["score"] and after["score"] is not None:
        verb = "scored"
    else:
        return
    result = {"completion": after["completion"] == "completed"}
    if after["success"] in ("passed", "failed"):
        result["success"] = after["success"] == "passed"
    if after["score"] is not None:
        result["score"] = {"scaled": float(after["score"])}
    _save(
        attempt,
        {
            "verb": {"id": f"{ADL}{verb}", "display": {"en-GB": verb}},
            "object": {
                "objectType": "Activity",
                "id": activity_iri(attempt.package),
                "definition": {"name": {"en-GB": attempt.package.item.title}},
            },
            "result": result,
        },
    )


def visible(statements, user):
    """Statements on the courses the user teaches (all for course administrators)."""
    from courses.access import taught_sites

    return statements.filter(site__in=taught_sites(user))


def as_json(statement: Statement) -> dict:
    return statement.statement
