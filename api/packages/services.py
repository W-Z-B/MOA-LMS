"""Packages: putting one up, opening it in an attempt, what SCORM content commits, and how it counts.

Completion (items 5.12, 5.13). A SCORM part is complete when it reports "completed" or "passed" (SCORM 1.2
lesson_status; SCORM 2004 completion_status or success_status). A package is complete when every part is,
and a learner's completed attempt records the item as complete for release conditions and progress
(ItemCompletion, how="package"). An H5P exercise is complete when its main activity reports a result
(packages.xapi).

Score. Each part's score is its scaled score (SCORM 2004 cmi.score.scaled) or raw score between its minimum
and maximum (0 and 100 when the package does not say); the attempt's score is the mean of its parts' scores.

Coursework. A package with a weight above 0 counts like an assignment (assessments.services): the learner's
best scored attempt counts; a completed attempt that reports no score counts as full marks, as Moodle's
"learning objects" method does; nothing finished yet is "not_due". Packages have no closing date, so a
package never counts as zero. Scores come from the learner's browser: a determined student could forge one,
so a weight is the lecturer's choice for practice and low-stakes work.
"""

import json
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from audit.services import record, snapshot
from courses import release
from courses.models import ContentItem, ItemCompletion
from packages.archive import Checked
from packages.models import ContentPackage, PackageAttempt

FOUR_PLACES = Decimal("0.0001")
MAX_RUNTIME_BYTES = 256 * 1024  # SCORM 2004 suspend data alone may be 64,000 characters
DONE_12 = {"completed", "passed"}


class Refused(Exception):
    def __init__(self, code: str, detail: str, status: int = 409):
        super().__init__(detail)
        self.code, self.detail, self.status = code, detail, status


def activity_iri(package: ContentPackage) -> str:
    """The xAPI activity id of a package; its parts and H5P sub-content have ids below it."""
    return f"{settings.PUBLIC_URL}/xapi/activities/packages/{package.pk}"


# ---------------------------------------------------------------------------------------------------------
# Putting a package up, and copying one


def put_up(request, *, module, upload, checked: Checked, item_fields: dict, package_fields: dict):
    """Keep a checked package as a new item of the module, with its ContentPackage. Audited."""
    from django.db.models import Max

    from core.uploads import original_name

    user = request.user
    with transaction.atomic():
        last = module.items.aggregate(last=Max("position"))["last"] or 0
        item = ContentItem(
            module=module,
            kind=ContentItem.Kind.PACKAGE,
            position=last + 1,
            original_name=original_name(upload),
            file_size=upload.size,
            created_by=user,
            updated_by=user,
            **item_fields,
        )
        item.title = item.title or checked.title
        item.file.save(original_name(upload), upload, save=False)
        item.save()
        package = ContentPackage.objects.create(
            item=item,
            standard=checked.standard,
            version_label=checked.version_label,
            scos=[sco.as_dict() for sco in checked.scos],
            entries=checked.entries,
            unpacked_bytes=checked.unpacked_bytes,
            created_by=user,
            updated_by=user,
            **package_fields,
        )
        record(request, "create", item, after=snapshot(item))
        record(request, "create", package, after=snapshot(package))
    return package


def copy_package(source_item: ContentItem, copy: ContentItem, *, keep_category: bool = False) -> None:
    """Give a copied item (course copy, duplicate, library) the package settings of the one it came from.
    A gradebook category belongs to its course, so it travels only within the same course."""
    package = getattr(source_item, "package", None)
    if package is None:
        return
    ContentPackage.objects.create(
        item=copy,
        standard=package.standard,
        version_label=package.version_label,
        scos=package.scos,
        entries=package.entries,
        unpacked_bytes=package.unpacked_bytes,
        weight=package.weight,
        max_attempts=package.max_attempts,
        grade_category=package.grade_category if keep_category else None,
        created_by=copy.created_by,
        updated_by=copy.updated_by,
    )


# ---------------------------------------------------------------------------------------------------------
# Attempts


def attempts_of(package: ContentPackage, person) -> list[PackageAttempt]:
    return list(package.attempts.filter(person=person, is_preview=False).order_by("number"))


def launch(package: ContentPackage, *, user, person, learner: bool, new: bool) -> PackageAttempt:
    """The attempt to work in: the learner's open attempt, or a new one when asked for and allowed.
    Teaching staff get a preview attempt of their own, which never counts."""
    with transaction.atomic():
        ContentPackage.objects.select_for_update().filter(pk=package.pk).first()  # one attempt at a time
        if not learner:
            preview = package.attempts.filter(user=user, is_preview=True).order_by("-number").first()
            if preview is not None and not new:
                return preview
            return PackageAttempt.objects.create(
                package=package,
                person=person,
                user=user,
                is_preview=True,
                number=(preview.number + 1) if preview else 1,
            )
        mine = attempts_of(package, person)
        latest = mine[-1] if mine else None
        if latest is not None and not (new and latest.finished):
            return latest
        if package.max_attempts and len(mine) >= package.max_attempts:
            raise Refused(
                "no_attempts_left",
                f"You have used all {package.max_attempts} attempts at this package. "
                "Your best result counts.",
            )
        return PackageAttempt.objects.create(
            package=package, person=person, user=user, number=(latest.number + 1) if latest else 1
        )


