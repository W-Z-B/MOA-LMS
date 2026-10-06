"""Required training (item 5.05): courses staff must take by campus, unit or post, with due dates, reminders,
renewal before a completion expires, and the report of who is overdue.

Decision D13 (ADR 0019) puts the requirement in the HRMS, which knows each person's post. With
HRMS_TRAINING_REQUIREMENTS_SYNC on, the HRMS's list is read each night before the daily run here
(integration.hrms.sync_training_requirements, scope training:read) and kept as RequiredTraining rows whose
source is the HRMS; those are read-only in the LMS. Course administrators keep their own requirements beside
them (source lms), and do so for all of them while the setting is off. Either way, each requirement is matched
against the post, unit and campus the HRMS staff directory sends (integration.hrms.sync_staff).
"""

from datetime import date, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from approvals.delegation import users_of
from audit.services import record, snapshot
from courses.models import Completion
from notifications.services import notify
from people.models import PersonRef
from staffdev.models import RequiredTraining, TrainingAssignment


def matches(requirement: RequiredTraining, person: PersonRef) -> bool:
    if person.kind != PersonRef.Kind.STAFF or not person.is_active:
        return False
    if requirement.campus_code and requirement.campus_code != person.campus_code:
        return False
    if requirement.unit_code and requirement.unit_code != person.unit_code:
        return False
    return not requirement.post_title or requirement.post_title.casefold() == person.post_title.casefold()


def staff_for(requirement: RequiredTraining):
    qs = PersonRef.objects.filter(kind=PersonRef.Kind.STAFF, is_active=True)
    if requirement.campus_code:
        qs = qs.filter(campus_code=requirement.campus_code)
    if requirement.unit_code:
        qs = qs.filter(unit_code=requirement.unit_code)
    if requirement.post_title:
        qs = qs.filter(post_title__iexact=requirement.post_title)
    return qs.select_related("user")


def requirements_for(person: PersonRef, *, site=None) -> list[RequiredTraining]:
    qs = RequiredTraining.objects.filter(is_active=True)
    if site is not None:
        qs = qs.filter(site=site)
    return [r for r in qs if matches(r, person)]


def _current_completion(person, site, today: date) -> Completion | None:
    from staffdev.completion import renewal_open

    done = Completion.objects.filter(person=person, site=site).first()
    if done is None or renewal_open(done, today):
        return None
    return done


def assign(requirement: RequiredTraining, *, request=None, today: date | None = None) -> int:
    """Assign the course to every member of staff the requirement covers who has no assignment yet, put them
    on the course, and tell them. Returns how many were assigned."""
    from staffdev.enrolment import add_learner

    today = today or timezone.localdate()
    if not requirement.is_active:
        return 0
    count = 0
    have = set(requirement.assignments.values_list("person_id", flat=True))
    for person in staff_for(requirement).exclude(pk__in=have):
        done = _current_completion(person, requirement.site, today)
        due = today + timedelta(days=requirement.due_days)
        with transaction.atomic():
            assignment = TrainingAssignment.objects.create(
                requirement=requirement,
                person=person,
                assigned_on=today,
                due_on=due,
                completed_on=done.completed_on if done else None,
            )
            record(request, "training_assigned", assignment, after=snapshot(assignment))
            if done is None:
                add_learner(request, requirement.site, person, why="Required training")
        count += 1
        if done is None:
            notify(
                users_of([person]),
                title=f"Required training: {requirement.site.title}",
                body=f"You are asked to complete it by {due:%d/%m/%Y}. It is under My courses.",
                link=f"/sites/{requirement.site_id}",
                dedupe_key=f"required:assigned:{assignment.pk}",
            )
    return count


def mark_done(person: PersonRef, site, day: date) -> int:
    """The course is complete: every open assignment of it to the person is done."""
    return TrainingAssignment.objects.filter(
        person=person, requirement__site=site, completed_on__isnull=True
    ).update(completed_on=day, updated_at=timezone.now())


def reopen_renewals(today: date) -> int:
    """Open each done assignment again whose completion has entered its renewal window, due on the day the
    completion expires, and put the person back on the course."""
    from staffdev.completion import renewal_open
    from staffdev.enrolment import add_learner

    count = 0
    done = TrainingAssignment.objects.filter(
        completed_on__isnull=False, requirement__is_active=True
    ).select_related("requirement__site", "person", "person__user")
    for assignment in done:
        completion = Completion.objects.filter(
            person=assignment.person, site=assignment.requirement.site
        ).first()
        if completion is None or not renewal_open(completion, today):
            continue
        with transaction.atomic():
            before = snapshot(assignment)
            assignment.completed_on = None
            assignment.due_on = completion.expires_on
            assignment.save(update_fields=["completed_on", "due_on", "updated_at"])
            record(None, "training_renewal_due", assignment, before=before, after=snapshot(assignment))
            add_learner(None, assignment.requirement.site, assignment.person, why="Required training renewal")
        notify(
            users_of([assignment.person]),
            title=f"Time to renew: {assignment.requirement.site.title}",
            body=f"Your completion runs out on {completion.expires_on:%d/%m/%Y}. Take the course again.",
            link=f"/sites/{assignment.requirement.site_id}",
            dedupe_key=f"required:renew:{assignment.pk}:{completion.expires_on:%Y%m%d}",
        )
        count += 1
    return count


def remind(today: date) -> dict:
    """Remind those due within REQUIRED_TRAINING_REMIND_DAYS (once per due date) and those overdue (once a
    week)."""
    soon = today + timedelta(days=settings.REQUIRED_TRAINING_REMIND_DAYS)
    counts = {"due_soon": 0, "overdue": 0}
    open_ = TrainingAssignment.objects.filter(
        completed_on__isnull=True, requirement__is_active=True, person__is_active=True, due_on__lte=soon
    ).select_related("requirement__site", "person", "person__user")
    week = today.isocalendar()
    for assignment in open_:
        title = assignment.requirement.site.title
        if assignment.due_on >= today:
            sent = notify(
                users_of([assignment.person]),
                title=f"Required training due by {assignment.due_on:%d/%m/%Y}: {title}",
                body="Complete it by then. It is under My courses.",
                link=f"/sites/{assignment.requirement.site_id}",
                dedupe_key=f"required:soon:{assignment.pk}:{assignment.due_on:%Y%m%d}",
            )
            counts["due_soon"] += len(sent)
        else:
            sent = notify(
                users_of([assignment.person]),
                title=f"Required training overdue: {title}",
                body=f"It was due by {assignment.due_on:%d/%m/%Y}. Complete it as soon as you can.",
                link=f"/sites/{assignment.requirement.site_id}",
                kind="alert",
                dedupe_key=f"required:overdue:{assignment.pk}:{week.year}-{week.week}",
            )
            counts["overdue"] += len(sent)
    return counts


def daily(today: date | None = None) -> dict:
    """The daily run: assign new staff, open renewals, and remind."""
    today = today or timezone.localdate()
    assigned = sum(assign(r, today=today) for r in RequiredTraining.objects.filter(is_active=True))
    return {"assigned": assigned, "renewals": reopen_renewals(today), **remind(today)}


def overdue(today: date | None = None, *, campus_code: str = ""):
    """Assignments past their due date and not done: the overdue report."""
    today = today or timezone.localdate()
    qs = TrainingAssignment.objects.filter(
        completed_on__isnull=True, due_on__lt=today, requirement__is_active=True, person__is_active=True
    ).select_related("requirement__site", "person")
    if campus_code:
        qs = qs.filter(person__campus_code=campus_code)
    return qs.order_by("due_on", "person__last_name")
