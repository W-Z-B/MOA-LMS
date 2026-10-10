"""Requests the server sends out: no redirects, no private networks from data (core.outbound; ASVS 5.2.6)."""

import socket
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from core import outbound


class Handler(BaseHTTPRequestHandler):
    seen: list = []

    def do_GET(self):  # noqa: N802 - the standard library's name
        Handler.seen.append((self.path, self.headers.get("Authorization")))
        if self.path == "/moved":
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/secret")
            self.end_headers()
            return
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    Handler.seen = []
    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    httpd.server_close()


def get(url, **options):
    return outbound.urlopen(urllib.request.Request(url), timeout=5, schemes=("http", "https"), **options)  # noqa: S310


def fake_lookup(monkeypatch, *answers):
    """Make names look up to these addresses, one answer per lookup (the last one repeats)."""
    calls = []

    def getaddrinfo(host, port, *args, **kwargs):
        address = answers[min(len(calls), len(answers) - 1)]
        calls.append(host)
        family = socket.AF_INET6 if ":" in address else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (address, port))]

    monkeypatch.setattr(outbound.socket, "getaddrinfo", getaddrinfo)
    return calls


def test_an_address_from_data_may_not_reach_a_private_network(server, settings):
    settings.OUTBOUND_PRIVATE_HOSTS = []
    with pytest.raises(outbound.OutboundRefused, match="private or reserved"):
        get(f"{server}/keys")
    assert Handler.seen == []


def test_a_configured_sibling_on_the_private_network_is_reached_only_when_its_host_is_named(server, settings):
    settings.OUTBOUND_PRIVATE_HOSTS = []
    with pytest.raises(outbound.OutboundRefused):
        get(f"{server}/staff", configured=True)
    settings.OUTBOUND_PRIVATE_HOSTS = ["127.0.0.1"]
    with get(f"{server}/staff", configured=True) as answer:
        assert answer.status == 200 and answer.read() == b'{"ok": true}'
    # Data never earns the exception, even for the same host.
    with pytest.raises(outbound.OutboundRefused):
        get(f"{server}/staff")


def test_a_redirect_is_refused_and_never_followed(server, settings):
    settings.OUTBOUND_PRIVATE_HOSTS = ["127.0.0.1"]
    request = urllib.request.Request(f"{server}/moved", headers={"Authorization": "Api-Key k"})  # noqa: S310
    with pytest.raises(urllib.error.HTTPError) as refused:
        outbound.urlopen(request, timeout=5, configured=True, schemes=("http",))
    assert refused.value.code == 302
    assert [path for path, _ in Handler.seen] == ["/moved"]  # /secret was never asked for


@pytest.mark.parametrize(
    "address",
    ["10.1.2.3", "192.168.0.5", "172.16.0.1", "127.0.0.1", "169.254.169.254", "0.0.0.0", "::1",  # noqa: S104
     "fd00::1", "fe80::1", "::ffff:127.0.0.1", "224.0.0.1", "100.64.0.1"],
)  # fmt: skip
def test_private_loopback_link_local_and_metadata_addresses_are_refused(monkeypatch, address):
    fake_lookup(monkeypatch, address)
    with pytest.raises(outbound.OutboundRefused, match="private or reserved"):
        outbound.check_url("https://tool.example/jwks")


def test_a_public_address_is_accepted_and_odd_addresses_are_refused(monkeypatch):
    fake_lookup(monkeypatch, "93.184.216.34")
    assert outbound.check_url("https://tool.example/jwks") == "https://tool.example/jwks"
    for url in (
        "http://tool.example/jwks",
        "file:///etc/passwd",
        "https://user:pw@tool.example/",
        "https:///x",
    ):
        with pytest.raises(outbound.OutboundRefused):
            outbound.check_url(url)


def test_a_name_that_cannot_be_found_is_told_apart(monkeypatch):
    def missing(*args, **kwargs):
        raise socket.gaierror("no such name")

    monkeypatch.setattr(outbound.socket, "getaddrinfo", missing)
    with pytest.raises(outbound.NotFound):
        outbound.check_url("https://nowhere.example/")


def test_a_name_that_looks_up_differently_the_second_time_gains_nothing(monkeypatch):
    """DNS rebinding: the check sees a public address, the connection would go to a private one."""
    calls = fake_lookup(monkeypatch, "93.184.216.34", "127.0.0.1")
    with pytest.raises(outbound.OutboundRefused, match="private or reserved"):
        get("http://rebind.example/latest/meta-data/")
    assert len(calls) == 2  # checked again when connecting, on the address actually used


def test_no_proxy_from_the_environment_is_used(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:3128")
    handlers = outbound.opener(allow_private=False).handlers
    proxies = [h for h in handlers if isinstance(h, urllib.request.ProxyHandler)]
    assert all(h.proxies == {} for h in proxies)  # none from the environment (an empty one is not kept)


def test_the_push_session_follows_no_redirect_and_ignores_proxies():
    session = outbound.requests_session()
    assert session.max_redirects == 0 and session.trust_env is False


def test_plainly_private_addresses_are_told_without_a_lookup():
    for url in ("https://localhost/x", "https://a.localhost/", "https://10.0.0.1/", "https://[::1]/",
                "https://169.254.169.254/latest/"):  # fmt: skip
        assert outbound.plainly_private(url), url
    for url in ("https://tool.example/jwks", "https://93.184.216.34/"):
        assert not outbound.plainly_private(url), url


def test_the_sibling_client_does_not_follow_a_redirect_with_its_key(server, settings):
    from integration.client import IntegrationError, call

    settings.OUTBOUND_PRIVATE_HOSTS = ["127.0.0.1"]
    with pytest.raises(IntegrationError) as refused:
        call(server, "k" * 40, "/moved")
    assert refused.value.status == 302
    assert Handler.seen == [("/moved", f"Api-Key {'k' * 40}")]
    assert call(server, "k" * 40, "/staff") == {"ok": True}
    settings.OUTBOUND_PRIVATE_HOSTS = []
    with pytest.raises(IntegrationError, match="not called"):
        call(server, "k" * 40, "/staff")


def test_a_tools_key_set_may_not_be_on_a_private_network(monkeypatch):
    from lti import api, keys

    fake_lookup(monkeypatch, "10.0.0.7")
    with pytest.raises(ValueError, match="private or reserved"):
        keys.fetch_json("https://tool.internal.example/jwks")
    with pytest.raises(ValueError, match="https"):
        keys.fetch_json("http://tool.example/jwks")
    serializer = api.ToolSerializer()
    with pytest.raises(api.serializers.ValidationError):
        serializer.validate_jwks_url("https://169.254.169.254/latest/meta-data/")
    assert serializer.validate_jwks_url("https://tool.example/jwks") == "https://tool.example/jwks"


def test_the_ai_model_is_reached_without_following_redirects(server, settings):
    from assist.providers import OllamaProvider, ProviderError

    settings.OUTBOUND_PRIVATE_HOSTS = []
    with pytest.raises(ProviderError):
        OllamaProvider(server, "llama3.1:8b", 5).generate("Hello")
    assert Handler.seen == []  # refused before anything was sent: the host was not named