def sco_of(package: ContentPackage, sco_id: str | None) -> dict:
    scos = package.scos or []
    if not scos:
        raise Refused("no_content", "The package has nothing to open.", 400)
    if not sco_id:
        return scos[0]
    for sco in scos:
        if sco["id"] == sco_id:
            return sco
    raise Refused("unknown_part", "The package has no part with that name.", 400)


def _get(data: dict, path: str, default=""):
    node = data
    for step in path.split("."):
        if not isinstance(node, dict) or step not in node:
            return default
        node = node[step]
    return node if node is not None else default


def initial_cmi(attempt: PackageAttempt, sco_id: str) -> dict:
    """What the run-time starts with: the learner's own details, and where they left off when they
    suspended. Only values a package may read back are given (the rest are the run-time's own)."""
    stored = (attempt.runtime.get(sco_id) or {}).get("cmi") or {}
    person = attempt.person
    learner_id = person.external_id if person else str(attempt.user_id)
    name = f"{person.last_name}, {person.first_name}".strip(", ") if person else "Preview"
    standard = attempt.package.standard
    if standard == ContentPackage.Standard.SCORM12:
        core = _get(stored, "core", {}) or {}
        resumed = core.get("exit") == "suspend"
        cmi = {
            "core": {
                "student_id": learner_id,
                "student_name": name,
                "entry": "resume" if resumed else "ab-initio",
            }
        }
        for key in ("lesson_status", "lesson_location"):
            if core.get(key):
                cmi["core"][key] = core[key]
        score = core.get("score")
        if isinstance(score, dict) and any(score.values()):
            cmi["core"]["score"] = {k: v for k, v in score.items() if k in ("raw", "min", "max") and v != ""}
        if stored.get("suspend_data"):
            cmi["suspend_data"] = stored["suspend_data"]
        return cmi
    resumed = stored.get("exit") == "suspend"
    cmi = {"learner_id": learner_id, "learner_name": name, "entry": "resume" if resumed else "ab-initio"}
    for key in ("completion_status", "success_status", "location", "suspend_data", "progress_measure"):
        value = stored.get(key)
        if value not in (None, "", "unknown", "not attempted"):
            cmi[key] = value
    score = stored.get("score")
    if isinstance(score, dict):
        kept = {
            k: v for k, v in score.items() if k in ("scaled", "raw", "min", "max") and v not in ("", None)
        }
        if kept:
            cmi["score"] = kept
    return cmi


def _decimal(value) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _fraction(raw, low, high) -> Decimal | None:
    raw = _decimal(raw)
    if raw is None:
        return None
    low = _decimal(low) if _decimal(low) is not None else Decimal(0)
    high = _decimal(high) if _decimal(high) is not None else Decimal(100)
    if high <= low:
        return None
    return min(max((raw - low) / (high - low), Decimal(0)), Decimal(1))


def read_cmi(standard: str, cmi: dict) -> dict:
    """completion, success and score (a fraction or None) from a SCORM part's CMI data."""
    if standard == ContentPackage.Standard.SCORM12:
        status = str(_get(cmi, "core.lesson_status") or "").lower()
        score = _fraction(
            _get(cmi, "core.score.raw"), _get(cmi, "core.score.min"), _get(cmi, "core.score.max")
        )
        completion = (
            "completed"
            if status in ("completed", "passed", "failed")
            else ("incomplete" if status in ("incomplete", "browsed") else "not_attempted")
        )
        success = status if status in ("passed", "failed") else "unknown"
        return {"completion": completion, "success": success, "score": score, "exit": _get(cmi, "core.exit")}
    completion_status = str(cmi.get("completion_status") or "").lower()
    success = str(cmi.get("success_status") or "").lower()
    scaled = _decimal(_get(cmi, "score.scaled"))
    if scaled is not None:
        score = min(max(scaled, Decimal(0)), Decimal(1))
    else:
        score = _fraction(_get(cmi, "score.raw"), _get(cmi, "score.min"), _get(cmi, "score.max"))
    if completion_status == "completed" or success in ("passed", "failed"):
        completion = "completed"
    elif completion_status == "incomplete":
        completion = "incomplete"
    else:
        completion = "not_attempted"
    return {
        "completion": completion,
        "success": success if success in ("passed", "failed") else "unknown",
        "score": score,
        "exit": cmi.get("exit", ""),
    }


