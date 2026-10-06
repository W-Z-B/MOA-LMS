"""The LTI 1.3 messages and services, with the rules each one is checked against (item 6.07).

Launch (OIDC third-party initiated login, then the signed id_token):
  1. A signed-in person opens a placement (or teaching staff choose content in a tool). The LMS records a
     Launch and sends the browser to the tool's login address with a login hint that names it.
  2. The tool sends the browser back to the LMS's authorisation address. The LMS checks the tool, the
     address the answer goes to (one the tool registered), the hint (the same person, once, within
     LTI_LAUNCH_SECONDS) and the nonce (never seen before from this tool), then posts a signed id_token to
     the tool. The token carries the person's opaque identifier for this tool, their role on the site, the
     course, and their name or email only when the tool's data-sharing settings allow.

Deep Linking 2.0: the tool posts a signed token back with the content chosen. It is accepted only from a
registered tool, for its deployment, with a fresh nonce, before it expires, and naming a content-selection
launch this LMS began and that has not already returned. Each resource link becomes a link item in the
chosen module, as a draft, with a gradebook column when the tool asks for one.

Services (Assignment and Grade Services, Names and Role Provisioning Services): the tool asks for a bearer
token with a client assertion it signs (OAuth 2 client credentials, JWT bearer). The assertion must be
signed by the tool's key, addressed to this LMS, unexpired and not replayed (its jti is kept).
"""

import datetime
import hashlib
import secrets
import time
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from urllib.parse import urlencode, urlparse

import jwt
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from audit.services import record, snapshot
from courses import release
from courses.access import ADMIN, site_role
from courses.models import ContentItem, CourseSite, Membership, Module
from lti import keys
from lti.models import AccessToken, Launch, LineItem, Placement, Score, Tool, ToolUser, UsedValue

LTI = "https://purl.imsglobal.org/spec/lti/claim/"
DL = "https://purl.imsglobal.org/spec/lti-dl/claim/"
AGS_CLAIM = "https://purl.imsglobal.org/spec/lti-ags/claim/endpoint"
NRPS_CLAIM = "https://purl.imsglobal.org/spec/lti-nrps/claim/namesroleservice"
SCOPE_LINEITEM = "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem"
SCOPE_LINEITEM_READ = "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly"
SCOPE_RESULT_READ = "https://purl.imsglobal.org/spec/lti-ags/scope/result.readonly"
SCOPE_SCORE = "https://purl.imsglobal.org/spec/lti-ags/scope/score"
SCOPE_MEMBERS = "https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly"
GRADE_SCOPES = (SCOPE_LINEITEM, SCOPE_LINEITEM_READ, SCOPE_RESULT_READ, SCOPE_SCORE)
ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"

MEMBERSHIP = "http://purl.imsglobal.org/vocab/lis/v2/membership#"
ROLES = {
    Membership.SiteRole.STUDENT: [f"{MEMBERSHIP}Learner"],
    Membership.SiteRole.LECTURER: [f"{MEMBERSHIP}Instructor"],
    Membership.SiteRole.ASSISTANT: [f"{MEMBERSHIP}Instructor", f"{MEMBERSHIP}Instructor#TeachingAssistant"],
    ADMIN: [
        f"{MEMBERSHIP}Administrator",
        "http://purl.imsglobal.org/vocab/lis/v2/institution/person#Administrator",
    ],
}
TEACHING_ROLES = (Membership.SiteRole.LECTURER, Membership.SiteRole.ASSISTANT, ADMIN)
ACTIVITY = {"Initialized", "Started", "InProgress", "Submitted", "Completed"}
GRADING = {"FullyGraded", "Pending", "PendingManual", "Failed", "NotReady"}


class Refusal(Exception):
    """A message or request that is refused: a stable code, a sentence, and the HTTP status."""

    def __init__(self, code: str, detail: str, status: int = 400):
        super().__init__(detail)
        self.code, self.detail, self.status = code, detail, status


def issuer() -> str:
    return settings.LTI_ISSUER.rstrip("/")


def address(path: str) -> str:
    return f"{issuer()}/api/lti/{path}"


