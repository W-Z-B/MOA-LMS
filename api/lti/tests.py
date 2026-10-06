"""LTI 1.3 with Advantage (item 6.07), tested against a fake tool that signs and checks tokens itself."""

import json
import re
import time
import uuid
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import AuditLog
from lti import keys, services
from lti.models import Launch, LineItem, Placement, Score, Tool, ToolUser

pytestmark = pytest.mark.django_db

LAUNCH_URL = "https://tool.example/launch"
CHOOSE_URL = "https://tool.example/choose"


class FakeTool:
    """An outside tool: its own key pair, and the messages a real tool would send."""

    def __init__(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.kid = "tool-key-1"

    def public_pem(self) -> str:
        return (
            self.key.public_key()
            .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
            .decode()
        )

    def public_jwk(self) -> dict:
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        return {**jwk, "kid": self.kid, "alg": "RS256", "use": "sig"}

    def sign(self, claims: dict, key=None) -> str:
        return jwt.encode(claims, key or self.key, algorithm="RS256", headers={"kid": self.kid})

    @staticmethod
    def platform_claims(id_token: str, client_id: str) -> dict:
        """Check the LMS's id_token as a tool does: against the LMS's published key set."""
        header = jwt.get_unverified_header(id_token)
        jwk = next(k for k in APIClient().get("/api/lti/jwks/").json()["keys"] if k["kid"] == header["kid"])
        public = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
        return jwt.decode(
            id_token, public, algorithms=["RS256"], audience=client_id, issuer=services.issuer()
        )


@pytest.fixture
def fake():
    return FakeTool()


@pytest.fixture
def tool(fake, course_admin):
    return Tool.objects.create(
        name="Soil quiz tool",
        oidc_login_url="https://tool.example/login",
        launch_url=LAUNCH_URL,
        deep_linking_url=CHOOSE_URL,
        public_key=fake.public_pem(),
        class_list=True,
    )


@pytest.fixture
def module(site):
    from courses.models import Module

    return Module.objects.create(site=site, title="Week 1: Soils")


@pytest.fixture
def placement(tool, module, lecturer, client_for):
    answer = client_for(lecturer.user).post(
        "/api/v1/tool-placements/",
        {"module": module.id, "tool": tool.id, "title": "Soil texture practice", "score_maximum": "20"},
        format="json",
    )
    assert answer.status_code == 201, answer.content
    found = Placement.objects.get(pk=answer.json()["id"])
    found.item.is_published = True
    found.item.save()
    return found


def begin(client, path: str) -> dict:
    answer = client.get(path)
    assert answer.status_code == 302, answer.content
    assert answer["Location"].startswith("https://tool.example/login?")
    return {k: v[0] for k, v in parse_qs(urlparse(answer["Location"]).query).items()}


def auth_params(tool, login: dict, *, nonce: str | None = None, redirect=LAUNCH_URL) -> dict:
    return {
        "scope": "openid",
        "response_type": "id_token",
        "response_mode": "form_post",
        "prompt": "none",
        "client_id": tool.client_id,
        "redirect_uri": redirect,
        "login_hint": login["login_hint"],
        "lti_message_hint": login["lti_message_hint"],
        "state": "tool-state-1",
        "nonce": uuid.uuid4().hex if nonce is None else nonce,
    }


def id_token_of(answer) -> str:
    assert answer.status_code == 200, answer.content
    return re.search(r'name="id_token" value="([^"]+)"', answer.content.decode()).group(1)


def launch_as(client, placement, tool) -> dict:
    login = begin(client, f"/api/lti/launch/{placement.item_id}/")
    answer = client.get("/api/lti/auth/", auth_params(tool, login))
    return FakeTool.platform_claims(id_token_of(answer), tool.client_id)


# ---------------------------------------------------------------------------------------------------------
# Keys


def test_the_platform_publishes_its_public_keys_and_signs_with_the_newest():
    first = keys.signing_key()
    published = APIClient().get("/api/lti/jwks/").json()["keys"]
    assert [k["kid"] for k in published] == [first.kid]
    assert "d" not in published[0]  # never the private part
    second = keys.make_key()
    kids = {k["kid"] for k in APIClient().get("/api/lti/jwks/").json()["keys"]}
    assert kids == {first.kid, second.kid}
    assert jwt.get_unverified_header(keys.sign({"a": 1}))["kid"] == second.kid


def test_a_tool_key_can_be_read_from_its_key_set_address(fake, tool, monkeypatch):
    tool.public_key, tool.jwks_url = "", "https://tool.example/jwks"
    tool.save()
    monkeypatch.setattr(keys, "fetch_json", lambda url: {"keys": [fake.public_jwk()]})
    token = fake.sign(
        {"iss": tool.client_id, "aud": "x", "iat": int(time.time()), "exp": int(time.time()) + 60}
    )
    assert keys.verify_from_tool(tool, token, audience="x")["iss"] == tool.client_id


def test_an_unreadable_key_set_is_refused(tool, fake, monkeypatch):
    tool.public_key, tool.jwks_url = "", "https://tool.example/jwks"
    tool.save()

    def down(url):
        raise OSError("no route")

    monkeypatch.setattr(keys, "fetch_json", down)
    token = fake.sign(
        {"iss": tool.client_id, "aud": "x", "iat": int(time.time()), "exp": int(time.time()) + 60}
    )
    with pytest.raises(services.Refusal) as refused:
        services.verify(tool, token, audience="x")
    assert refused.value.code == "no_key"


def test_key_set_addresses_must_be_secure():
    with pytest.raises(ValueError):
        keys.fetch_json("file:///etc/passwd")


# ---------------------------------------------------------------------------------------------------------
# Launch


def test_a_student_launch_carries_role_and_course_but_no_personal_data_by_default(
    placement, tool, student, client_for
):
    claims = launch_as(client_for(student.user), placement, tool)
    assert claims[f"{services.LTI}message_type"] == "LtiResourceLinkRequest"
    assert claims[f"{services.LTI}deployment_id"] == tool.deployment_id
    assert claims[f"{services.LTI}roles"] == [f"{services.MEMBERSHIP}Learner"]
    assert claims[f"{services.LTI}context"]["label"] == placement.site.code
    assert claims[f"{services.LTI}resource_link"]["id"] == str(placement.resource_link_id)
    assert claims["sub"] == ToolUser.objects.get(tool=tool, person=student).sub
    assert student.external_id not in json.dumps(claims)
    for personal in ("name", "given_name", "family_name", "email"):
        assert personal not in claims
    grades = claims[services.AGS_CLAIM]
    assert grades["lineitem"].endswith(f"/line-items/{LineItem.objects.get().id}/")
    assert claims[services.NRPS_CLAIM]["context_memberships_url"].endswith(
        f"/sites/{placement.site.id}/members/"
    )
    entry = AuditLog.objects.get(action="lti_launch")
    assert entry.actor == student.user and entry.after["name_shared"] is False


def test_names_and_emails_go_only_where_the_tool_is_allowed_them(placement, tool, lecturer, client_for):
    tool.share_name = tool.share_email = True
    tool.save()
    claims = launch_as(client_for(lecturer.user), placement, tool)
    assert claims["name"] == "Asha Persaud" and claims["email"] == "asha@gsa.edu.gy"
    assert claims[f"{services.LTI}roles"] == [f"{services.MEMBERSHIP}Instructor"]


def test_each_tool_knows_a_person_by_a_different_identifier(fake, placement, tool, student):
    other = Tool.objects.create(
        name="Other",
        oidc_login_url="https://o.example/l",
        launch_url="https://o.example/x",
        public_key=fake.public_pem(),
    )
    assert services.tool_user(tool, student) != services.tool_user(other, student)


def test_a_launch_is_refused_without_a_nonce_and_a_nonce_is_used_once(placement, tool, student, client_for):
    client = client_for(student.user)
    login = begin(client, f"/api/lti/launch/{placement.item_id}/")
    refused = client.get("/api/lti/auth/", auth_params(tool, login, nonce=""))
    assert refused.status_code == 400 and b"no nonce" in refused.content
    client.get("/api/lti/auth/", auth_params(tool, login, nonce="same-nonce"))
    again = begin(client, f"/api/lti/launch/{placement.item_id}/")
    replayed = client.get("/api/lti/auth/", auth_params(tool, again, nonce="same-nonce"))
    assert replayed.status_code == 400 and b"already used" in replayed.content


def test_a_launch_cannot_be_replayed(placement, tool, student, client_for):
    client = client_for(student.user)
    params = auth_params(tool, begin(client, f"/api/lti/launch/{placement.item_id}/"))
    assert client.get("/api/lti/auth/", params).status_code == 200
    params["nonce"] = uuid.uuid4().hex
    replayed = client.get("/api/lti/auth/", params)
    assert replayed.status_code == 400 and b"already used once" in replayed.content


def test_an_expired_launch_is_refused(placement, tool, student, client_for):
    client = client_for(student.user)
    login = begin(client, f"/api/lti/launch/{placement.item_id}/")
    Launch.objects.update(created_at=timezone.now() - timedelta(minutes=10))
    refused = client.get("/api/lti/auth/", auth_params(tool, login))
    assert refused.status_code == 400 and b"expired" in refused.content


def test_the_answer_goes_only_to_an_address_the_tool_registered(placement, tool, student, client_for):
    client = client_for(student.user)
    login = begin(client, f"/api/lti/launch/{placement.item_id}/")
    refused = client.get("/api/lti/auth/", auth_params(tool, login, redirect="https://evil.example/catch"))
    assert refused.status_code == 400 and b"did not register" in refused.content


def test_a_launch_begun_by_one_person_cannot_be_finished_by_another(
    placement, tool, student, other_student, client_for
):
    login = begin(client_for(student.user), f"/api/lti/launch/{placement.item_id}/")
    refused = client_for(other_student.user).get("/api/lti/auth/", auth_params(tool, login))
    assert refused.status_code == 403


def test_a_form_post_from_the_tool_without_a_session_is_answered(placement, tool, student, client_for):
    login = begin(client_for(student.user), f"/api/lti/launch/{placement.item_id}/")
    answer = APIClient().post("/api/lti/auth/", auth_params(tool, login))
    claims = FakeTool.platform_claims(id_token_of(answer), tool.client_id)
    assert claims["nonce"] and "form-action https://tool.example" in answer["Content-Security-Policy"]


def test_unknown_tools_and_wrong_requests_are_refused(placement, tool, student, client_for):
    client = client_for(student.user)
    login = begin(client, f"/api/lti/launch/{placement.item_id}/")
    params = auth_params(tool, login)
    assert client.get("/api/lti/auth/", {**params, "client_id": "nobody"}).status_code == 403
    assert client.get("/api/lti/auth/", {**params, "response_type": "code"}).status_code == 400
    assert client.get("/api/lti/auth/", {**params, "response_mode": "query"}).status_code == 400
    assert client.get("/api/lti/auth/", {**params, "login_hint": "made-up"}).status_code == 403


def test_drafts_and_switched_off_tools_do_not_open_for_students(placement, tool, student, client_for):
    client = client_for(student.user)
    placement.item.is_published = False
    placement.item.save()
    assert client.get(f"/api/lti/launch/{placement.item_id}/").status_code == 404
    placement.item.is_published = True
    placement.item.save()
    tool.is_active = False
    tool.save()
    assert client.get(f"/api/lti/launch/{placement.item_id}/").status_code == 403
    assert client.get("/api/lti/launch/999999/").status_code == 404


def test_people_outside_the_site_cannot_launch(placement, make_person, client_for):
    outsider = make_person("student", "26MRP0099", "Out", "Sider", "student")
    assert client_for(outsider.user).get(f"/api/lti/launch/{placement.item_id}/").status_code == 403


# ---------------------------------------------------------------------------------------------------------
# Deep Linking 2.0


def choose(client, tool, module) -> tuple[dict, dict]:
    login = begin(client, f"/api/lti/choose/?tool={tool.id}&module={module.id}")
    answer = client.get("/api/lti/auth/", auth_params(tool, login, redirect=CHOOSE_URL))
    claims = FakeTool.platform_claims(id_token_of(answer), tool.client_id)
    return login, claims


def link_response(fake, tool, request_claims, *, items=None, **changes) -> str:
    settings_claim = request_claims[f"{services.DL}deep_linking_settings"]
    now = int(time.time())
    claims = {
        "iss": tool.client_id,
        "aud": services.issuer(),
        "iat": now,
        "exp": now + 300,
        "nonce": uuid.uuid4().hex,
        f"{services.LTI}deployment_id": tool.deployment_id,
        f"{services.LTI}message_type": "LtiDeepLinkingResponse",
        f"{services.LTI}version": "1.3.0",
        f"{services.DL}data": settings_claim["data"],
        f"{services.DL}content_items": items
        if items is not None
        else [
            {
                "type": "ltiResourceLink",
                "title": "Soil texture by feel",
                "url": "https://tool.example/activity/7",
                "custom": {"activity": "7"},
                "lineItem": {"scoreMaximum": 10, "label": "Soil texture score", "tag": "practice"},
            },
            {"type": "html", "html": "<p>ignored</p>"},
        ],
    }
    claims.update(changes)
    return fake.sign(claims)


def test_content_chosen_in_a_tool_is_placed_in_the_module_as_a_draft(
    fake, tool, module, lecturer, client_for
):
    client = client_for(lecturer.user)
    _, request_claims = choose(client, tool, module)
    assert request_claims[f"{services.LTI}message_type"] == "LtiDeepLinkingRequest"
    assert request_claims[f"{services.LTI}roles"] == [f"{services.MEMBERSHIP}Instructor"]
    returned = APIClient().post("/api/lti/deep-links/", {"JWT": link_response(fake, tool, request_claims)})
    assert returned.status_code == 200 and b"1 added" in returned.content
    placed = Placement.objects.get()
    assert placed.item.module == module and not placed.item.is_published
    assert placed.item.url == f"/api/lti/launch/{placed.item_id}/"
    assert placed.target_url == "https://tool.example/activity/7" and placed.custom == {"activity": "7"}
    line_item = LineItem.objects.get()
    assert line_item.placement == placed and line_item.score_maximum == 10 and line_item.weight == 0
    assert AuditLog.objects.filter(
        action="create", entity="courses.contentitem", actor=lecturer.user
    ).exists()


def test_deep_linking_refusals(fake, tool, module, lecturer, client_for):
    client = client_for(lecturer.user)
    _, request_claims = choose(client, tool, module)
    post = APIClient().post
    wrong_deployment = link_response(fake, tool, request_claims, **{f"{services.LTI}deployment_id": "99"})
    answer = post("/api/lti/deep-links/", {"JWT": wrong_deployment})
    assert answer.status_code == 400 and b"deployment" in answer.content
    expired = link_response(
        fake, tool, request_claims, iat=int(time.time()) - 900, exp=int(time.time()) - 600
    )
    assert b"expired" in post("/api/lti/deep-links/", {"JWT": expired}).content
    no_nonce = link_response(fake, tool, request_claims, nonce="")
    assert b"no nonce" in post("/api/lti/deep-links/", {"JWT": no_nonce}).content
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode(
        jwt.decode(link_response(fake, tool, request_claims), options={"verify_signature": False}),
        other_key,
        algorithm="RS256",
    )
    assert b"not signed by the tool" in post("/api/lti/deep-links/", {"JWT": forged}).content
    wrong_audience = link_response(fake, tool, request_claims, aud="https://other-lms.example")
    assert b"not addressed" in post("/api/lti/deep-links/", {"JWT": wrong_audience}).content
    assert post("/api/lti/deep-links/", {"JWT": "not-a-token"}).status_code == 400
    good = link_response(fake, tool, request_claims)
    assert post("/api/lti/deep-links/", {"JWT": good}).status_code == 200
    replayed = post("/api/lti/deep-links/", {"JWT": good})
    assert replayed.status_code == 400 and b"already added" in replayed.content
    assert Placement.objects.count() == 1


def test_a_deep_link_answer_must_belong_to_a_selection_the_lms_began(
    fake, tool, module, lecturer, client_for
):
    client = client_for(lecturer.user)
    _, request_claims = choose(client, tool, module)
    request_claims[f"{services.DL}deep_linking_settings"]["data"] = "made-up"
    answer = APIClient().post("/api/lti/deep-links/", {"JWT": link_response(fake, tool, request_claims)})
    assert answer.status_code == 403


def test_deep_link_items_must_use_secure_addresses(fake, tool, module, lecturer, client_for):
    _, request_claims = choose(client_for(lecturer.user), tool, module)
    items = [{"type": "ltiResourceLink", "title": "Plain", "url": "http://tool.example/x"}]
    answer = APIClient().post(
        "/api/lti/deep-links/", {"JWT": link_response(fake, tool, request_claims, items=items)}
    )
    assert answer.status_code == 400 and not Placement.objects.exists()


def test_only_teaching_staff_choose_content(tool, module, student, client_for):
    answer = client_for(student.user).get(f"/api/lti/choose/?tool={tool.id}&module={module.id}")
    assert answer.status_code == 404


def test_a_tool_without_content_selection_is_refused(tool, module, lecturer, client_for):
    tool.deep_linking_url = ""
    tool.save()
    answer = client_for(lecturer.user).get(f"/api/lti/choose/?tool={tool.id}&module={module.id}")
    assert answer.status_code == 400


# ---------------------------------------------------------------------------------------------------------
# Tokens, grades and class lists


def assertion(fake, tool, **changes) -> str:
    now = int(time.time())
    claims = {
        "iss": tool.client_id,
        "sub": tool.client_id,
        "aud": services.address("token/"),
        "iat": now,
        "exp": now + 300,
        "jti": uuid.uuid4().hex,
    }
    claims.update(changes)
    return fake.sign(claims)


ALL_SCOPES = " ".join((*services.GRADE_SCOPES, services.SCOPE_MEMBERS))


def token_for(fake, tool, scope=ALL_SCOPES, **changes):
    return APIClient().post(
        "/api/lti/token/",
        {
            "grant_type": "client_credentials",
            "client_assertion_type": services.ASSERTION_TYPE,
            "client_assertion": assertion(fake, tool, **changes),
            "scope": scope,
        },
    )


def tool_client(fake, tool) -> APIClient:
    answer = token_for(fake, tool)
    assert answer.status_code == 200, answer.content
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {answer.json()['access_token']}")
    return client


def test_token_refusals(fake, tool):
    replayed_jti = assertion(fake, tool)
    form = {
        "grant_type": "client_credentials",
        "client_assertion_type": services.ASSERTION_TYPE,
        "client_assertion": replayed_jti,
        "scope": services.SCOPE_SCORE,
    }
    assert APIClient().post("/api/lti/token/", form).status_code == 200
    again = APIClient().post("/api/lti/token/", form)
    assert again.status_code == 400 and again.json()["error"] == "replayed"
    expired = token_for(fake, tool, iat=int(time.time()) - 900, exp=int(time.time()) - 600)
    assert expired.json()["code"] == "expired"
    assert token_for(fake, tool, aud="https://other.example/token").json()["code"] == "wrong_audience"
    assert token_for(fake, tool, jti="").json()["code"] == "invalid_client"
    assert token_for(fake, tool, scope="https://example.com/other").json()["code"] == "invalid_scope"
    assert token_for(fake, tool, iss="nobody").status_code == 401
    form.update(grant_type="password")
    assert APIClient().post("/api/lti/token/", form).json()["error"] == "unsupported_grant_type"
    form.update(grant_type="client_credentials", client_assertion_type="other")
    assert APIClient().post("/api/lti/token/", form).status_code == 401
    form.update(client_assertion_type=services.ASSERTION_TYPE, client_assertion="junk")
    assert APIClient().post("/api/lti/token/", form).status_code == 401


def test_scopes_follow_what_the_tool_may_do(fake, tool):
    tool.class_list = False
    tool.save()
    granted = token_for(fake, tool).json()["scope"].split()
    assert services.SCOPE_MEMBERS not in granted and services.SCOPE_SCORE in granted


def score_body(sub: str, given=8, **changes) -> dict:
    body = {
        "userId": sub,
        "scoreGiven": given,
        "scoreMaximum": 10,
        "activityProgress": "Completed",
        "gradingProgress": "FullyGraded",
        "timestamp": timezone.now().isoformat(),
        "comment": "Well done",
    }
    body.update(changes)
    return body


def test_scores_posted_by_the_tool_feed_the_gradebook_and_coursework(
    fake, placement, tool, student, other_student, lecturer, client_for
):
    from assessments.services import coursework_percent, gradebook

    sub = launch_as(client_for(student.user), placement, tool)["sub"]
    line_item = LineItem.objects.get()
    base = f"/api/lti/sites/{placement.site.id}/line-items/{line_item.id}/"
    client = tool_client(fake, tool)
    posted = client.post(
        f"{base}scores/", json.dumps(score_body(sub)), content_type="application/vnd.ims.lis.v1.score+json"
    )
    assert posted.status_code == 204, posted.content
    score = Score.objects.get()
    assert score.person == student and score.graded
    assert AuditLog.objects.filter(action="lti_score", subject=student.id).exists()
    book = gradebook(placement.site)
    assert book["tools"][0]["title"] == "Soil texture practice"
    row = next(r for r in book["rows"] if r["person_id"] == student.id)
    assert row["tools"][str(line_item.id)] == {"state": "graded", "percent": "80.00"}
    assert coursework_percent(placement.site, student) is None  # weight 0: shown, not counted
    changed = client_for(lecturer.user).patch(
        f"/api/v1/tool-line-items/{line_item.id}/", {"weight": "1"}, format="json"
    )
    assert changed.status_code == 200, changed.content
    assert coursework_percent(placement.site, student) == 80
    results = client.get(f"{base}results/").json()
    assert results[0]["userId"] == sub and results[0]["resultScore"] == 8.0
    exported = client_for(lecturer.user).get(f"/api/v1/sites/{placement.site.id}/gradebook/export/")
    text = b"".join(exported.streaming_content).decode()
    assert "Soil texture practice (Soil quiz tool, %)" in text and ",80.00," in text and "not yet due" in text


def test_score_refusals(fake, placement, tool, student, lecturer, client_for):
    sub = launch_as(client_for(student.user), placement, tool)["sub"]
    teacher_sub = services.tool_user(tool, lecturer)
    line_item = LineItem.objects.get()
    url = f"/api/lti/sites/{placement.site.id}/line-items/{line_item.id}/scores/"
    client = tool_client(fake, tool)

    def post(body):
        return client.post(url, json.dumps(body), content_type="application/json")

    assert post(score_body(sub)).status_code == 204
    stale = score_body(sub, timestamp=(timezone.now() - timedelta(days=1)).isoformat())
    assert post(stale).status_code == 409
    assert post(score_body("someone-else")).status_code == 400
    assert post(score_body(teacher_sub)).status_code == 400  # scores are for students
    assert post(score_body(sub, activityProgress="Done")).status_code == 400
    assert post(score_body(sub, timestamp="soon")).status_code == 400
    assert post(score_body(sub, scoreMaximum=0)).status_code == 400
    assert post(score_body(sub, scoreGiven="lots")).status_code == 400
    assert post(["not", "an", "object"]).status_code == 400
    assert APIClient().post(url, "{}", content_type="application/json").status_code == 401
    other = Tool.objects.create(
        name="Other",
        oidc_login_url="https://o.example/l",
        launch_url="https://o.example/x",
        public_key=fake.public_pem(),
    )
    elsewhere = tool_client(fake, other)
    assert (
        elsewhere.post(url, json.dumps(score_body(sub)), content_type="application/json").status_code == 404
    )


def test_a_tool_manages_its_own_line_items(fake, placement, tool):
    client = tool_client(fake, tool)
    base = f"/api/lti/sites/{placement.site.id}/line-items/"
    made = client.post(
        base,
        json.dumps(
            {"label": "Quiz 2", "scoreMaximum": 50, "resourceLinkId": str(placement.resource_link_id)}
        ),
        content_type="application/vnd.ims.lis.v2.lineitem+json",
    )
    assert made.status_code == 201, made.content
    url = made.json()["id"]
    assert made.json()["resourceLinkId"] == str(placement.resource_link_id)
    listed = client.get(base, {"resource_link_id": str(placement.resource_link_id)}).json()
    assert {li["label"] for li in listed} == {"Soil texture practice", "Quiz 2"}
    assert client.get(base, {"tag": "none"}).json() == []
    assert client.get(base, {"resource_id": "none"}).json() == []
    path = urlparse(url).path
    changed = client.put(
        path, json.dumps({"label": "Quiz two", "scoreMaximum": 40}), content_type="application/json"
    )
    assert changed.json()["label"] == "Quiz two"
    assert client.get(path).json()["scoreMaximum"] == 40.0
    assert client.post(base, json.dumps({"label": ""}), content_type="application/json").status_code == 400
    bad_link = {"label": "x", "scoreMaximum": 1, "resourceLinkId": str(uuid.uuid4())}
    assert client.post(base, json.dumps(bad_link), content_type="application/json").status_code == 400
    assert client.delete(path).status_code == 204
    assert client.get(path).status_code == 404
    assert client.get("/api/lti/sites/999999/line-items/").status_code == 404


def test_the_class_list_respects_the_data_sharing_setting(fake, placement, tool, student):
    client = tool_client(fake, tool)
    url = f"/api/lti/sites/{placement.site.id}/members/"
    listed = client.get(url).json()
    assert len(listed["members"]) == 3 and listed["context"]["label"] == placement.site.code
    assert all(set(m) == {"status", "user_id", "roles"} for m in listed["members"])
    assert AuditLog.objects.filter(action="lti_class_list", after__members=3).exists()
    tool.share_name = True
    tool.save()
    assert {m.get("name") for m in client.get(url).json()["members"]} >= {"Ravi Singh"}
    tool.class_list = False
    tool.save()
    assert client.get(url).status_code == 403


def test_a_token_without_the_scope_is_refused(fake, placement, tool):
    answer = token_for(fake, tool, scope=services.SCOPE_SCORE)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {answer.json()['access_token']}")
    assert client.get(f"/api/lti/sites/{placement.site.id}/members/").status_code == 403
    client.credentials(HTTP_AUTHORIZATION="Bearer unknown")
    assert client.get(f"/api/lti/sites/{placement.site.id}/members/").status_code == 401


# ---------------------------------------------------------------------------------------------------------
# Registering and placing tools


def tool_form(**changes) -> dict:
    form = {
        "name": "Crop simulator",
        "oidc_login_url": "https://sim.example/login",
        "launch_url": "https://sim.example/launch",
        "jwks_url": "https://sim.example/jwks",
    }
    form.update(changes)
    return form


def test_course_administrators_register_tools_with_data_sharing_off(course_admin, client_for):
    client = client_for(course_admin)
    made = client.post("/api/v1/tools/", tool_form(), format="json")
    assert made.status_code == 201, made.content
    body = made.json()
    assert body["client_id"] and body["share_name"] is False and body["share_email"] is False
    assert "Each person's name" not in body["receives"]
    assert AuditLog.objects.filter(action="create", entity="lti.tool").exists()
    assert (
        client.post("/api/v1/tools/", tool_form(launch_url="http://sim.example/x"), format="json").status_code
        == 400
    )
    assert client.post("/api/v1/tools/", tool_form(jwks_url=""), format="json").status_code == 400
    bad_key = tool_form(jwks_url="", public_key="-----BEGIN PUBLIC KEY-----\nnope\n-----END PUBLIC KEY-----")
    assert client.post("/api/v1/tools/", bad_key, format="json").status_code == 400
    assert (
        client.post("/api/v1/tools/", tool_form(jwks_url="", public_key="{}"), format="json").status_code
        == 400
    )
    changed = client.patch(f"/api/v1/tools/{body['id']}/", {"share_name": True}, format="json")
    assert "Each person's name" in changed.json()["receives"]
    assert AuditLog.objects.filter(action="update", entity="lti.tool").exists()
    assert client.get("/api/v1/lti/platform/").json()["jwks_url"].endswith("/api/lti/jwks/")
    assert client.delete(f"/api/v1/tools/{body['id']}/").status_code == 204


def test_a_tool_can_be_registered_with_a_pasted_jwk(course_admin, client_for, fake):
    form = tool_form(jwks_url="", public_key=json.dumps(fake.public_jwk()))
    assert client_for(course_admin).post("/api/v1/tools/", form, format="json").status_code == 201


def test_teaching_staff_see_tools_but_not_their_registration(tool, lecturer, student, client_for, site):
    listed = client_for(lecturer.user).get("/api/v1/tools/").json()["results"]
    assert listed[0]["name"] == tool.name and "client_id" not in listed[0] and "public_key" not in listed[0]
    assert client_for(lecturer.user).post("/api/v1/tools/", tool_form(), format="json").status_code == 403
    assert client_for(lecturer.user).get("/api/v1/lti/platform/").status_code == 403
    assert client_for(student.user).get("/api/v1/tools/").json()["results"] == []


def test_the_tools_on_a_site(placement, tool, student, lecturer, client_for):
    teaching = client_for(lecturer.user).get(f"/api/v1/sites/{placement.site.id}/tools/").json()
    assert teaching["teaching"] and teaching["line_items"][0]["label"] == "Soil texture practice"
    assert teaching["tools"][0]["receives"]
    seen = client_for(student.user).get(f"/api/v1/sites/{placement.site.id}/tools/").json()
    assert seen["placements"][0]["launch_url"] == f"/api/lti/launch/{placement.item_id}/"
    assert seen["line_items"] == [] and seen["tools"] == []


def test_line_item_settings_are_for_teaching_staff_only(placement, student, lecturer, client_for, site):
    from assessments.models import GradeCategory
    from courses.models import CourseSite

    line_item = LineItem.objects.get()
    url = f"/api/v1/tool-line-items/{line_item.id}/"
    assert client_for(student.user).patch(url, {"weight": "2"}, format="json").status_code == 403
    other_site_category = GradeCategory.objects.create(
        site=CourseSite.objects.create(code="X1", title="X"),
        name="Other",
        weight=1,
    )
    refused = client_for(lecturer.user).patch(url, {"grade_category": other_site_category.id}, format="json")
    assert refused.status_code == 400
    mine = GradeCategory.objects.create(site=site, name="Tools", weight=1)
    assert client_for(lecturer.user).patch(url, {"grade_category": mine.id}, format="json").status_code == 200


def test_removing_a_placement_keeps_columns_that_hold_scores(
    fake, placement, tool, student, lecturer, client_for
):
    sub = launch_as(client_for(student.user), placement, tool)["sub"]
    line_item = LineItem.objects.get()
    tool_client(fake, tool).post(
        f"/api/lti/sites/{placement.site.id}/line-items/{line_item.id}/scores/",
        json.dumps(score_body(sub)),
        content_type="application/json",
    )
    assert client_for(student.user).delete(f"/api/v1/tool-placements/{placement.id}/").status_code == 403
    assert client_for(lecturer.user).delete(f"/api/v1/tool-placements/{placement.id}/").status_code == 204
    assert not Placement.objects.exists() and LineItem.objects.filter(pk=line_item.pk).exists()
    assert AuditLog.objects.filter(action="delete", entity="courses.contentitem").exists()


def test_a_placed_tool_cannot_be_removed(placement, tool, course_admin, client_for):
    answer = client_for(course_admin).delete(f"/api/v1/tools/{tool.id}/")
    assert answer.status_code == 409


def test_course_administrators_without_a_person_record_cannot_launch(placement, course_admin, client_for):
    assert client_for(course_admin).get(f"/api/lti/launch/{placement.item_id}/").status_code == 403


def test_a_tool_held_back_by_release_conditions_neither_shows_nor_opens(placement, student, client_for):
    placement.item.available_from = timezone.now() + timedelta(days=2)
    placement.item.save()
    client = client_for(student.user)
    assert client.get(f"/api/v1/sites/{placement.site.id}/tools/").json()["placements"] == []
    assert client.get(f"/api/lti/launch/{placement.item_id}/").status_code == 404
