"""The address a request really came from.

Caddy is the only way in from outside. It sets X-Real-IP to the client address it worked out itself
(`header_up X-Real-IP {client_ip}`, see deploy/), replacing anything the client sent. Without Caddy in
front (tests, or a sibling system calling the API on the private network) the socket address is used.

X-Forwarded-For is never read here: its left-most entry is whatever the client chose to write, so an
address taken from it could be forged in the audit log or used to slip past a rate limit.
"""

import ipaddress


def client_ip(request) -> str | None:
    meta = getattr(request, "META", None) or {}
    for value in (meta.get("HTTP_X_REAL_IP", ""), meta.get("REMOTE_ADDR", "")):
        value = (value or "").strip()
        if not value:
            continue
        try:
            return str(ipaddress.ip_address(value))
        except ValueError:
            continue
    return None
