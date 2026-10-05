"""One approvals engine for every module (ported from the HRMS approvals/engine.py, its item 1.33): states,
transitions, who may act, guards, side effects.

A definition is plain data. The staff-development enrolment request is the first to use it in the LMS
(staffdev.workflow). Who may act is one of: the person the request belongs to, the approver it was sent to
(or a colleague standing in for them that day), any course administrator while it has no approver to go to,
or anyone holding a named role. A decision is never taken by the person the request belongs to.

The engine also notes when a request starts waiting at a step, so time limits can remind and escalate.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from approvals.delegation import acts_for
from audit.services import record
from iam.models import Role
from iam.services import has_role

OWNER = "owner"  # the person the request belongs to
APPROVER = "approver"  # the person the request was sent to, or whoever stands in for them that day
STAND_IN = "stand_in"  # a course administrator, only while the request has no approver to go to


class WorkflowError(Exception):
    code = "invalid_transition"

    def __init__(self, detail: str, code: str | None = None):
        super().__init__(detail)
        self.detail = detail
        if code:
            self.code = code


@dataclass(frozen=True)
class Transition:
    action: str
    sources: tuple[str, ...]
    target: str
    actors: tuple[str, ...]  # role codes, or OWNER, APPROVER, STAND_IN
    requires_comment: bool = False
    independent: bool = False  # a decision on the request: never taken by the person it belongs to
    guards: tuple[Callable, ...] = field(default_factory=tuple)  # run first; raise WorkflowError to refuse
    on_success: tuple[Callable, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class WorkflowDefinition:
    key: str
    transitions: tuple[Transition, ...]
    # States in which the request waits for someone's decision: entering one starts its clock.
    waiting_states: tuple[str, ...] = ()

    def _can_act(self, instance, user, transition: Transition) -> bool:
        person = getattr(user, "person", None)
        is_owner = person is not None and person.pk == instance.person_id
        if transition.independent and is_owner:
            return False
        approver_id = getattr(instance, "approver_id", None)
        for actor in transition.actors:
            if actor == OWNER:
                if is_owner:
                    return True
            elif actor == APPROVER:
                if person is not None and approver_id is not None:
                    if person.pk == approver_id or acts_for(person, approver_id):
                        return True
            elif actor == STAND_IN:
                if approver_id is None and has_role(user, Role.COURSE_ADMIN):
                    return True
            elif has_role(user, actor):
                return True
        return False

    def allowed_actions(self, instance, user) -> list[str]:
        return [
            t.action
            for t in self.transitions
            if instance.state in t.sources and self._can_act(instance, user, t)
        ]

    def apply(self, instance, action: str, *, request, comment: str = ""):
        """Move `instance` through `action` as request.user, run side effects, audit. Atomic."""
        user = request.user
        matches = [t for t in self.transitions if t.action == action and instance.state in t.sources]
        if not matches:
            raise WorkflowError(f"'{action}' is not allowed from state '{instance.state}'.")
        transition = matches[0]
        if not self._can_act(instance, user, transition):
            raise WorkflowError("You are not permitted to perform this action.", code="forbidden_actor")
        if transition.requires_comment and not comment.strip():
            raise WorkflowError("A comment is required for this action.", code="comment_required")
        for guard in transition.guards:
            guard(instance, request)
        with transaction.atomic():
            before = {"state": instance.state}
            instance.previous_state = instance.state
            instance.state = transition.target
            if comment:
                instance.decision_comment = comment
            if hasattr(instance, "waiting_since"):
                instance.waiting_since = timezone.now() if transition.target in self.waiting_states else None
            instance.decided_by = user
            instance.save()
            for hook in transition.on_success:
                hook(instance, request)
            record(request, f"transition:{action}", instance, before=before, after={"state": instance.state})
        return instance
