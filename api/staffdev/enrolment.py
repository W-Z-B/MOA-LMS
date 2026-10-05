"""Joining a staff-development course (item 5.02): at once where the course is open, through the approvals
engine where it needs approval, never where it is closed.

Approval goes to the person's supervisor as the HRMS records them (PersonRef.supervisor). The HRMS staff
directory does not yet say who supervises whom, so until it does every request goes to the course
administrators, who decide as the engine's stand-in. A decision is never taken by the person who asked.
"""

from django.db import transaction
from django.utils import timezone

from approvals.delegation import delegates_of, users_of
from approvals.engine import APPROVER, OWNER, STAND_IN, Transition, WorkflowDefinition, WorkflowError
from audit.services import record, snapshot
from courses.models import Completion, CourseSite, Membership
from iam.models import Role
from notifications.services import notify, users_with_role
from people.models import PersonRef
from staffdev.models import CatalogueEntry, EnrolmentRequest


class Refused(Exception):
    def __init__(self, code: str, detail: str, status: int = 409):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status


def places_left(entry: CatalogueEntry) -> int | None:
    if entry.capacity is None:
        return None
    taken = Membership.objects.filter(
        site=entry.site, role=Membership.SiteRole.STUDENT, is_active=True
    ).count()
    return max(entry.capacity - taken, 0)


def add_learner(request, site: CourseSite, person: PersonRef, *, why: str) -> Membership:
    """Put the person on the course as a learner, or back on it, and say so in the audit log."""
    membership = Membership.objects.filter(site=site, person=person).first()
    before = snapshot(membership) if membership is not None else None
    if membership is None:
        membership = Membership.objects.create(site=site, person=person, role=Membership.SiteRole.STUDENT)
    elif not membership.is_active:
        membership.is_active = True
        membership.save(update_fields=["is_active", "updated_at"])
    else:
        return membership
    record(request, "enrolled", membership, before=before, after=snapshot(membership), reason=why)
    return membership


def _full(instance, request) -> None:
    """Guard: no approval once the course is full."""
    entry = instance.site.catalogue
    left = places_left(entry)
    if left is not None and left <= 0:
        raise WorkflowError(
            "The course is full. Ask the course administrator about another run.", code="full"
        )


def _approved(instance, request) -> None:
    add_learner(request, instance.site, instance.person, why="Enrolment approved")
    notify(
        users_of([instance.person]),
        title=f"You can start {instance.site.title}",
        body="Your request to join was approved. The course is under My courses.",
        link=f"/sites/{instance.site_id}",
        dedupe_key=f"enrolment:approved:{instance.pk}",
    )


def _rejected(instance, request) -> None:
    notify(
        users_of([instance.person]),
        title=f"Your request to join {instance.site.title} was not approved",
        body=instance.decision_comment,
        link="/staff-development",
        dedupe_key=f"enrolment:rejected:{instance.pk}",
    )


WORKFLOW = WorkflowDefinition(
    key="staffdev.enrolment",
    transitions=(
        Transition(
            "approve",
            (EnrolmentRequest.State.SUBMITTED,),
            EnrolmentRequest.State.APPROVED,
            actors=(APPROVER, STAND_IN),
            independent=True,
            guards=(_full,),
            on_success=(_approved,),
        ),
        Transition(
            "reject",
            (EnrolmentRequest.State.SUBMITTED,),
            EnrolmentRequest.State.REJECTED,
            actors=(APPROVER, STAND_IN),
            independent=True,
            requires_comment=True,
            on_success=(_rejected,),
        ),
        Transition(
            "withdraw",
            (EnrolmentRequest.State.SUBMITTED,),
            EnrolmentRequest.State.WITHDRAWN,
            actors=(OWNER,),
        ),
    ),
    waiting_states=(EnrolmentRequest.State.SUBMITTED,),
)


def approver_for(person: PersonRef) -> PersonRef | None:
    """The supervisor from the HRMS record, when one is named and can sign in to decide; otherwise None, and
    the course administrators decide."""
    boss = person.supervisor
    if boss is None or not boss.is_active or boss.user is None or not boss.user.is_active:
        return None
    return boss


def _deciders(enrolment: EnrolmentRequest) -> list:
    if enrolment.approver is not None:
        return users_of([enrolment.approver, *delegates_of(enrolment.approver)])
    return list(users_with_role(Role.COURSE_ADMIN).exclude(person=enrolment.person))


def check_can_join(entry: CatalogueEntry, person: PersonRef) -> None:
    """Raise Refused when the person cannot ask to join the course."""
    from staffdev import paths
    from staffdev.completion import renewal_open

    site = entry.site
    if person.kind != PersonRef.Kind.STAFF or not person.is_active:
        raise Refused("not_staff", "Staff-development courses are for members of staff.", status=403)
    if not site.is_published or site.kind != CourseSite.Kind.STAFF_DEVELOPMENT:
        raise Refused("not_listed", "That course is not in the catalogue.", status=404)
    if Membership.objects.filter(site=site, person=person, is_active=True).exists():
        raise Refused("already_enrolled", "You are already on this course.")
    done = Completion.objects.filter(site=site, person=person).first()
    if done is not None and not renewal_open(done):
        raise Refused("already_completed", "You have already completed this course.")
    locked = paths.locked_by(person, site)
    if locked:
        raise Refused("path_locked", locked)
    if entry.self_enrol == CatalogueEntry.Enrol.CLOSED:
        raise Refused("closed", "This course is not open to join. Ask the course administrator.")
    left = places_left(entry)
    if left is not None and left <= 0:
        raise Refused("full", "The course is full. Ask the course administrator about another run.")
    if EnrolmentRequest.objects.filter(
        site=site, person=person, state=EnrolmentRequest.State.SUBMITTED
    ).exists():
        raise Refused("already_requested", "Your request to join is waiting for a decision.")


def join(request, entry: CatalogueEntry, person: PersonRef, *, reason: str = "") -> dict:
    """Join an open course at once, or ask to join one that needs approval."""
    check_can_join(entry, person)
    if entry.self_enrol == CatalogueEntry.Enrol.OPEN:
        with transaction.atomic():
            add_learner(request, entry.site, person, why="Joined from the catalogue")
        return {"outcome": "enrolled", "request": None}
    with transaction.atomic():
        enrolment = EnrolmentRequest.objects.create(
            site=entry.site,
            person=person,
            approver=approver_for(person),
            reason=reason.strip(),
            waiting_since=timezone.now(),
        )
        record(request, "create", enrolment, after=snapshot(enrolment), reason=enrolment.reason)
    notify(
        _deciders(enrolment),
        title=f"To decide: {person.full_name} asks to join {entry.site.title}",
        body=enrolment.reason or "No reason given.",
        link="/to-do",
        kind="approval",
        dedupe_key=f"enrolment:asked:{enrolment.pk}",
    )
    return {"outcome": "requested", "request": enrolment}
