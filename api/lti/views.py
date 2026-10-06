"""The addresses tools and browsers use for LTI 1.3 (item 6.07), under /api/lti/.

Browser steps answer with small pages of their own (the tool's pages are elsewhere); service calls from
tools answer in the IMS media types. Refusals carry {code, detail}; the token address answers as OAuth 2
does ({error, error_description}) as well.
"""

import html
import secrets
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import get_user
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import path
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import parsers, serializers
from rest_framework.decorators import api_view, authentication_classes, parser_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from audit.services import record, snapshot
from core.serializers import ErrorSerializer
from courses.access import can_teach
from courses.models import ContentItem, Module
from iam.permissions import RolePermission
from lti import keys, services
from lti.models import LineItem, Tool
from lti.services import Refusal

LINE_ITEM_TYPE = "application/vnd.ims.lis.v2.lineitem+json"
LINE_ITEMS_TYPE = "application/vnd.ims.lis.v2.lineitemcontainer+json"
SCORE_TYPE = "application/vnd.ims.lis.v1.score+json"
RESULTS_TYPE = "application/vnd.ims.lis.v2.resultcontainer+json"
MEMBERS_TYPE = "application/vnd.ims.lti-nrps.v2.membershipcontainer+json"


class LineItemParser(parsers.JSONParser):
    media_type = LINE_ITEM_TYPE


class ScoreParser(parsers.JSONParser):
    media_type = SCORE_TYPE


PAGE = """<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;margin:0 auto;padding:16px;max-width:36rem;color:#1b2a1f}}
button,a.button{{min-height:44px;padding:8px 16px;font:inherit}}.error{{color:#8a1c1c}}</style></head>
<body><main>{body}</main>{script}</body></html>"""


def _page(title: str, body: str, *, status=200, script="", nonce="", form_to="") -> HttpResponse:
    response = HttpResponse(
        PAGE.format(title=html.escape(title), body=body, script=script),
        status=status,
        content_type="text/html; charset=utf-8",
    )
    form_action = f"{urlparse(form_to).scheme}://{urlparse(form_to).netloc}" if form_to else "'none'"
    script_src = f"'nonce-{nonce}'" if nonce else "'none'"
    response["Content-Security-Policy"] = (
        f"default-src 'none'; style-src 'unsafe-inline'; script-src {script_src}; "
        f"form-action {form_action}; frame-ancestors 'none'; base-uri 'none'"
    )
    response["Cache-Control"] = "no-store"
    response["Referrer-Policy"] = "no-referrer"
    return response


def _refused_page(refusal: Refusal) -> HttpResponse:
    body = (
        "<h1>The tool could not be opened</h1>"
        f'<p class="error" role="alert">{html.escape(refusal.detail)}</p>'
        f'<p><a href="{html.escape(settings.PUBLIC_URL)}/">Back to the GSA LMS</a></p>'
    )
    return _page("The tool could not be opened", body, status=refusal.status)


def _refused(refusal: Refusal, **extra) -> Response:
    return Response({"code": refusal.code, "detail": refusal.detail, **extra}, status=refusal.status)


HTML = OpenApiResponse(OpenApiTypes.STR, description="A small page of its own")
REDIRECT = OpenApiResponse(description="Sends the browser to the tool's login initiation address")


# ---------------------------------------------------------------------------------------------------------
# Keys


@extend_schema(
    auth=[],
    responses={200: OpenApiTypes.OBJECT},
    summary="The LMS's public keys (JWKS), which tools check its messages against",
)
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def jwks(request):
    response = Response(keys.key_set())
    response["Cache-Control"] = "public, max-age=3600"
    return response


# ---------------------------------------------------------------------------------------------------------
# Launch: begun by a signed-in person, answered to the tool


