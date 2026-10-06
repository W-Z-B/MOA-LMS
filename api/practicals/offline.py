"""Writes from a phone's offline queue (item 3.15).

A phone in the field records an observation or a logbook entry without signal and sends it when it
reconnects; if the answer is lost on the way it sends it again. Two rules make that safe:

- Every write takes a client-made key (a UUID) in the Idempotency-Key header, or as `idempotency_key` in
  the body. The first successful write under a key is kept with its answer; the same request sent again
  under the same key gets that answer back (with the header Idempotent-Replay: true) and changes nothing.
  The same key on a different request is refused, so a phone cannot mix two records up.
- The phone's own time is kept beside the server's, and refused when it cannot be right: more than 7 days
  old (the record waited too long; it should be entered again with the lecturer) or more than 10 minutes in
  the future (the phone's clock is wrong).
"""

import hashlib
import json
import uuid
from datetime import timedelta
from functools import wraps

from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.request import Request
from rest_framework.response import Response

from practicals.models import IdempotencyKey

MAX_AGE = timedelta(days=7)
MAX_AHEAD = timedelta(minutes=10)
HEADER = "HTTP_IDEMPOTENCY_KEY"
BODY_FIELD = "idempotency_key"

IDEMPOTENCY_HEADER = OpenApiParameter(
    "Idempotency-Key",
    OpenApiTypes.UUID,
    OpenApiParameter.HEADER,
    required=False,
    description="A UUID made on the phone for this one record. Sending the same request again under the "
    "same key returns the first answer and changes nothing. May also be sent as `idempotency_key` in the "
    "body.",
)


class ClientTimeRefused(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "client_time_refused"


class KeyRefused(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "idempotency_key_reused"


class BadKey(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "invalid_idempotency_key"


def check_client_time(value, *, now=None):
    """The phone's time for a record, or a refusal that says why it cannot be accepted."""
    if value is None:
        return value
    now = now or timezone.now()
    if value < now - MAX_AGE:
        raise ClientTimeRefused(
            f"This was recorded on the phone on {timezone.localtime(value):%d/%m/%Y at %H:%M}, more "
            "than 7 days "
            "ago. Records older than 7 days are not accepted from the phone; enter it again with the "
            "lecturer.",
            code="client_time_too_old",
        )
    if value > now + MAX_AHEAD:
        raise ClientTimeRefused(
            "The phone's clock is more than 10 minutes ahead of the school's. Set the phone's date and time "
            "correctly, then send it again.",
            code="client_time_in_future",
        )
    return value


def _key_of(request: Request) -> uuid.UUID | None:
    raw = request.META.get(HEADER)
    if not raw and hasattr(request.data, "get"):
        raw = request.data.get(BODY_FIELD)
    if not raw:
        return None
    try:
        return uuid.UUID(str(raw))
    except ValueError:
        raise BadKey("The idempotency key must be a UUID made on the phone.") from None


def _fingerprint(request: Request) -> str:
    data = request.data
    if hasattr(data, "lists"):  # a form or multipart body: every value of every field
        data = {name: values for name, values in data.lists()}
    data = {k: v for k, v in dict(data).items() if k != BODY_FIELD}
    files = {name: [(f.name, f.size) for f in request.FILES.getlist(name)] for name in request.FILES}
    body = json.dumps({"data": data, "files": files}, sort_keys=True, cls=DjangoJSONEncoder, default=str)
    return hashlib.sha256(body.encode()).hexdigest()


def run_idempotent(request: Request, perform):
    """Run perform() once per key; replay the kept answer for the same request sent again."""
    if getattr(request, "_idempotency_checked", False):  # an inner call (partial_update calls update)
        return perform()
    request._idempotency_checked = True
    key = _key_of(request)
    if key is None:
        return perform()
    fingerprint = _fingerprint(request)
    with transaction.atomic():
        done = IdempotencyKey.objects.filter(user=request.user, key=key).first()
        if done is not None:
            if (done.method, done.path, done.fingerprint) != (request.method, request.path, fingerprint):
                raise KeyRefused(
                    "This idempotency key was already used for a different record. Make a new key for each "
                    "new record."
                )
            replay = Response(done.response, status=done.status_code)
            replay["Idempotent-Replay"] = "true"
            return replay
        response = perform()
        if 200 <= response.status_code < 300:
            try:
                with transaction.atomic():
                    IdempotencyKey.objects.create(
                        user=request.user,
                        key=key,
                        method=request.method,
                        path=request.path[:300],
                        fingerprint=fingerprint,
                        status_code=response.status_code,
                        response=getattr(response, "data", None),
                    )
            except IntegrityError:
                # The same request arrived twice at once and the other copy finished first: undo this one.
                raise KeyRefused(
                    "The same record is being saved already. Send it again in a moment.", code="in_progress"
                ) from None
        return response


def idempotent(view):
    """Decorator for a view function or a view method: the request is the first Request among its args."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        request = next(a for a in args if isinstance(a, Request))
        return run_idempotent(request, lambda: view(*args, **kwargs))

    return wrapper


class IdempotentWrites:
    """Viewset mixin: create, update and destroy each honour the idempotency key."""

    @idempotent
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @idempotent
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @idempotent
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    @idempotent
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)
