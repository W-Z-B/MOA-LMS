"""Every request the server itself sends out (ASVS 5.2.6, 12.6.1: server-side request forgery).

One way out for all of them: the sibling systems' client (integration.client), tools' key sets (lti.keys),
the AI model (assist.providers) and push notices (notifications.push). Two rules hold for every one:

- **No redirects.** An answer of 3xx is refused, never followed: a redirect could lead the request, with
  its service key, to another host, or from https to http.
- **No private addresses from data.** An address that comes from data (a tool's key set address that a
  course administrator typed, a push endpoint that a browser gave) may not reach a private, loopback,
  link-local (169.254.169.254, the cloud metadata service, among them), multicast or reserved address.
  The check is made on the address actually connected to, after the name is looked up, so a name that
  looks up differently the second time (DNS rebinding) gains nothing.

The sibling systems and the AI model are on GSA's private network by design, at addresses the operator
sets in the environment (HRMS_API_URL, SRMS_API_URL, AI_OLLAMA_URL). Those calls pass `configured=True`,
and a private address is then allowed only for a host named in OUTBOUND_PRIVATE_HOSTS, which defaults to
the hosts of those three settings; nothing a person types can add to it.

Proxies from the environment (HTTP_PROXY and the like) are not used: every connection goes direct, so the
address checked is the address reached.
"""

import http.client
import ipaddress
import socket
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from django.conf import settings


class OutboundRefused(ValueError):
    """The address may not be fetched: a private network reached from data, a redirect, or a bad scheme."""


class NotFound(OutboundRefused):
    """The name could not be looked up (perhaps only for now)."""


def _public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def private_allowed(host: str) -> bool:
    """Whether the operator named this host as one on the private network (OUTBOUND_PRIVATE_HOSTS)."""
    return (host or "").lower().rstrip(".") in {
        h.lower().rstrip(".") for h in settings.OUTBOUND_PRIVATE_HOSTS
    }


def plainly_private(url: str) -> bool:
    """Whether an address names a private place outright (localhost, or a private IP address), so a form
    can refuse it at once; names are looked up, and checked again, only when the address is fetched."""
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return not _public(host)
    except ValueError:
        return False  # a name, not an address


def resolve(host: str, port: int, *, allow_private: bool) -> list[tuple]:
    """The addresses for host:port that may be connected to, or OutboundRefused."""
    try:
        found = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError) as error:
        raise NotFound(f"{host} could not be found.") from error
    if not allow_private:
        refused = [info[4][0] for info in found if not _public(info[4][0])]
        if refused:
            raise OutboundRefused(f"{host} is on a private or reserved network ({refused[0]}); not fetched.")
    return found


def check_url(url: str, *, configured: bool = False, schemes=("https",)) -> str:
    """Refuse an address before anything is sent: its scheme, and (from data) a private network."""
    parts = urlsplit(url)
    if parts.scheme not in schemes or not parts.hostname:
        raise OutboundRefused(f"Only {' or '.join(schemes)} addresses are fetched.")
    if parts.username or parts.password:
        raise OutboundRefused("An address with a name or password in it is not fetched.")
    allow = configured and private_allowed(parts.hostname)
    resolve(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80), allow_private=allow)
    return url


def _connector(allow_private: bool):
    def create_connection(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None, **_kw):
        host, port = address
        last = None
        for family, kind, proto, _name, target in resolve(host, port, allow_private=allow_private):
            sock = socket.socket(family, kind, proto)
            try:
                if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
                    sock.settimeout(timeout)
                if source_address:
                    sock.bind(source_address)
                sock.connect(target)  # the very address that was checked
                return sock
            except OSError as error:
                last = error
                sock.close()
        raise last or OSError(f"{host} could not be reached")

    return create_connection


class _GuardedHTTP(http.client.HTTPConnection):
    allow_private = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _connector(self.allow_private)


class _GuardedHTTPS(http.client.HTTPSConnection):
    allow_private = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _connector(self.allow_private)


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, f"redirect to {newurl} refused", headers, fp)


def opener(*, allow_private: bool) -> urllib.request.OpenerDirector:
    """A urllib opener that connects only to checked addresses, follows no redirect and uses no proxy."""
    http_class = type("GuardedHTTP", (_GuardedHTTP,), {"allow_private": allow_private})
    https_class = type("GuardedHTTPS", (_GuardedHTTPS,), {"allow_private": allow_private})

    class HTTPHandler(urllib.request.HTTPHandler):
        def http_open(self, req):
            return self.do_open(http_class, req)

    class HTTPSHandler(urllib.request.HTTPSHandler):
        def https_open(self, req):
            return self.do_open(https_class, req, context=self._context)

    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}), HTTPHandler(), HTTPSHandler(), _NoRedirects()
    )


def urlopen(request: urllib.request.Request, *, timeout: float, configured: bool = False, schemes=("https",)):
    """Send a request the guarded way. `configured=True` only for an address the operator set in the
    environment; anything that comes from data leaves it False. Raises OutboundRefused, or urllib's errors
    (HTTPError for a refused redirect, URLError when the connection is refused by the guard)."""
    check_url(request.full_url, configured=configured, schemes=schemes)
    allow = configured and private_allowed(urlsplit(request.full_url).hostname or "")
    try:
        return opener(allow_private=allow).open(request, timeout=timeout)
    except urllib.error.URLError as error:
        if isinstance(error.reason, OutboundRefused):
            raise error.reason from error
        raise


def requests_session():
    """A requests session for libraries that take one (pywebpush): no redirects, no proxies. The address is
    checked with check_url before it is used."""
    import requests

    session = requests.Session()
    session.max_redirects = 0
    session.trust_env = False
    return session
