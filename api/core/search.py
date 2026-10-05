"""Search (items 2.07 to 2.09): one box that finds sites, content, assignments, quizzes, forum
threads, people and staff-development courses in the catalogue (item 5.02).

Search never finds what the person could not open: each kind is looked for inside the same list its own
page shows, so a student finds only the published, released items of their own courses, and never finds
people. Teaching staff find the people on the sites they teach; administrators and auditors find anyone.
Searching is a read and is not written to the audit trail.
"""

from django.db.models import Q, Value
from django.db.models.functions import Concat
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from assessments.models import Assignment
from core.home import persona
from core.serializers import ErrorSerializer
from courses import release
from courses.access import taught_sites, visible_sites
from courses.models import ContentItem, Membership
from iam.permissions import RolePermission
from iam.services import BROAD_READ_ROLES, has_role
from people.models import PersonRef

SHOWN = 5  # at most this many of each kind
SHORTEST = 2


def _hit(id_: int, title: str, sub: str, link: str) -> dict:
    return {"id": id_, "title": title, "sub": sub, "link": link}


def _sites(user, q: str) -> list[dict]:
    sites = visible_sites(user).filter(Q(title__icontains=q) | Q(code__icontains=q)).order_by("title", "id")
    return [_hit(s.id, s.title, s.code, f"/sites/{s.id}") for s in sites[:SHOWN]]


def _content(request, q: str) -> list[dict]:
    """As courses.api.ContentItemViewSet lists them: published items on the sites the person can open,
    drafts only where they teach, and nothing a student's release conditions or a review hold back."""
    user = request.user
    items = ContentItem.objects.filter(module__site__in=visible_sites(user), title__icontains=q)
    items = items.filter(is_published=True) | items.filter(module__site__in=taught_sites(user))
    hidden = release.hidden_items(request, items)
    if hidden:
        items = items.exclude(id__in=hidden)
    items = items.select_related("module__site").order_by("title", "id")
    return [_hit(i.id, i.title, i.module.site.title, f"/sites/{i.module.site_id}") for i in items[:SHOWN]]


def _assignments(user, q: str) -> list[dict]:
    """As assessments.api lists them: published ones, and drafts where the person teaches."""
    qs = Assignment.objects.filter(site__in=visible_sites(user), title__icontains=q)
    qs = (qs.filter(is_published=True) | qs.filter(site__in=taught_sites(user))).select_related("site")
    return [
        _hit(
            a.id,
            a.title,
            f"{a.site.title} · due {timezone.localtime(a.due_at):%d/%m/%Y}",
            f"/sites/{a.site_id}/assignments",
        )
        for a in qs.order_by("due_at", "id")[:SHOWN]
    ]


def _quizzes(user, q: str) -> list[dict]:
    """As quizzes.api.QuizViewSet lists them: published ones, and drafts where the person teaches."""
    from quizzes.models import Quiz

    qs = Quiz.objects.filter(site__in=visible_sites(user), title__icontains=q)
    qs = (qs.filter(is_published=True) | qs.filter(site__in=taught_sites(user))).select_related("site")
    return [
        _hit(z.id, z.title, z.site.title, f"/sites/{z.site_id}/quizzes")
        for z in qs.order_by("title", "id")[:SHOWN]
    ]


def _threads(user, q: str) -> list[dict]:
    """Forum threads by title, in the forums the person sees (forums.services.forum_visible)."""
    from forums.models import Thread
    from forums.services import visible_forums

    threads = Thread.objects.filter(forum__site__in=visible_sites(user), title__icontains=q).select_related(
        "forum__site", "forum__module"
    )
    forums = {f.id for f in visible_forums(user, {t.forum for t in threads})}
    shown = [t for t in threads.order_by("-last_post_at", "-id") if t.forum_id in forums]
    return [
        _hit(t.id, t.title, f"{t.forum.site.title} · {t.forum.title}", f"/forums/{t.forum_id}/threads/{t.id}")
        for t in shown[:SHOWN]
    ]


def _people(user, q: str) -> list[dict]:
    """Staff only: the people on the sites the person teaches, or anyone for administrators and auditors.
    Each links to a site the searcher can open that the person belongs to, when there is one."""
    if persona(user) == "student":
        return []
    people = PersonRef.objects.annotate(whole=Concat("first_name", Value(" "), "last_name"))
    if not has_role(user, *BROAD_READ_ROLES):
        members = Membership.objects.filter(site__in=taught_sites(user), is_active=True)
        people = people.filter(pk__in=members.values("person_id"))
    people = people.filter(
        Q(first_name__icontains=q)
        | Q(last_name__icontains=q)
        | Q(whole__icontains=q)
        | Q(external_id__icontains=q)
    ).order_by("last_name", "first_name", "id")
    rows = []
    sites = visible_sites(user) if has_role(user, *BROAD_READ_ROLES) else taught_sites(user)
    for person in people[:SHOWN]:
        shared = (
            Membership.objects.filter(person=person, is_active=True, site__in=sites)
            .order_by("site__title")
            .first()
        )
        kind = "Student" if person.kind == PersonRef.Kind.STUDENT else "Staff"
        rows.append(
            _hit(
                person.id,
                person.full_name,
                f"{person.external_id} · {kind}",
                f"/sites/{shared.site_id}" if shared else "",
            )
        )
    return rows


def _catalogue(user, q: str) -> list[dict]:
    """Staff-development courses in the catalogue (item 5.02): for members of staff, and for course
    administrators and auditors; never for students."""
    from staffdev.models import CatalogueEntry

    person = getattr(user, "person", None)
    if not has_role(user, *BROAD_READ_ROLES) and (person is None or person.kind != PersonRef.Kind.STAFF):
        return []
    entries = CatalogueEntry.objects.filter(site__kind="staff_development", site__is_published=True).filter(
        Q(site__title__icontains=q) | Q(site__code__icontains=q) | Q(summary__icontains=q)
    )
    return [
        _hit(e.site_id, e.site.title, e.audience or e.site.code, f"/staff-development/{e.site_id}")
        for e in entries.select_related("site").order_by("site__title", "id")[:SHOWN]
    ]


class HitSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    sub = serializers.CharField(help_text="A second line: the site's code, the course, or a student number")
    link = serializers.CharField(help_text="Where it opens in the web app; empty when nowhere")


class SearchSerializer(serializers.Serializer):
    sites = HitSerializer(many=True)
    content = HitSerializer(many=True)
    assignments = HitSerializer(many=True)
    quizzes = HitSerializer(many=True)
    threads = HitSerializer(many=True, help_text="Forum threads, by title")
    people = HitSerializer(many=True, help_text="Always empty for a student")
    catalogue = HitSerializer(many=True, help_text="Staff-development courses; always empty for a student")


@extend_schema(
    parameters=[OpenApiParameter("q", OpenApiTypes.STR, description="At least two letters")],
    responses={200: SearchSerializer, 400: ErrorSerializer, 403: ErrorSerializer},
    summary=f"Find sites, content, assignments, quizzes, threads and people I may open, {SHOWN} of each "
    "at most",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def search(request):
    q = (request.query_params.get("q") or "").strip()
    if len(q) < SHORTEST:
        return Response({"code": "bad_request", "detail": "Type at least two letters."}, status=400)
    user = request.user
    found = {
        "sites": _sites(user, q),
        "content": _content(request, q),
        "assignments": _assignments(user, q),
        "quizzes": _quizzes(user, q),
        "threads": _threads(user, q),
        "people": _people(user, q),
        "catalogue": _catalogue(user, q),
    }
    return Response(SearchSerializer(found).data)
