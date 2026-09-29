"""Integration and reference endpoints of the LMS."""

from django.urls import path
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from audit.models import AuditLog
from courses.models import CourseSite
from iam.permissions import RolePermission
from integration.auth import ServiceKeyAuthentication, scope
from integration.models import CampusRef


@api_view(["GET"])
@authentication_classes([ServiceKeyAuthentication])
@permission_classes([scope("sites:read")])
def sites(request):
    """Course sites for sibling systems (for example to link from the SRMS to the course site)."""
    rows = [
        {
            "code": s.code,
            "title": s.title,
            "term_code": s.term_code,
            "campus_code": s.campus_code,
            "kind": s.kind,
            "is_published": s.is_published,
        }
        for s in CourseSite.objects.all()
    ]
    AuditLog.objects.create(
        action="integration:sites.read",
        entity="integration.serviceclient",
        entity_id=request.auth.pk,
        after={"client": request.auth.name, "count": len(rows)},
    )
    return Response({"count": len(rows), "results": rows})


@api_view(["GET"])
@permission_classes([RolePermission])
def campuses(request):
    return Response([{"id": c.id, "code": c.code, "name": c.name} for c in CampusRef.objects.all()])


integration_urls = [path("sites/", sites, name="integration-sites")]
reference_urls = [path("campuses/", campuses, name="reference-campuses")]
