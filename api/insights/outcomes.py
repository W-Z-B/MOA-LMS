"""Learning outcomes (item 3.11): which outcomes a site has, and each student's standing on each.

A site's outcomes are its course's outcomes in the SRMS course outline, synced nightly (insights.srms).
While the SRMS holds none for the course, teaching staff may add the site's own. Teaching staff link each
outcome to evidence on the site: assignments, quiz questions and rubric criteria.

A student's standing on an outcome is the mean of their results on its evidence, each as a percentage:
an assignment's mark (before any late penalty: the outcome is about what was shown, not when), the latest
marked answer to a linked question, and the points given on a linked rubric criterion. It is "met" at
OUTCOME_MET_PERCENT or above. It is a guide for the lecturer, worked out from marks people gave; it decides
nothing, and the student sees it only from released marks.
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings

from assessments.models import Submission
from insights.models import Outcome, OutcomeLink, SiteProfile
from quizzes.models import Attempt, AttemptAnswer
from rubrics.models import Rubric

ONE_PLACE = Decimal("0.1")
MET, NOT_YET, NO_EVIDENCE = "met", "not_yet", "no_evidence"


def course_code_of(site) -> str:
    profile = SiteProfile.objects.filter(site=site).first()
    return profile.course_code if profile else ""


def srms_outcomes(site):
    code = course_code_of(site)
    if not code:
        return Outcome.objects.none()
    return Outcome.objects.filter(source=Outcome.Source.SRMS, course_code=code, is_active=True)


def site_outcomes(site) -> list[Outcome]:
    """The course's SRMS outcomes; the site's own only while the SRMS has none."""
    srms = list(srms_outcomes(site))
    if srms:
        return srms
    return list(Outcome.objects.filter(source=Outcome.Source.LOCAL, site=site, is_active=True))


def may_add_local(site) -> bool:
    return not srms_outcomes(site).exists()


def criterion_max(criterion) -> Decimal | None:
    if criterion.rubric.kind == Rubric.Kind.GUIDE:
        return criterion.max_points
    if criterion.rubric.kind == Rubric.Kind.SCORED:
        points = [level.points for level in criterion.levels.all()]
        return max(points) if points and max(points) > 0 else None
    return None  # a descriptive rubric gives no points to measure against


@dataclass
class Evidence:
    """One result counted towards an outcome, as a fraction of what it could be."""

    kind: str
    title: str
    fraction: Decimal


@dataclass
class _SiteMarks:
    """Each student's marks on the site, read once for every outcome."""

    submissions: dict = field(default_factory=dict)  # (assignment id, student id) -> Submission
    answers: dict = field(default_factory=dict)  # (question id, student id) -> AttemptAnswer, the latest


def _site_marks(site, student_ids, released_only: bool) -> _SiteMarks:
    from quizzes.services import student_sees_marks

    marks = _SiteMarks()
    submissions = Submission.objects.filter(
        assignment__site=site, student_id__in=student_ids, mark__isnull=False
    ).select_related("mark", "assignment")
    for submission in submissions:
        if released_only and not submission.mark.is_released:
            continue
        if not released_only and submission.assignment.names_hidden:
            continue  # anonymous marking: no result is put beside a name until release (item 3.16)
        marks.submissions[(submission.assignment_id, submission.student_id)] = submission
    answers = (
        AttemptAnswer.objects.filter(
            attempt__quiz__site=site,
            attempt__student_id__in=student_ids,
            attempt__state=Attempt.State.FINISHED,
            awarded__isnull=False,
            max_mark__gt=0,
        )
        .select_related("attempt", "attempt__quiz", "version")
        .order_by("attempt__submitted_at", "attempt_id")
    )
    for answer in answers:
        if released_only and not student_sees_marks(answer.attempt):
            continue
        marks.answers[(answer.version.question_id, answer.attempt.student_id)] = answer  # the latest wins
    return marks


def _evidence(link: OutcomeLink, student_id: int, marks: _SiteMarks) -> list[Evidence]:
    if link.assignment_id:
        submission = marks.submissions.get((link.assignment_id, student_id))
        if submission is None:
            return []
        fraction = submission.mark.mark / submission.assignment.max_mark
        return [Evidence("assignment", submission.assignment.title, min(fraction, Decimal(1)))]
    if link.question_id:
        answer = marks.answers.get((link.question_id, student_id))
        if answer is None:
            return []
        title = f"{answer.attempt.quiz.title}, question {answer.position}"
        return [Evidence("question", title, min(answer.awarded / answer.max_mark, Decimal(1)))]
    criterion = link.criterion
    possible = criterion_max(criterion)
    if not possible:
        return []
    found = []
    for (_, sid), submission in marks.submissions.items():
        if sid != student_id or submission.assignment.rubric_id != criterion.rubric_id:
            continue
        for row in submission.mark.rubric_scores or []:
            if row.get("criterion") == criterion.id and row.get("points") not in (None, ""):
                title = f"{submission.assignment.title}: {criterion.title}"
                found.append(
                    Evidence("criterion", title, min(Decimal(str(row["points"])) / possible, Decimal(1)))
                )
    return found


def _standing(evidence: list[Evidence]) -> dict:
    if not evidence:
        return {"standing": NO_EVIDENCE, "percent": None, "evidence": []}
    mean = sum((e.fraction for e in evidence), Decimal(0)) / len(evidence) * 100
    value = mean.quantize(ONE_PLACE, rounding=ROUND_HALF_UP)
    return {
        "standing": MET if value >= settings.OUTCOME_MET_PERCENT else NOT_YET,
        "percent": str(value),
        "evidence": [
            {
                "kind": e.kind,
                "title": e.title,
                "percent": str((e.fraction * 100).quantize(ONE_PLACE, rounding=ROUND_HALF_UP)),
            }
            for e in evidence
        ],
    }


def standings(site, students, *, released_only: bool = False) -> dict:
    """{"outcomes": [...], "students": [{person_id, outcomes: {outcome id: standing}}]}."""
    outcomes = site_outcomes(site)
    links = list(
        OutcomeLink.objects.filter(site=site, outcome__in=outcomes).select_related(
            "criterion__rubric", "assignment", "question"
        )
    )
    by_outcome: dict[int, list[OutcomeLink]] = {}
    for link in links:
        by_outcome.setdefault(link.outcome_id, []).append(link)
    marks = _site_marks(site, [s.id for s in students], released_only)
    rows = []
    for student in students:
        cells = {}
        for outcome in outcomes:
            evidence = [
                e for link in by_outcome.get(outcome.id, []) for e in _evidence(link, student.id, marks)
            ]
            cells[str(outcome.id)] = _standing(evidence)
        rows.append(
            {
                "person_id": student.id,
                "student_no": student.external_id,
                "name": student.full_name,
                "outcomes": cells,
            }
        )
    return {
        "met_percent": settings.OUTCOME_MET_PERCENT,
        "outcomes": [
            {
                "id": o.id,
                "code": o.code,
                "text": o.text,
                "source": o.source,
                "links": len(by_outcome.get(o.id, [])),
            }
            for o in outcomes
        ],
        "students": rows,
    }