def platform_details() -> dict:
    """What a tool's maker needs to register the LMS with their tool."""
    return {
        "issuer": issuer(),
        "jwks_url": address("jwks/"),
        "auth_url": address("auth/"),
        "token_url": address("token/"),
        "deep_link_return_url": address("deep-links/"),
        "launch_start": "Each placement opens at /api/lti/launch/<content item id>/",
    }


def _actor(request, user):
    """The request as the audit log sees it, with the person who began a launch as the actor: the tool's
    returns come from the tool's page, without the person's session."""
    return SimpleNamespace(user=user, META=getattr(request, "META", {}))


def _once(tool: Tool, kind: str, value: str) -> None:
    """Remember a nonce or token id; refuse one already seen from this tool. Old ones are forgotten."""
    UsedValue.objects.filter(at__lt=timezone.now() - timedelta(days=2)).delete()
    try:
        with transaction.atomic():
            UsedValue.objects.create(tool=tool, kind=kind, value=value[:255])
    except IntegrityError as error:
        raise Refusal("replayed", "This message was already used once and cannot be used again.") from error


def tool_user(tool: Tool, person) -> str:
    return ToolUser.objects.get_or_create(tool=tool, person=person)[0].sub


def _https(url: str) -> bool:
    return urlparse(url).scheme == "https" or (settings.DEBUG and urlparse(url).scheme == "http")


# ---------------------------------------------------------------------------------------------------------
# Launch


def start(user, tool: Tool, *, placement: Placement | None = None, module: Module | None = None) -> str:
    """Begin a launch for a signed-in person; the address of the tool's login initiation."""
    if not tool.is_active:
        raise Refusal("tool_off", "This tool has been switched off by a course administrator.", 403)
    if getattr(user, "person", None) is None:
        raise Refusal(
            "no_person", "Only people with a staff or student record can open outside tools.", status=403
        )
    site = placement.site if placement is not None else module.site
    role = site_role(user, site)
    if role not in ROLES:
        raise Refusal("not_on_site", "Only the site's members can open its tools.", 403)
    if placement is None:
        if role not in TEACHING_ROLES:
            raise Refusal("not_teaching", "Only the site's teaching staff can add content from a tool.", 403)
        if not tool.deep_linking_url:
            raise Refusal("no_selection", "This tool does not offer content to choose.", 400)
        kind = Launch.Kind.DEEP_LINKING
    else:
        item = placement.item
        # A student opens it only as the module shows it: published, not under review, and released to them.
        if role not in TEACHING_ROLES and not release.item_open(item, release.student_state(user.person)):
            raise Refusal("not_found", "No such tool on this course.", 404)
        kind = Launch.Kind.RESOURCE_LINK
    launch = Launch.objects.create(kind=kind, user=user, tool=tool, placement=placement, module=module)
    target = tool.deep_linking_url if placement is None else (placement.target_url or tool.launch_url)
    params = {
        "iss": issuer(),
        "login_hint": launch.hint,
        "lti_message_hint": launch.hint,
        "target_link_uri": target,
        "client_id": tool.client_id,
        "lti_deployment_id": tool.deployment_id,
    }
    separator = "&" if "?" in tool.oidc_login_url else "?"
    return f"{tool.oidc_login_url}{separator}{urlencode(params)}"


@dataclass
class Answer:
    redirect_uri: str
    id_token: str
    state: str
    tool: Tool


