"""HTTP client for sibling systems. Standard library only, so the ecosystem adds no dependency."""

import json
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings


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
        with urllib.request.urlopen(request, timeout=settings.INTEGRATION_TIMEOUT_SECONDS) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        raise IntegrationError(f"{url} answered HTTP {exc.code}", status=exc.code) from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise IntegrationError(f"{url} could not be reached: {exc}") from exc


def pages(base_url: str, key: str, path: str, *, params: dict | None = None):
    """Yield every row of a paginated list endpoint."""
    payload = call(base_url, key, path, params=params)
    while True:
        yield from payload.get("results", [])
        if not payload.get("next"):
            return
        payload = call(base_url, key, payload["next"])
