"""One shape for every refusal: {"code": ..., "detail": ...}.

Views already answer that way. Errors raised by the framework itself (not signed in, no permission,
not found, too many requests) carried only "detail"; this adds the code, so the web app can tell "your
session ended" from "you may not do that" without reading sentences. Field validation errors keep their
per-field shape.
"""

from collections import Counter

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.db.models import ProtectedError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler


def still_held(objects) -> str:
    """Why a record cannot go, counted kind by kind: "1 submission and 2 marks still refer to it"."""
    counts = Counter(obj._meta for obj in objects)
    parts = sorted(
        f"{n} {meta.verbose_name if n == 1 else meta.verbose_name_plural}" for meta, n in counts.items()
    )
    if not parts:
        return "It cannot be removed while other records still refer to it."
    listed = parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"
    verb = "refers" if sum(counts.values()) == 1 else "refer"
    return f"It cannot be removed while {listed} still {verb} to it."


def api_exception_handler(exc, context):
    if isinstance(exc, ProtectedError):
        # Removing a record others still point to, such as a person with submissions: say so, not a 500.
        return Response(
            {"code": "in_use", "detail": still_held(exc.protected_objects)},
            status=status.HTTP_409_CONFLICT,
        )
    response = exception_handler(exc, context)
    if response is None or not isinstance(response.data, dict):
        return response
    # The framework turns Django's own errors into its equivalents only inside its handler; do the same
    # here so that their codes are known.
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()
    if "detail" in response.data and "code" not in response.data:
        codes = exc.get_codes() if hasattr(exc, "get_codes") else None
        response.data["code"] = codes if isinstance(codes, str) else getattr(exc, "default_code", "error")
    return response
