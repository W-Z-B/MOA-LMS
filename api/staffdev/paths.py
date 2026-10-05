"""Learning paths (item 5.04): courses in order for a role. A person on a path joins its first course; each
later course opens to them once the one before it is complete, and they are put forward for it then (joined
at once, or asked for, as the course's catalogue entry says)."""

from django.db import transaction
from django.utils import timezone

from approvals.delegation import users_of
from audit.services import record, snapshot
from courses.models import Completion, Membership
from notifications.services import notify
from staffdev.models import CatalogueEntry, LearningPath, PathEnrolment, PathStep


def completed_sites(person) -> set[int]:
    """Sites the person has completed and whose completion has not run out."""
    today = timezone.localdate()
    return {
        c.site_id
        for c in Completion.objects.filter(person=person)
        if c.expires_on is None or c.expires_on >= today
    }


def steps_of(path: LearningPath) -> list[PathStep]:
    return list(path.steps.select_related("site").order_by("position"))


def locked_by(person, site) -> str | None:
    """Why the person cannot yet join the site: a path they follow puts an unfinished course before it."""
    done = completed_sites(person)
    for joined in PathEnrolment.objects.filter(person=person, path__steps__site=site).select_related("path"):
        for step in steps_of(joined.path):
            if step.site_id == site.id:
                break
            if step.site_id not in done:
                return (
                    f"Complete {step.site.title} first: it comes before this course on the path "
                    f"{joined.path.title}."
                )
    return None


def progress(path: LearningPath, person) -> dict:
    """Each step: done, open (the next to take) or locked; and how far through the path the person is."""
    done = completed_sites(person)
    enrolled = set(Membership.objects.filter(person=person, is_active=True).values_list("site_id", flat=True))
    steps, reached_open = [], False
    for step in steps_of(path):
        if step.site_id in done:
            state = "done"
        elif not reached_open:
            state, reached_open = "open", True
        else:
            state = "locked"
        steps.append(
            {
                "position": step.position,
                "site": step.site_id,
                "title": step.site.title,
                "state": state,
                "enrolled": step.site_id in enrolled,
            }
        )
    finished = sum(1 for s in steps if s["state"] == "done")
    return {
        "steps": steps,
        "done": finished,
        "total": len(steps),
        "complete": bool(steps) and finished == len(steps),
    }


def _put_forward(request, person, step: PathStep) -> str | None:
    """Join the step's course, or ask to, as its catalogue entry allows. The outcome, or None when refused."""
    from staffdev.enrolment import Refused, join

    entry = CatalogueEntry.objects.filter(site=step.site).first()
    if entry is None:
        return None
    try:
        return join(request, entry, person, reason=f"Next course on the path {step.path.title}")["outcome"]
    except Refused:
        return None


def join_path(request, path: LearningPath, person) -> PathEnrolment:
    with transaction.atomic():
        joined, created = PathEnrolment.objects.get_or_create(path=path, person=person)
        if created:
            record(request, "create", joined, after=snapshot(joined))
    done = completed_sites(person)
    first = next((s for s in steps_of(path) if s.site_id not in done), None)
    if first is not None:
        _put_forward(request, person, first)
    return joined


def unlock_next(person, site, *, request=None) -> list[str]:
    """After a course is completed, put the person forward for the next course on each path they follow."""
    opened = []
    done = completed_sites(person)
    for joined in PathEnrolment.objects.filter(person=person, path__steps__site=site).select_related("path"):
        following = [s for s in steps_of(joined.path) if s.site_id not in done]
        if not following:
            continue
        step = following[0]
        outcome = _put_forward(request, person, step)
        opened.append(step.site.title)
        notify(
            users_of([person]),
            title=f"Next on {joined.path.title}: {step.site.title}",
            body="You have joined it." if outcome == "enrolled" else "It is now open to you.",
            link="/staff-development",
            dedupe_key=f"path:{joined.pk}:{step.site_id}",
        )
    return opened