def _sum_up(attempt: PackageAttempt) -> None:
    """The attempt's completion, success and score from its parts'."""
    parts = [attempt.runtime.get(sco["id"]) or {} for sco in attempt.package.scos]
    states = [p.get("completion", "not_attempted") for p in parts]
    if states and all(s == "completed" for s in states):
        attempt.completion = PackageAttempt.Completion.COMPLETED
    elif any(s != "not_attempted" for s in states):
        attempt.completion = PackageAttempt.Completion.INCOMPLETE
    successes = [p.get("success", "unknown") for p in parts]
    if "failed" in successes:
        attempt.success = PackageAttempt.Success.FAILED
    elif successes and all(s == "passed" for s in successes):
        attempt.success = PackageAttempt.Success.PASSED
    scores = [Decimal(p["score"]) for p in parts if p.get("score") is not None]
    attempt.score = (sum(scores) / len(scores)).quantize(FOUR_PLACES, ROUND_HALF_UP) if scores else None


def finish_changes(request, attempt: PackageAttempt, before: dict) -> None:
    """After a commit or a result: note when the attempt was completed, record the item as complete for the
    learner, and say so in the statements and the audit log."""
    from packages import xapi

    now = timezone.now()
    done = attempt.completion == PackageAttempt.Completion.COMPLETED or attempt.success == "passed"
    if done and attempt.completed_at is None:
        attempt.completed_at = now
    attempt.last_commit_at = now
    attempt.save()
    after = {"completion": attempt.completion, "success": attempt.success, "score": _s(attempt.score)}
    if after == before:
        return
    record(request, "package_result", attempt, before=before, after=after)
    xapi.result_statement(attempt, before, after)
    if done and not attempt.is_preview and attempt.person is not None:
        completion, created = release.complete(
            attempt.person, attempt.package.item, ItemCompletion.How.PACKAGE
        )
        if created:
            record(request, "create", completion, after=snapshot(completion))


def _s(value) -> str | None:
    return None if value is None else str(value)


def state_of(attempt: PackageAttempt) -> dict:
    return {"completion": attempt.completion, "success": attempt.success, "score": _s(attempt.score)}


def commit(request, attempt: PackageAttempt, sco_id: str, data) -> PackageAttempt:
    """Keep what a SCORM part committed ({"cmi": {...}} as scorm-again sends it) and work out the results."""
    package = attempt.package
    if package.standard == ContentPackage.Standard.H5P:
        raise Refused("not_scorm", "H5P content reports its results as statements, not commits.", 400)
    sco_of(package, sco_id)
    cmi = data.get("cmi") if isinstance(data, dict) else None
    if not isinstance(cmi, dict):
        raise Refused("bad_commit", 'Send the run-time data as {"cmi": {...}}.', 400)
    if len(json.dumps(cmi)) > MAX_RUNTIME_BYTES:
        raise Refused("too_large", "The run-time data is larger than the LMS keeps.", 400)
    with transaction.atomic():
        attempt = (
            PackageAttempt.objects.select_for_update().select_related("package__item").get(pk=attempt.pk)
        )
        before = state_of(attempt)
        found = read_cmi(package.standard, cmi)
        attempt.runtime = {
            **attempt.runtime,
            sco_id: {
                "cmi": cmi,
                "completion": found["completion"],
                "success": found["success"],
                "score": _s(found["score"]),
                "exit": found["exit"],
            },
        }
        _sum_up(attempt)
        finish_changes(request, attempt, before)
    return attempt


# ---------------------------------------------------------------------------------------------------------
# Coursework


def best_result(package: ContentPackage, person, attempts=None) -> tuple[Decimal | None, str]:
    """(fraction, state) for coursework: the best scored attempt; a completed one with no score is 1."""
    best, finished = None, False
    for attempt in attempts_of(package, person) if attempts is None else attempts:
        if attempt.score is not None:
            best = attempt.score if best is None else max(best, attempt.score)
        if attempt.completion == PackageAttempt.Completion.COMPLETED:
            finished = True
    if best is not None:
        return Decimal(best), "graded"
    if finished:
        return Decimal(1), "graded"
    return None, "not_due"


def coursework_packages(site, person) -> list[tuple]:
    """(package, fraction, state) for each package that counts: published and weighted."""
    from assessments import preload

    loaded = preload.current(site)
    if loaded is not None and loaded.packages is not None:  # the class read at once (item 7.08)
        return [
            (package, *best_result(package, person, loaded.package_attempts.get((package.id, person.pk), [])))
            for package in loaded.packages
        ]
    packages = ContentPackage.objects.filter(
        item__module__site=site, item__is_published=True, weight__gt=0
    ).select_related("item")
    return [(package, *best_result(package, person)) for package in packages]


def coursework_items(site, student, *, released_only: bool = False, now=None) -> list[tuple]:
    """As practicals.services.coursework_items: (weight, fraction) for each package that counts. Results
    of packaged content are never held back, so released_only changes nothing."""
    return [(package.weight, fraction) for package, fraction, _ in coursework_packages(site, student)]