def authenticate(request, params, session_user=None) -> Answer:
    """The tool's authentication request (OIDC), checked; the signed id_token to post back."""
    if params.get("scope") != "openid" or params.get("response_type") != "id_token":
        raise Refusal("invalid_request", "The tool's request is not an LTI launch request.")
    if params.get("response_mode", "form_post") != "form_post":
        raise Refusal("invalid_request", "Only form_post answers are supported.")
    tool = Tool.objects.filter(client_id=params.get("client_id") or "", is_active=True).first()
    if tool is None:
        raise Refusal("unknown_tool", "This tool is not registered with the LMS, or is switched off.", 403)
    redirect_uri = params.get("redirect_uri") or ""
    if redirect_uri not in tool.allowed_redirects():
        raise Refusal("bad_redirect", "The tool asked for an answer address it did not register.")
    hint = params.get("login_hint") or ""
    launch = (
        Launch.objects.select_related("user", "placement__item__module__site", "module__site")
        .filter(hint=hint, tool=tool)
        .first()
    )
    if launch is None or params.get("lti_message_hint", hint) != hint:
        raise Refusal("bad_hint", "This launch was not begun by the LMS.", 403)
    if launch.authenticated_at is not None:
        raise Refusal("replayed", "This launch was already used once. Open the tool again from the course.")
    if timezone.now() - launch.created_at > timedelta(seconds=settings.LTI_LAUNCH_SECONDS):
        raise Refusal("expired", "This launch has expired. Open the tool again from the course.")
    if session_user is not None and session_user.is_authenticated and session_user.pk != launch.user_id:
        raise Refusal("wrong_person", "This launch was begun by someone else.", 403)
    nonce = params.get("nonce") or ""
    if not nonce:
        raise Refusal("bad_nonce", "The tool's request has no nonce.")
    _once(tool, "auth_nonce", nonce)
    launch.authenticated_at = timezone.now()
    launch.save(update_fields=["authenticated_at"])
    claims = launch_claims(launch, nonce)
    record(
        _actor(request, launch.user),
        "lti_launch",
        tool,
        after={
            "kind": launch.kind,
            "site": _site_of(launch).pk,
            "placement": launch.placement_id,
            "name_shared": tool.share_name,
            "email_shared": tool.share_email,
        },
        reason="Opened an outside tool",
    )
    return Answer(redirect_uri, keys.sign(claims), params.get("state") or "", tool)


def _site_of(launch: Launch) -> CourseSite:
    return launch.placement.site if launch.placement_id else launch.module.site


def context_claim(site: CourseSite) -> dict:
    return {
        "id": f"site-{site.pk}",
        "label": site.code,
        "title": site.title,
        "type": ["http://purl.imsglobal.org/vocab/lis/v2/course#CourseOffering"],
    }


def personal_claims(tool: Tool, person) -> dict:
    """Only what the course administrator allowed for this tool; nothing by default."""
    shared = {}
    if tool.share_name:
        shared.update(name=person.full_name, given_name=person.first_name, family_name=person.last_name)
    if tool.share_email and person.email:
        shared["email"] = person.email
    return shared


def services_claims(tool: Tool, site: CourseSite, placement: Placement | None) -> dict:
    claims = {}
    if tool.grades:
        endpoint = {"scope": list(GRADE_SCOPES), "lineitems": address(f"sites/{site.pk}/line-items/")}
        if placement is not None:
            mine = list(placement.line_items.filter(tool=tool).values_list("pk", flat=True))
            if len(mine) == 1:
                endpoint["lineitem"] = address(f"sites/{site.pk}/line-items/{mine[0]}/")
        claims[AGS_CLAIM] = endpoint
    if tool.class_list:
        claims[NRPS_CLAIM] = {
            "context_memberships_url": address(f"sites/{site.pk}/members/"),
            "service_versions": ["2.0"],
        }
    return claims


def launch_claims(launch: Launch, nonce: str) -> dict:
    tool, user = launch.tool, launch.user
    person = user.person
    site = _site_of(launch)
    now = int(time.time())
    claims = {
        "iss": issuer(),
        "aud": tool.client_id,
        "azp": tool.client_id,
        "sub": tool_user(tool, person),
        "iat": now,
        "exp": now + settings.LTI_LAUNCH_SECONDS,
        "nonce": nonce,
        f"{LTI}version": "1.3.0",
        f"{LTI}deployment_id": tool.deployment_id,
        f"{LTI}roles": ROLES.get(site_role(user, site), []),
        f"{LTI}context": context_claim(site),
        f"{LTI}tool_platform": {"guid": issuer(), "name": "GSA LMS", "product_family_code": "gsa-lms"},
        f"{LTI}launch_presentation": {
            "document_target": "window",
            "return_url": f"{settings.PUBLIC_URL}/#/sites/{site.pk}",
            "locale": "en-GB",
        },
        **personal_claims(tool, person),
        **services_claims(tool, site, launch.placement),
    }
    if launch.kind == Launch.Kind.RESOURCE_LINK:
        placement = launch.placement
        claims.update(
            {
                f"{LTI}message_type": "LtiResourceLinkRequest",
                f"{LTI}target_link_uri": placement.target_url or tool.launch_url,
                f"{LTI}resource_link": {"id": str(placement.resource_link_id), "title": placement.item.title},
                f"{LTI}custom": placement.custom or {},
            }
        )
    else:
        claims.update(
            {
                f"{LTI}message_type": "LtiDeepLinkingRequest",
                f"{LTI}target_link_uri": tool.deep_linking_url,
                f"{DL}deep_linking_settings": {
                    "deep_link_return_url": address("deep-links/"),
                    "accept_types": ["ltiResourceLink"],
                    "accept_presentation_document_targets": ["window"],
                    "accept_multiple": True,
                    "auto_create": True,
                    "title": launch.module.title,
                    "data": launch.hint,
                },
            }
        )
    return claims


