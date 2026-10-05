"""Self-paced completion (item 5.03): a staff-development course completes itself when its rules are met.

The rules are set on the catalogue entry: every published item completed, every published quiz with a pass
mark passed at that mark, every published assignment marked (and the mark released) at least a percentage.
Every rule switched on must hold. The check runs when a person completes an item, finishes or is marked on a
quiz, or is given a mark (staffdev.signals), and again each night for everyone (staffdev.tasks), so nothing
is missed.

A completion that expires opens for renewal RENEWAL_WINDOW_DAYS before it does: the person's progress through
the items is cleared, and only work done since the window opened counts towards the renewal.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from audit.services import record, snapshot
from courses.models import Completion, ContentItem, CourseSite, ItemCompletion, Membership
from notifications.services import notify
from staffdev.models import CatalogueEntry


@dataclass
class Rule:
    code: str
    label: str
    met: bool
    done: int
    total: int


@dataclass
class Progress:
    rules: list[Rule] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return bool(self.rules) and all(rule.met for rule in self.rules)


def add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    for last in (31, 30, 29, 28):
        try:
            return day.replace(year=year, month=month, day=min(day.day, last))
        except ValueError:
            continue
    raise ValueError(day)  # pragma: no cover


def _items(site: CourseSite, person, since: datetime | None) -> Rule:
    items = ContentItem.objects.filter(module__site=site, is_published=True, under_review=False)
    done = ItemCompletion.objects.filter(person=person, item__in=items)
    if since is not None:
        done = done.filter(completed_at__gte=since)
    total, count = items.count(), done.count()
    return Rule("all_items", "Every item completed", count >= total, count, total)


def _passed(quiz, person, since: datetime | None) -> bool:
    from quizzes.models import Attempt
    from quizzes.services import quiz_grade, student_sees_marks

    if since is None:
        grade = quiz_grade(quiz, person, released_only=True)
        return grade.state == "graded" and grade.fraction * 100 >= quiz.pass_mark
    attempts = Attempt.objects.filter(
        quiz=quiz, student=person, state=Attempt.State.FINISHED, submitted_at__gte=since, needs_grading=False
    )
    return any(
        a.max_score and a.score is not None and student_sees_marks(a) and a.percent >= quiz.pass_mark
        for a in attempts
    )


def _quizzes(site: CourseSite, person, since: datetime | None) -> Rule:
    from quizzes.models import Quiz

    quizzes = Quiz.objects.filter(site=site, is_published=True, is_practice=False, pass_mark__isnull=False)
    passed = sum(1 for quiz in quizzes if _passed(quiz, person, since))
    total = len(quizzes)
    return Rule("quizzes_passed", "Every quiz passed at its pass mark", passed >= total, passed, total)


def _assignments(site: CourseSite, person, percent, since: datetime | None) -> Rule:
    from assessments.models import Assignment, Mark

    assignments = Assignment.objects.filter(site=site, is_published=True)
    marks = Mark.objects.filter(
        submission__assignment__in=assignments, submission__student=person, is_released=True
    ).select_related("submission__assignment")
    if since is not None:
        marks = marks.filter(submission__submitted_at__gte=since)
    good = {
        m.submission.assignment_id
        for m in marks
        if m.mark * 100 >= percent * m.submission.assignment.max_mark
    }
    total = assignments.count()
    label = f"Every assignment marked at least {percent.normalize():f}%"
    return Rule("assignments_marked", label, len(good) >= total, len(good), total)


def progress(entry: CatalogueEntry, person, *, since: datetime | None = None) -> Progress:
    site = entry.site
    rules = []
    if entry.rule_all_items:
        rules.append(_items(site, person, since))
    if entry.rule_quizzes_passed:
        rules.append(_quizzes(site, person, since))
    if entry.rule_assignment_percent is not None:
        rules.append(_assignments(site, person, entry.rule_assignment_percent, since))
    return Progress(rules)


def renewal_opens(completion: Completion) -> date | None:
    if completion.expires_on is None:
        return None
    return completion.expires_on - timedelta(days=settings.RENEWAL_WINDOW_DAYS)


def renewal_open(completion: Completion, today: date | None = None) -> bool:
    opens = renewal_opens(completion)
    return opens is not None and (today or timezone.localdate()) >= opens


def _since(completion: Completion | None) -> datetime | None:
    if completion is None:
        return None
    opens = renewal_opens(completion)
    return timezone.make_aware(datetime.combine(opens, time.min)) if opens else None


def validity_months(entry: CatalogueEntry, person) -> int | None:
    """How long a completion lasts: the shortest renewal any requirement on the person sets, else the
    catalogue's own."""
    from staffdev.required import requirements_for

    months = [r.renewal_months for r in requirements_for(person, site=entry.site) if r.renewal_months]
    if months:
        return min(months)
    return entry.validity_months


