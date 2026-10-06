"""Closed sites refuse changes (item 7.12), wherever in the API the change is made.

The middleware remembers the request for the length of every request that can change something. Before any
record that belongs to a course site is saved or deleted (terms.lifecycle.site_models), the guard works out
the site's phase; a closed site refuses the change unless the person is a course administrator or an
administrator (a change made for an appeal, audited as usual), and an archived site refuses everyone.

Work done outside a request (the nightly jobs, the SRMS sync, the retention schedule's disposal) is never
refused: those follow their own rules. Reading is never refused.
"""

from contextvars import ContextVar
from functools import lru_cache

from django.db.models.signals import pre_delete, pre_save
from rest_framework import status
from rest_framework.exceptions import APIException

from iam.models import Role
from iam.services import has_role

_request: ContextVar = ContextVar("terms_guard_request", default=None)
SAFE = {"GET", "HEAD", "OPTIONS", "TRACE"}


class SiteClosed(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "site_closed"
    default_detail = "This course site is closed and kept read-only."


class ClosedSiteMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in SAFE:
            return self.get_response(request)
        token = _request.set(request)
        try:
            return self.get_response(request)
        finally:
            _request.reset(token)


@lru_cache(maxsize=1)
def _paths() -> dict[str, str]:
    from terms.lifecycle import site_models

    return site_models()


def check(instance) -> None:
    """Refuse a change to a record of a closed site made in a request; see the module's description."""
    request = _request.get()
    if request is None:
        return
    path = _paths().get(instance._meta.label_lower)
    if path is None:
        return
    from courses.models import CourseSite
    from terms import lifecycle

    site_id = lifecycle.site_id_of(instance, path)
    if site_id is None:
        return
    # One look per site per request: a quiz answer or a register saves several records of the same site.
    seen = request.__dict__.setdefault("_terms_phases", {})
    if site_id not in seen:
        # The stored site, not one being changed in this save (a new term code is checked as it stands).
        site = CourseSite.objects.filter(pk=site_id).first()
        seen[site_id] = (site, lifecycle.site_phase(site) if site is not None else None)
    site, phase = seen[site_id]
    if phase is None or not phase.locked:
        return
    user = getattr(request, "user", None)
    if phase.phase == lifecycle.CLOSED and has_role(user, Role.ADMINISTRATOR, Role.COURSE_ADMIN):
        return
    raise SiteClosed(lifecycle.explain(site, phase))


def _before_save(sender, instance, raw=False, **kwargs):
    if not raw:
        check(instance)


def _before_delete(sender, instance, **kwargs):
    check(instance)


def connect() -> None:
    pre_save.connect(_before_save, dispatch_uid="terms.guard.save")
    pre_delete.connect(_before_delete, dispatch_uid="terms.guard.delete")
