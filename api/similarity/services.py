"""Running the similarity check for one hand-in, and the report teaching staff read (item 3.20).

check(attempt) reads the hand-in, replaces the submission's fingerprints, finds the GSA submissions that
share the most with it, compares each in full and keeps the matches for both sides. It runs in the
background after each hand-in (similarity.tasks), so handing in never waits for it.
"""

import logging
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from similarity import engine, extract
from similarity.models import Fingerprint, SimilarityDocument, SimilarityMatch

log = logging.getLogger(__name__)
TWO_PLACES = Decimal("0.01")

STATEMENT = (
    "Overlap is evidence for a person to judge, not a verdict. Text can match for good reasons: a shared "
    "source, set phrases of the subject, group work the course allows, or the student's own earlier work. "
    "Only GSA submissions are compared, on GSA's own server; copying from the web or from elsewhere is not "
    "found. Passages in quotation marks and the assignment's own instructions are left out. Nothing here "
    "says whether a person or a tool wrote the work: GSA uses no detector of AI writing. Talk to the "
    "student before deciding anything; they can answer."
)


def _percent(part: int, whole: int) -> Decimal:
    if not whole:
        return Decimal(0)
    return (Decimal(part) * 100 / Decimal(whole)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def enabled() -> bool:
    return bool(getattr(settings, "SIMILARITY_CHECKS", True))


def _passages(comparison, a_words, b_words, *, swap=False) -> list[dict]:
    rows = []
    for passage in comparison.passages[: engine.MAX_PASSAGES]:
        mine, theirs = (passage["b"], passage["a"]) if swap else (passage["a"], passage["b"])
        rows.append(
            {
                "mine": engine.passage_text(b_words if swap else a_words, mine),
                "theirs": engine.passage_text(a_words if swap else b_words, theirs),
                "words": mine[1] - mine[0],
            }
        )
    if swap:
        rows.sort(key=lambda r: -r["words"])
    return rows


def _refresh_overall(document: SimilarityDocument) -> None:
    ranges = [r for m in document.matches.all() for r in m.ranges]
    document.overall_percent = _percent(engine.covered(ranges), document.word_count)
    document.save(update_fields=["overall_percent", "updated_at"])


def _candidates(document: SimilarityDocument, kept: list[tuple[int, int]]):
    submission = document.submission
    others = (
        Fingerprint.objects.filter(hash__in={h for h, _ in kept})
        .exclude(document=document)
        .exclude(document__status=SimilarityDocument.Status.WAITING)
    )
    if submission.group_id:
        # Members of one group hand in one piece of work: it is never compared with itself.
        others = others.exclude(
            Q(document__submission__assignment_id=submission.assignment_id)
            & Q(document__submission__group_id=submission.group_id)
        )
    return (
        others.values("document")
        .annotate(shared=Count("hash", distinct=True))
        .filter(shared__gte=engine.MIN_SHARED_FINGERPRINTS)
        .order_by("-shared", "document")[: engine.MAX_CANDIDATES]
    )


def check(attempt) -> SimilarityDocument | None:
    """Check one hand-in against every other GSA submission. None when the check is switched off."""
    if not enabled():
        return None
    submission = attempt.submission
    assignment = submission.assignment
    read = extract.attempt_text(attempt)
    words = engine.words_of(read.text)
    excluded = engine.instruction_hashes(assignment.instructions)
    with transaction.atomic():
        document, _ = SimilarityDocument.objects.select_for_update().update_or_create(
            submission=submission,
            defaults={
                "attempt_number": attempt.number,
                "words": " ".join(words),
                "word_count": len(words),
                "status": SimilarityDocument.Status.WAITING,
                "notes": read.notes,
                "overall_percent": None,
            },
        )
        document.fingerprints.all().delete()
        others_before = list(
            SimilarityMatch.objects.filter(other=document).values_list("document", flat=True)
        )
        document.matches.all().delete()
        SimilarityMatch.objects.filter(other=document).delete()
        for earlier in SimilarityDocument.objects.filter(pk__in=others_before):
            _refresh_overall(earlier)
        hashes = engine.shingles(words)
        kept = [(h, p) for h, p in engine.winnow(hashes) if h not in excluded]
        if not kept:
            document.status = (
                SimilarityDocument.Status.NO_TEXT if not words else SimilarityDocument.Status.DONE
            )
            document.overall_percent = Decimal(0) if words else None
            document.checked_at = timezone.now()
            document.save()
            return document
        Fingerprint.objects.bulk_create(
            [Fingerprint(document=document, hash=h, position=p) for h, p in kept], batch_size=2000
        )
        for row in _candidates(document, kept):
            other = SimilarityDocument.objects.select_related("submission__assignment").get(
                pk=row["document"]
            )
            other_words = other.words.split(" ") if other.words else []
            excluded_both = excluded | engine.instruction_hashes(other.submission.assignment.instructions)
            found = engine.compare(words, other_words, excluded_both)
            if not found.passages:
                continue
            SimilarityMatch.objects.create(
                document=document,
                other=other,
                shared_words=found.shared_a,
                percent=_percent(found.shared_a, len(words)),
                ranges=found.ranges_a,
                passages=_passages(found, words, other_words),
            )
            SimilarityMatch.objects.update_or_create(
                document=other,
                other=document,
                defaults={
                    "shared_words": found.shared_b,
                    "percent": _percent(found.shared_b, len(other_words)),
                    "ranges": found.ranges_b,
                    "passages": _passages(found, words, other_words, swap=True),
                },
            )
            _refresh_overall(other)
        document.status = SimilarityDocument.Status.DONE
        document.checked_at = timezone.now()
        document.save()
        _refresh_overall(document)
    return document


def check_safely(attempt) -> SimilarityDocument | None:
    """For the background job: a failure is noted on the report, never lost and never raised."""
    try:
        return check(attempt)
    except Exception:  # noqa: BLE001 - the report says the check failed; the lecturer can run it again
        log.exception("similarity check failed for attempt %s", attempt.pk)
        SimilarityDocument.objects.update_or_create(
            submission=attempt.submission,
            defaults={"attempt_number": attempt.number, "status": SimilarityDocument.Status.FAILED},
        )
        return None


# ---------------------------------------------------------------------------------------------------------
# The report


def describe_other(user, other: SimilarityDocument) -> dict:
    """Who the other submission is, said only to staff who teach on its site as well; otherwise only that it
    is another GSA submission and its year. An anonymous assignment keeps its pseudonym until release."""
    from assessments import rules
    from courses.access import can_teach

    submission = other.submission
    assignment = submission.assignment
    year = submission.submitted_at.year
    if not can_teach(user, assignment.site):
        return {
            "known": False,
            "label": f"Another GSA submission, {year}",
            "year": year,
            "site": None,
            "assignment": None,
            "student": None,
            "submission": None,
        }
    student = (
        rules.pseudonym(assignment, submission.student)
        if assignment.names_hidden
        else f"{submission.student.full_name} ({submission.student.external_id})"
    )
    return {
        "known": True,
        "label": f"{student}, {assignment.title}, {assignment.site.code}",
        "year": year,
        "site": assignment.site.code,
        "assignment": assignment.title,
        "student": student,
        "submission": submission.id,
    }


def report(user, submission) -> dict:
    document = getattr(submission, "similarity", None)
    if document is None:
        return {
            "status": "not_checked",
            "statement": STATEMENT,
            "overall_percent": None,
            "word_count": 0,
            "attempt_number": None,
            "checked_at": None,
            "notes": [],
            "matches": [],
        }
    matches = document.matches.select_related(
        "other__submission__assignment__site", "other__submission__student"
    ).order_by("-percent", "id")
    return {
        "status": document.status,
        "statement": STATEMENT,
        "overall_percent": str(document.overall_percent) if document.overall_percent is not None else None,
        "word_count": document.word_count,
        "attempt_number": document.attempt_number,
        "checked_at": document.checked_at,
        "notes": document.notes,
        "matches": [
            {
                "id": m.id,
                "percent": str(m.percent),
                "shared_words": m.shared_words,
                "other": describe_other(user, m.other),
                "passages": m.passages,
            }
            for m in matches
        ],
    }