def evaluate(entry: CatalogueEntry, person, *, request=None) -> Completion | None:
    """Record the completion when the rules are met. Returns it when recorded now, None otherwise."""
    if not entry.has_rules or not person.is_active:
        return None
    existing = Completion.objects.filter(site=entry.site, person=person).first()
    if existing is not None and not renewal_open(existing):
        return None
    if not progress(entry, person, since=_since(existing)).complete:
        return None
    return record_completion(entry, person, request=request, how=Completion.How.RULES)


def record_completion(entry: CatalogueEntry, person, *, request=None, how: str, on: date | None = None):
    """Record (or renew) the completion, issue the certificate, tell the person, and report it to the HRMS
    at once (item 5.06); the nightly push sends it if that cannot."""
    from staffdev import paths, required

    today = on or timezone.localdate()
    months = validity_months(entry, person)
    expires = add_months(today, months) if months else None
    with transaction.atomic():
        completion = Completion.objects.select_for_update().filter(site=entry.site, person=person).first()
        before = snapshot(completion) if completion is not None else None
        if completion is None:
            completion = Completion(site=entry.site, person=person)
            ref = ""
        else:
            # A renewal is a new entry in the HRMS training record, under a reference of its own.
            ref = f"lms:{entry.site.code}:{person.external_id}:{today:%Y%m%d}"
        completion.completed_on, completion.expires_on, completion.how = today, expires, how
        completion.external_ref, completion.reported_at = ref, None
        completion.save()
        record(
            request,
            "completed" if before is None else "renewed",
            completion,
            before=before,
            after=snapshot(completion),
        )
        required.mark_done(person, entry.site, today)
        if entry.issue_certificate:
            from certificates.services import issue

            issue(request, completion, template_code=entry.certificate_template)
        transaction.on_commit(lambda: _report(completion.pk))
    if person.user is not None and person.user.is_active:
        notify(
            [person.user],
            title=f"You have completed {entry.site.title}",
            body="Well done. It is sent to your training record in the HRMS."
            + (f" It is valid until {expires:%d/%m/%Y}." if expires else ""),
            link="/staff-development",
            dedupe_key=f"completed:{completion.pk}:{today:%Y%m%d}",
        )
    paths.unlock_next(person, entry.site, request=request)
    return completion


def _report(completion_id: int) -> None:
    from integration.tasks import report_completion

    if settings.HRMS_API_URL and settings.HRMS_API_KEY:
        report_completion.defer(completion_id=completion_id)


def open_renewals(today: date | None = None) -> int:
    """Clear the item progress of everyone whose completion has entered its renewal window, once, so the
    course can be taken again. Returns how many were opened."""
    today = today or timezone.localdate()
    opened = 0
    window = timedelta(days=settings.RENEWAL_WINDOW_DAYS)
    due = Completion.objects.filter(
        expires_on__isnull=False, expires_on__lte=today + window, site__catalogue__isnull=False
    ).select_related("site", "person")
    for completion in due:
        since = _since(completion)
        stale = ItemCompletion.objects.filter(
            person=completion.person, item__module__site=completion.site, completed_at__lt=since
        )
        if not stale.exists():
            continue
        with transaction.atomic():
            cleared = stale.delete()[0]
            record(
                None,
                "renewal_opened",
                completion,
                after={"items_cleared": cleared, "expires_on": completion.expires_on.isoformat()},
                reason="The completion is due for renewal",
            )
        opened += 1
    return opened


def sweep(today: date | None = None) -> dict:
    """The nightly check of everyone on a staff-development course with completion rules."""
    counts = {"renewals_opened": open_renewals(today), "completed": 0}
    for entry in CatalogueEntry.objects.select_related("site"):
        if not entry.has_rules:
            continue
        learners = Membership.objects.filter(
            site=entry.site, role=Membership.SiteRole.STUDENT, is_active=True, person__is_active=True
        ).select_related("person", "person__user")
        for membership in learners:
            if evaluate(entry, membership.person) is not None:
                counts["completed"] += 1
    return counts