# ---------------------------------------------------------------------------------------------------------
# Deep Linking 2.0


def _decimal(value, name: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise Refusal("invalid_value", f"{name} is not a number.") from error
    if not number.is_finite() or number < 0:
        raise Refusal("invalid_value", f"{name} must be a number of 0 or more.")
    return number


def place(module: Module, tool: Tool, title: str, *, target_url="", custom=None, user=None) -> Placement:
    """A link item in the module that opens the tool, as a draft for teaching staff to publish."""
    last = module.items.aggregate(last=Max("position"))["last"] or 0
    item = ContentItem.objects.create(
        module=module,
        kind=ContentItem.Kind.LINK,
        title=title[:160],
        url="https://placeholder.invalid/",  # replaced below once the item has its id
        position=last + 1,
        is_published=False,
        licence=ContentItem.Licence.PERMISSION_HELD,
        source=f"Outside tool: {tool.name}",
        created_by=user,
        updated_by=user,
    )
    item.url = f"/api/lti/launch/{item.pk}/"
    item.save(update_fields=["url"])
    return Placement.objects.create(
        item=item, tool=tool, target_url=target_url, custom=custom or {}, created_by=user, updated_by=user
    )


def receive_deep_link(request, token: str) -> tuple[Launch, list[Placement]]:
    """The content a tool returns from a content-selection launch, checked and placed in the module."""
    try:
        unverified = jwt.decode(token, options={"verify_signature": False})
    except jwt.InvalidTokenError as error:
        raise Refusal("invalid_token", "The tool's answer is not a signed token.") from error
    tool = Tool.objects.filter(client_id=str(unverified.get("iss", "")), is_active=True).first()
    if tool is None:
        raise Refusal("unknown_tool", "This tool is not registered with the LMS, or is switched off.", 403)
    claims = verify(tool, token, audience=issuer())
    if claims.get(f"{LTI}deployment_id") != tool.deployment_id:
        raise Refusal("wrong_deployment", "The answer names a deployment the LMS did not give this tool.")
    if claims.get(f"{LTI}message_type") != "LtiDeepLinkingResponse" or claims.get(f"{LTI}version") != "1.3.0":
        raise Refusal("invalid_request", "The tool's answer is not a content selection.")
    nonce = claims.get("nonce") or ""
    if not nonce:
        raise Refusal("bad_nonce", "The tool's answer has no nonce.")
    launch = (
        Launch.objects.select_related("user", "module__site")
        .filter(hint=str(claims.get(f"{DL}data") or ""), tool=tool, kind=Launch.Kind.DEEP_LINKING)
        .first()
    )
    if launch is None or launch.authenticated_at is None:
        raise Refusal("bad_hint", "This answer does not belong to a content selection the LMS began.", 403)
    if launch.returned_at is not None:
        raise Refusal("replayed", "Content from this selection was already added.")
    if timezone.now() - launch.created_at > timedelta(seconds=settings.LTI_DEEP_LINK_SECONDS):
        raise Refusal("expired", "The content selection took too long. Choose the content again.")
    _once(tool, "link_nonce", nonce)
    items = claims.get(f"{DL}content_items") or []
    if not isinstance(items, list):
        raise Refusal("invalid_request", "The tool's answer has no list of content.")
    actor = _actor(request, launch.user)
    placed = []
    with transaction.atomic():
        launch.returned_at = timezone.now()
        launch.save(update_fields=["returned_at"])
        for content in items:
            if not isinstance(content, dict) or content.get("type") != "ltiResourceLink":
                continue  # only links to the tool are accepted (accept_types)
            url = str(content.get("url") or "")
            if url and not _https(url):
                raise Refusal("invalid_value", "A chosen item's address is not a secure (https) address.")
            custom = content.get("custom") if isinstance(content.get("custom"), dict) else {}
            title = str(content.get("title") or tool.name)
            placement = place(launch.module, tool, title, target_url=url, custom=custom, user=launch.user)
            record(
                actor,
                "create",
                placement.item,
                after=snapshot(placement.item),
                reason="Chosen in " + tool.name,
            )
            line = content.get("lineItem")
            if isinstance(line, dict) and tool.grades:
                line_item = LineItem.objects.create(
                    site=launch.module.site,
                    tool=tool,
                    placement=placement,
                    label=str(line.get("label") or title)[:160],
                    score_maximum=_positive(line.get("scoreMaximum")),
                    resource_id=str(line.get("resourceId") or "")[:255],
                    tag=str(line.get("tag") or "")[:255],
                    created_by=launch.user,
                )
                record(actor, "create", line_item, after=snapshot(line_item))
            placed.append(placement)
    return launch, placed


def _positive(value) -> Decimal:
    number = _decimal(value, "scoreMaximum")
    if number <= 0:
        raise Refusal("invalid_value", "scoreMaximum must be more than 0.")
    return number


def verify(tool: Tool, token: str, *, audience) -> dict:
    """A token from the tool, with each failure said plainly. Expired tokens have their own code."""
    try:
        return keys.verify_from_tool(tool, token, audience=audience)
    except jwt.ExpiredSignatureError as error:
        raise Refusal("expired", "The tool's message has expired.") from error
    except jwt.InvalidAudienceError as error:
        raise Refusal("wrong_audience", "The tool's message was not addressed to this LMS.") from error
    except keys.ToolKeyError as error:
        raise Refusal("no_key", str(error)) from error
    except jwt.InvalidTokenError as error:
        raise Refusal("invalid_token", "The tool's message is not signed by the tool's key.") from error


# ---------------------------------------------------------------------------------------------------------
# Tokens for the services


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def allowed_scopes(tool: Tool) -> set[str]:
    return (set(GRADE_SCOPES) if tool.grades else set()) | ({SCOPE_MEMBERS} if tool.class_list else set())


def issue_token(form) -> dict:
    """OAuth 2 client credentials with a signed client assertion (RFC 7523), as LTI Advantage uses."""
    if form.get("grant_type") != "client_credentials":
        raise Refusal("unsupported_grant_type", "Only the client credentials grant is supported.")
    if form.get("client_assertion_type") != ASSERTION_TYPE:
        raise Refusal("invalid_client", "A signed client assertion is required.", 401)
    assertion = form.get("client_assertion") or ""
    try:
        unverified = jwt.decode(assertion, options={"verify_signature": False})
    except jwt.InvalidTokenError as error:
        raise Refusal("invalid_client", "The client assertion is not a signed token.", 401) from error
    tool = Tool.objects.filter(client_id=str(unverified.get("iss", "")), is_active=True).first()
    if tool is None or unverified.get("sub") != tool.client_id:
        raise Refusal("invalid_client", "This tool is not registered with the LMS, or is switched off.", 401)
    claims = verify(tool, assertion, audience=[address("token/"), issuer()])
    jti = claims.get("jti") or ""
    if not jti:
        raise Refusal("invalid_client", "The client assertion has no jti.", 401)
    _once(tool, "assertion", jti)
    asked = set((form.get("scope") or "").split())
    granted = sorted(asked & allowed_scopes(tool))
    if not granted:
        raise Refusal("invalid_scope", "None of the scopes asked for are allowed for this tool.")
    token = secrets.token_urlsafe(32)
    AccessToken.objects.filter(expires_at__lt=timezone.now()).delete()
    AccessToken.objects.create(
        tool=tool,
        token_hash=_hash(token),
        scopes=granted,
        expires_at=timezone.now() + timedelta(seconds=settings.LTI_TOKEN_SECONDS),
    )
    return {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": settings.LTI_TOKEN_SECONDS,
        "scope": " ".join(granted),
    }


def bearer_tool(request, *scopes: str) -> Tool:
    """The tool a service request comes from, holding at least one of the scopes."""
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if not header.startswith("Bearer "):
        raise Refusal("not_authenticated", "A bearer token from the token address is required.", 401)
    found = (
        AccessToken.objects.select_related("tool")
        .filter(token_hash=_hash(header[7:].strip()), expires_at__gt=timezone.now(), tool__is_active=True)
        .first()
    )
    if found is None:
        raise Refusal("not_authenticated", "The bearer token is unknown or has expired.", 401)
    if not set(scopes) & set(found.scopes):
        raise Refusal("permission_denied", "The token does not allow this.", 403)
    return found.tool


def placed_site(tool: Tool, site_id: int) -> CourseSite:
    """A site the tool is placed on; the services answer for no other."""
    site = CourseSite.objects.filter(pk=site_id, modules__items__tool_link__tool=tool).distinct().first()
    if site is None:
        raise Refusal("not_found", "The tool is not used on this course.", 404)
    return site


# ---------------------------------------------------------------------------------------------------------
# Assignment and Grade Services


def line_item_json(line_item: LineItem) -> dict:
    data = {
        "id": address(f"sites/{line_item.site_id}/line-items/{line_item.pk}/"),
        "label": line_item.label,
        "scoreMaximum": float(line_item.score_maximum),
    }
    if line_item.resource_id:
        data["resourceId"] = line_item.resource_id
    if line_item.tag:
        data["tag"] = line_item.tag
    if line_item.placement_id:
        data["resourceLinkId"] = str(line_item.placement.resource_link_id)
    return data


def save_line_item(request, tool: Tool, site: CourseSite, body: dict, line_item: LineItem | None = None):
    """Create or change a line item from the tool's JSON."""
    if not isinstance(body, dict):
        raise Refusal("invalid_request", "Send the line item as a JSON object.")
    label = str(body.get("label") or "").strip()
    if not label:
        raise Refusal("invalid_value", "A line item needs a label.")
    maximum = _positive(body.get("scoreMaximum"))
    placement = None
    link = body.get("resourceLinkId")
    if link:
        placement = Placement.objects.filter(
            resource_link_id=_uuid(link), tool=tool, item__module__site=site
        ).first()
        if placement is None:
            raise Refusal("invalid_value", "resourceLinkId is not a placement of this tool on this course.")
    before = snapshot(line_item) if line_item else None
    if line_item is None:
        line_item = LineItem(site=site, tool=tool)
    line_item.label, line_item.score_maximum = label[:160], maximum
    line_item.resource_id = str(body.get("resourceId") or "")[:255]
    line_item.tag = str(body.get("tag") or "")[:255]
    line_item.placement = placement
    line_item.save()
    record(request, "update" if before else "create", line_item, before=before, after=snapshot(line_item))
    return line_item


def _uuid(value):
    import uuid

    try:
        return uuid.UUID(str(value))
    except ValueError:
        return uuid.UUID(int=0)


def post_score(request, tool: Tool, line_item: LineItem, body: dict) -> Score:
    """A score the tool posts for one student. A score older than the one held is refused."""
    if not isinstance(body, dict):
        raise Refusal("invalid_request", "Send the score as a JSON object.")
    sub = str(body.get("userId") or "")
    found = ToolUser.objects.select_related("person").filter(tool=tool, sub=sub).first()
    if (
        found is None
        or not Membership.objects.filter(
            site=line_item.site, person=found.person, role=Membership.SiteRole.STUDENT, is_active=True
        ).exists()
    ):
        raise Refusal("unknown_user", "userId is not a student on this course known to this tool.")
    activity, grading = body.get("activityProgress"), body.get("gradingProgress")
    if activity not in ACTIVITY or grading not in GRADING:
        raise Refusal("invalid_value", "activityProgress and gradingProgress must be LTI values.")
    stamp = parse_datetime(str(body.get("timestamp") or ""))
    if stamp is None:
        raise Refusal("invalid_value", "timestamp must be a date and time.")
    if timezone.is_naive(stamp):
        stamp = timezone.make_aware(stamp, datetime.UTC)
    given = maximum = None
    if body.get("scoreGiven") is not None:
        given = _decimal(body["scoreGiven"], "scoreGiven")
        maximum = _positive(body.get("scoreMaximum"))
    score = Score.objects.filter(line_item=line_item, person=found.person).first()
    if score is not None and stamp <= score.timestamp:
        raise Refusal("stale_score", "A later score is already held for this student.", 409)
    before = snapshot(score) if score else None
    if score is None:
        score = Score(line_item=line_item, person=found.person)
    score.score_given, score.score_maximum = given, maximum
    score.activity_progress, score.grading_progress = activity, grading
    score.comment = str(body.get("comment") or "")[:5000]
    score.timestamp = stamp
    score.save()
    record(request, "lti_score", score, before=before, after=snapshot(score), reason=f"Posted by {tool.name}")
    return score


def results_json(line_item: LineItem, user_id: str | None = None) -> list[dict]:
    scores = line_item.scores.select_related("person")
    subs = dict(ToolUser.objects.filter(tool=line_item.tool).values_list("person_id", "sub"))
    rows = []
    for score in scores:
        sub = subs.get(score.person_id)
        if sub is None or (user_id and sub != user_id):
            continue
        row = {
            "id": f"{line_item_json(line_item)['id']}results/{score.pk}/",
            "scoreOf": line_item_json(line_item)["id"],
            "userId": sub,
        }
        if score.score_given is not None:
            row.update(resultScore=float(score.score_given), resultMaximum=float(score.score_maximum))
        if score.comment:
            row["comment"] = score.comment
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------------------------------------
# Names and Role Provisioning Services


def class_list(request, tool: Tool, site: CourseSite) -> dict:
    """The class list as the tool may see it: opaque ids and roles, and names or emails only if allowed."""
    if not tool.class_list:
        raise Refusal("permission_denied", "This tool may not read class lists.", 403)
    members = Membership.objects.filter(site=site, is_active=True).select_related("person")
    rows = [
        {
            "status": "Active",
            "user_id": tool_user(tool, m.person),
            "roles": ROLES[m.role],
            **personal_claims(tool, m.person),
        }
        for m in members.order_by("person__last_name", "person__first_name", "id")
    ]
    record(
        request,
        "lti_class_list",
        tool,
        after={
            "site": site.pk,
            "members": len(rows),
            "name_shared": tool.share_name,
            "email_shared": tool.share_email,
        },
        reason="Class list read by the tool",
    )
    return {"id": address(f"sites/{site.pk}/members/"), "context": context_claim(site), "members": rows}


# ---------------------------------------------------------------------------------------------------------
# The gradebook


def line_items(site: CourseSite):
    return LineItem.objects.filter(site=site).select_related("tool").order_by("id")


def score_state(line_item: LineItem, score: Score | None) -> tuple[Decimal | None, str]:
    """A fraction and a state as the coursework total uses them: graded once the tool says FullyGraded,
    pending while it has something not yet graded, not_due when nothing has come."""
    if score is not None and score.graded and score.score_maximum:
        return min(score.score_given / score.score_maximum, Decimal(1)), "graded"
    if score is not None:
        return None, "pending"
    return None, "not_due"


def coursework_line_items(site: CourseSite, person) -> list[tuple[LineItem, Decimal | None, str]]:
    """The weighted line items of the site, each with the student's fraction and state."""
    counted = [li for li in line_items(site) if li.weight > 0]
    scores = {s.line_item_id: s for s in Score.objects.filter(line_item__in=counted, person=person)}
    return [(li, *score_state(li, scores.get(li.id))) for li in counted]


def gradebook_cells(site: CourseSite, person) -> dict:
    scores = {s.line_item_id: s for s in Score.objects.filter(line_item__site=site, person=person)}
    cells = {}
    for li in line_items(site):
        fraction, state = score_state(li, scores.get(li.id))
        cells[str(li.id)] = {
            "state": state,
            "percent": None if fraction is None else str((fraction * 100).quantize(Decimal("0.01"))),
        }
    return cells