@extend_schema(
    responses={302: REDIRECT, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="Open a tool placed in a module: begins the LTI launch (third-party initiated login)",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def launch(request, item_id: int):
    item = ContentItem.objects.filter(pk=item_id, tool_link__isnull=False).select_related("tool_link").first()
    if item is None:
        return _refused_page(Refusal("not_found", "No such tool on this course.", 404))
    placement = item.tool_link
    try:
        return HttpResponseRedirect(services.start(request.user, placement.tool, placement=placement))
    except Refusal as refusal:
        return _refused_page(refusal)


@extend_schema(
    parameters=[
        OpenApiParameter("tool", OpenApiTypes.INT, required=True),
        OpenApiParameter("module", OpenApiTypes.INT, required=True, description="Where the content goes"),
    ],
    responses={302: REDIRECT, 400: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="Choose content in a tool for a module (Deep Linking 2.0): begins the launch; teaching staff",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def choose(request):
    tool = Tool.objects.filter(pk=_int(request.query_params.get("tool"))).first()
    module = Module.objects.select_related("site").filter(pk=_int(request.query_params.get("module"))).first()
    if tool is None or module is None or not can_teach(request.user, module.site):
        return _refused_page(Refusal("not_found", "No such tool or module.", 404))
    try:
        return HttpResponseRedirect(services.start(request.user, tool, module=module))
    except Refusal as refusal:
        return _refused_page(refusal)


def _int(value) -> int:
    return int(value) if str(value or "").isdigit() else 0


@extend_schema(
    auth=[],
    parameters=[
        OpenApiParameter(name, OpenApiTypes.STR)
        for name in (
            "scope",
            "response_type",
            "response_mode",
            "client_id",
            "redirect_uri",
            "login_hint",
            "lti_message_hint",
            "nonce",
            "state",
            "prompt",
        )
    ],
    request={"application/x-www-form-urlencoded": {"type": "object", "description": "The same, as a form"}},
    responses={(200, "text/html"): HTML, (400, "text/html"): HTML, (403, "text/html"): HTML},
    summary="The OIDC authorisation address tools send the browser to: answers with the signed id_token, "
    "posted to the tool's registered address",
)
@api_view(["GET", "POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def auth(request):
    params = request.query_params if request.method == "GET" else request.data
    session_user = get_user(request._request)  # the browser's own session, if it sent one
    try:
        answer = services.authenticate(request, params, session_user=session_user)
    except Refusal as refusal:
        return _refused_page(refusal)
    nonce = secrets.token_urlsafe(16)
    body = (
        f"<h1>Opening {html.escape(answer.tool.name)}</h1>"
        f'<form id="launch" method="post" action="{html.escape(answer.redirect_uri)}">'
        f'<input type="hidden" name="id_token" value="{html.escape(answer.id_token)}">'
        f'<input type="hidden" name="state" value="{html.escape(answer.state)}">'
        '<noscript><button type="submit">Continue to the tool</button></noscript></form>'
    )
    script = f'<script nonce="{nonce}">document.getElementById("launch").submit();</script>'
    return _page(f"Opening {answer.tool.name}", body, script=script, nonce=nonce, form_to=answer.redirect_uri)


@extend_schema(
    auth=[],
    request={
        "application/x-www-form-urlencoded": {"type": "object", "properties": {"JWT": {"type": "string"}}}
    },
    responses={(200, "text/html"): HTML, (400, "text/html"): HTML, (403, "text/html"): HTML},
    summary="Where a tool returns the content chosen (Deep Linking 2.0): checked, then placed in the module",
)
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@parser_classes([parsers.FormParser, parsers.MultiPartParser])
def deep_links(request):
    try:
        launch_, placed = services.receive_deep_link(request, request.data.get("JWT") or "")
    except Refusal as refusal:
        return _refused_page(refusal)
    site = launch_.module.site
    back = f"{settings.PUBLIC_URL}/#/sites/{site.pk}/tools"
    names = "".join(f"<li>{html.escape(p.item.title)}</li>" for p in placed)
    body = (
        f"<h1>{len(placed)} added to {html.escape(launch_.module.title)}</h1>"
        + (f"<ul>{names}</ul>" if names else "<p>The tool returned nothing that could be added.</p>")
        + "<p>They are drafts: publish them on the course when they are ready for students.</p>"
        + f'<p><a href="{html.escape(back)}">Back to the course</a></p>'
    )
    return _page("Content added", body)


# ---------------------------------------------------------------------------------------------------------
# Token


class TokenSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    token_type = serializers.CharField()
    expires_in = serializers.IntegerField()
    scope = serializers.CharField()


@extend_schema(
    auth=[],
    request={
        "application/x-www-form-urlencoded": {
            "type": "object",
            "properties": {
                "grant_type": {"type": "string", "enum": ["client_credentials"]},
                "client_assertion_type": {"type": "string"},
                "client_assertion": {"type": "string"},
                "scope": {"type": "string"},
            },
        }
    },
    responses={200: TokenSerializer, 400: OpenApiTypes.OBJECT, 401: OpenApiTypes.OBJECT},
    summary="A bearer token for the grade and class-list services, for a client assertion the tool signed",
)
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@parser_classes([parsers.FormParser, parsers.MultiPartParser])
def token(request):
    try:
        answer = services.issue_token(request.data)
    except Refusal as refusal:
        return _refused(refusal, error=refusal.code, error_description=refusal.detail)
    response = Response(answer)
    response["Cache-Control"] = "no-store"
    return response


# ---------------------------------------------------------------------------------------------------------
# Assignment and Grade Services


@extend_schema(
    methods=["GET"],
    auth=[],
    operation_id="lti_line_items_list",
    parameters=[
        OpenApiParameter("resource_link_id", OpenApiTypes.STR),
        OpenApiParameter("resource_id", OpenApiTypes.STR),
        OpenApiParameter("tag", OpenApiTypes.STR),
    ],
    responses={200: OpenApiTypes.OBJECT, 401: ErrorSerializer, 404: ErrorSerializer},
    summary="A tool's line items on a course; bearer token from the token address",
)
@extend_schema(
    methods=["POST"],
    auth=[],
    operation_id="lti_line_items_create",
    request={LINE_ITEM_TYPE: OpenApiTypes.OBJECT},
    responses={201: OpenApiTypes.OBJECT, 400: ErrorSerializer, 401: ErrorSerializer, 404: ErrorSerializer},
    summary="A tool adds a line item (a gradebook column) on a course",
)
@api_view(["GET", "POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@parser_classes([LineItemParser, parsers.JSONParser])
def line_items(request, site_id: int):
    try:
        if request.method == "GET":
            tool = services.bearer_tool(request, services.SCOPE_LINEITEM, services.SCOPE_LINEITEM_READ)
            site = services.placed_site(tool, site_id)
            found = LineItem.objects.filter(site=site, tool=tool).select_related("placement")
            query = request.query_params
            if query.get("resource_link_id"):
                found = found.filter(placement__resource_link_id=services._uuid(query["resource_link_id"]))
            if query.get("resource_id"):
                found = found.filter(resource_id=query["resource_id"])
            if query.get("tag"):
                found = found.filter(tag=query["tag"])
            return Response([services.line_item_json(li) for li in found], content_type=LINE_ITEMS_TYPE)
        tool = services.bearer_tool(request, services.SCOPE_LINEITEM)
        site = services.placed_site(tool, site_id)
        if not tool.grades:
            raise Refusal("permission_denied", "This tool may not post to the gradebook.", 403)
        made = services.save_line_item(request, tool, site, request.data)
        return Response(services.line_item_json(made), status=201, content_type=LINE_ITEM_TYPE)
    except Refusal as refusal:
        return _refused(refusal)


def _own_line_item(tool: Tool, site_id: int, line_item_id: int) -> LineItem:
    site = services.placed_site(tool, site_id)
    found = LineItem.objects.filter(pk=line_item_id, site=site, tool=tool).select_related("placement").first()
    if found is None:
        raise Refusal("not_found", "No such line item for this tool.", 404)
    return found


@extend_schema(
    auth=[],
    request={LINE_ITEM_TYPE: OpenApiTypes.OBJECT},
    responses={200: OpenApiTypes.OBJECT, 204: None, 401: ErrorSerializer, 404: ErrorSerializer},
    summary="One of a tool's line items: read, change (PUT) or remove (DELETE); bearer token",
)
@api_view(["GET", "PUT", "DELETE"])
@authentication_classes([])
@permission_classes([AllowAny])
@parser_classes([LineItemParser, parsers.JSONParser])
def line_item(request, site_id: int, line_item_id: int):
    try:
        if request.method == "GET":
            tool = services.bearer_tool(request, services.SCOPE_LINEITEM, services.SCOPE_LINEITEM_READ)
            found = _own_line_item(tool, site_id, line_item_id)
            return Response(services.line_item_json(found), content_type=LINE_ITEM_TYPE)
        tool = services.bearer_tool(request, services.SCOPE_LINEITEM)
        found = _own_line_item(tool, site_id, line_item_id)
        if request.method == "DELETE":
            record(request, "delete", found, before=snapshot(found))
            found.delete()
            return Response(status=204)
        changed = services.save_line_item(request, tool, found.site, request.data, found)
        return Response(services.line_item_json(changed), content_type=LINE_ITEM_TYPE)
    except Refusal as refusal:
        return _refused(refusal)


@extend_schema(
    auth=[],
    request={SCORE_TYPE: OpenApiTypes.OBJECT},
    responses={
        204: None,
        400: ErrorSerializer,
        401: ErrorSerializer,
        404: ErrorSerializer,
        409: ErrorSerializer,
    },
    summary="A tool posts a student's score to a line item; it feeds the gradebook column",
)
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@parser_classes([ScoreParser, parsers.JSONParser])
def scores(request, site_id: int, line_item_id: int):
    try:
        tool = services.bearer_tool(request, services.SCOPE_SCORE)
        found = _own_line_item(tool, site_id, line_item_id)
        services.post_score(request, tool, found, request.data)
        return Response(status=204)
    except Refusal as refusal:
        return _refused(refusal)


@extend_schema(
    auth=[],
    parameters=[OpenApiParameter("user_id", OpenApiTypes.STR)],
    responses={200: OpenApiTypes.OBJECT, 401: ErrorSerializer, 404: ErrorSerializer},
    summary="The results held on a line item, for the tool that owns it",
)
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def results(request, site_id: int, line_item_id: int):
    try:
        tool = services.bearer_tool(request, services.SCOPE_RESULT_READ)
        found = _own_line_item(tool, site_id, line_item_id)
        rows = services.results_json(found, request.query_params.get("user_id"))
        return Response(rows, content_type=RESULTS_TYPE)
    except Refusal as refusal:
        return _refused(refusal)


# ---------------------------------------------------------------------------------------------------------
# Names and Role Provisioning Services


@extend_schema(
    auth=[],
    responses={200: OpenApiTypes.OBJECT, 401: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="The class list for a tool allowed to read it: opaque ids and roles; names and emails only as "
    "the tool's data-sharing settings allow",
)
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def members(request, site_id: int):
    try:
        tool = services.bearer_tool(request, services.SCOPE_MEMBERS)
        site = services.placed_site(tool, site_id)
        return Response(services.class_list(request, tool, site), content_type=MEMBERS_TYPE)
    except Refusal as refusal:
        return _refused(refusal)


urlpatterns = [
    path("jwks/", jwks, name="lti-jwks"),
    path("launch/<int:item_id>/", launch, name="lti-launch"),
    path("choose/", choose, name="lti-choose"),
    path("auth/", auth, name="lti-auth"),
    path("deep-links/", deep_links, name="lti-deep-links"),
    path("token/", token, name="lti-token"),
    path("sites/<int:site_id>/line-items/", line_items, name="lti-line-items"),
    path("sites/<int:site_id>/line-items/<int:line_item_id>/", line_item, name="lti-line-item"),
    path("sites/<int:site_id>/line-items/<int:line_item_id>/scores/", scores, name="lti-scores"),
    path("sites/<int:site_id>/line-items/<int:line_item_id>/results/", results, name="lti-results"),
    path("sites/<int:site_id>/members/", members, name="lti-members"),
]
