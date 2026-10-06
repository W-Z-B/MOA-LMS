"""HTTP client for sibling systems. Standard library only, so the ecosystem adds no dependency."""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

from core import outbound


class IntegrationError(Exception):
    """A sibling system could not be reached or refused the request."""

    def __init__(self, detail: str, status: int | None = None):
        super().__init__(detail)
        self.status = status


def call(base_url: str, key: str, path: str, *, params: dict | None = None, data: dict | None = None) -> dict:
    """GET (or POST when data is given) a JSON endpoint with the service key."""
    if not base_url or not key:
        raise IntegrationError("The sibling system is not configured (URL or key missing).")
    url = path if path.startswith("http") else f"{base_url.rstrip('/')}{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    if not url.startswith(("http://", "https://")):
        raise IntegrationError("Only http and https URLs are allowed.")
    body = json.dumps(data).encode("utf-8") if data is not None else None
    request = urllib.request.Request(url, data=body, method="POST" if body else "GET")  # noqa: S310 - scheme checked
    request.add_header("Authorization", f"Api-Key {key}")
    request.add_header("Accept", "application/json")
    if body:
        request.add_header("Content-Type", "application/json")
    try:
        # On GSA's private network by design (OUTBOUND_PRIVATE_HOSTS); a redirect is refused, never followed,
        # so the service key cannot be carried to another host (core.outbound).
        with outbound.urlopen(
            request, timeout=settings.INTEGRATION_TIMEOUT_SECONDS, configured=True, schemes=("http", "https")
        ) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except outbound.OutboundRefused as exc:
        raise IntegrationError(f"{url} was not called: {exc}") from exc
    except urllib.error.HTTPError as exc:
        raise IntegrationError(f"{url} answered HTTP {exc.code}", status=exc.code) from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise IntegrationError(f"{url} could not be reached: {exc}") from exc


def pages(base_url: str, key: str, path: str, *, params: dict | None = None):
    """Yield every row of a paginated list endpoint. A "next" link is followed only when it
    points back at the same system: the service key is never sent anywhere else (ASVS 5.2.6, 12.6.1)."""
    payload = call(base_url, key, path, params=params)
    origin = urllib.parse.urlsplit(base_url)
    while True:
        yield from payload.get("results", [])
        following = payload.get("next")
        if not following:
            return
        target = urllib.parse.urlsplit(following)
        if target.netloc and (target.scheme, target.netloc) != (origin.scheme, origin.netloc):
            raise IntegrationError(f"The next page is on another system ({target.netloc}); not followed.")
        payload = call(base_url, key, following)


def unreachable(exc: IntegrationError) -> bool:
    """Whether the failure was the network or the other system's fault (worth trying again), rather than
    the other system refusing this one request."""
    return exc.status is None or exc.status >= 500


def with_retries(send, *, sleep=time.sleep):
    """Run `send()`, trying again with a growing wait while the other system cannot be reached (item 1.23).

    A refusal (HTTP 4xx) is raised at once: sending it again would be refused again.
    """
    attempts = max(1, settings.INTEGRATION_ATTEMPTS)
    for attempt in range(1, attempts + 1):
        try:
            return send()
        except IntegrationError as exc:
            if not unreachable(exc) or attempt == attempts:
                raise
            sleep(settings.INTEGRATION_RETRY_SECONDS * 2 ** (attempt - 1))
    raise AssertionError("unreachable")  # pragma: no cover - the loop returns or raises
