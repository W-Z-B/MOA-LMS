"""Serving a package's files to the player (items 5.12, 5.13).

The web app shows a package in a sandboxed frame, opened at /api/play/<token>/<entry>. The token is signed by
the LMS, names one attempt, and lasts PACKAGE_PLAY_HOURS; the frame needs no cookie, because a sandboxed page
has an origin of its own and the browser does not send the LMS's cookies with its requests.

Every response:
- is an entry of that package's zip, found by its exact name (archive.clean_name), never a path on the disk;
- carries a Content-Security-Policy with "sandbox" (no allow-same-origin): whatever the package's scripts do,
  they run in an origin of their own and cannot read the LMS's pages, cookies or storage, nor call its API
  as the learner. They may load only the package's own files and the players the web app serves;
- may be framed only by the LMS itself (frame-ancestors 'self'), and sends no Referer, so the token never
  leaves in an address;
- is readable from the sandboxed page (Access-Control-Allow-Origin: *), which H5P needs to load its files.

SCORM pages get two scripts added at the top of their head: scorm-again's cross-frame client and a few lines
that make it the page's SCORM API (window.API and window.API_1484_11). Calls go to the web app around the
frame by postMessage, where scorm-again's run-time keeps the data and commits it to the LMS as the learner.
An H5P file is opened with a small page of the LMS's own that runs h5p-standalone.
"""

import html
import json
import mimetypes
import posixpath
import re
import zipfile

from django.conf import settings
from django.core import signing
from django.http import HttpResponse, StreamingHttpResponse
from django.views.decorators.http import require_GET

from packages import archive
from packages.models import ContentPackage, PackageAttempt

SALT = "packages.play"
HTML_TYPES = {".html", ".htm", ".xhtml"}
MAX_INJECTED_BYTES = 8 * 1024 * 1024
TYPES = {
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".xml": "application/xml",
    ".xsd": "application/xml",
    ".dtd": "application/xml-dtd",
    ".svg": "image/svg+xml",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".vtt": "text/vtt",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".txt": "text/plain",
    ".pdf": "application/pdf",
}
SAFE_PREFIXES = ("text/", "image/", "audio/", "video/", "font/", "application/")
# The players are files the web app serves (web/vite.config.ts copies them from their npm packages).
PLAYERS = "/players"
SANDBOX = (
    "sandbox allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox allow-modals "
    "allow-downloads; default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' data: blob:; "
    "font-src 'self' data:; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'self'; "
    "form-action 'none'; frame-ancestors 'self'"
)
_HEAD = re.compile(rb"<head(\s[^>]*)?>", re.IGNORECASE)
_HTML = re.compile(rb"<html(\s[^>]*)?>", re.IGNORECASE)


def token_for(attempt: PackageAttempt) -> str:
    return signing.dumps([attempt.pk, attempt.package_id], salt=SALT, compress=False)


def play_url(attempt: PackageAttempt, sco: dict) -> str:
    base = f"/api/play/{token_for(attempt)}/"
    if attempt.package.standard == ContentPackage.Standard.H5P:
        return base
    query = f"?{sco['parameters']}" if sco.get("parameters") else ""
    return f"{base}{sco['href']}{query}"


def _attempt(token: str) -> PackageAttempt | None:
    try:
        attempt_id, package_id = signing.loads(token, salt=SALT, max_age=settings.PACKAGE_PLAY_HOURS * 3600)
    except (signing.BadSignature, ValueError, TypeError):
        return None
    return (
        PackageAttempt.objects.select_related("package__item")
        .filter(pk=attempt_id, package_id=package_id)
        .first()
    )


def _secure(response, content_type: str):
    response["Content-Type"] = content_type
    response["Content-Security-Policy"] = SANDBOX
    response["X-Content-Type-Options"] = "nosniff"
    response["Referrer-Policy"] = "no-referrer"
    response["Access-Control-Allow-Origin"] = "*"
    response["Cache-Control"] = "private, max-age=3600"
    response["X-Frame-Options"] = "SAMEORIGIN"
    return response


def _refused(status: int, words: str):
    response = HttpResponse(words, status=status)
    _secure(response, "text/plain; charset=utf-8")
    response["Cache-Control"] = "no-store"
    return response


def _origin(request) -> str:
    return f"{request.scheme}://{request.get_host()}"


def scorm_scripts(request) -> bytes:
    origin = html.escape(_origin(request), quote=True)
    return (
        f'<script src="{PLAYERS}/scorm-again/cross-frame-api.min.js"></script>'
        f'<script src="{PLAYERS}/gsa-scorm-frame.js" data-lms-origin="{origin}"></script>'
    ).encode()


def inject(page: bytes, scripts: bytes) -> bytes:
    """Put the scripts first in the page's head, so the SCORM API exists before the package looks for it."""
    for pattern in (_HEAD, _HTML):
        found = pattern.search(page)
        if found:
            return page[: found.end()] + scripts + page[found.end() :]
    return scripts + page


def h5p_page(request, attempt: PackageAttempt) -> bytes:
    from packages.services import activity_iri

    data = {
        "jsonPath": request.path.rstrip("/"),
        "lmsOrigin": _origin(request),
        "activity": activity_iri(attempt.package),
        "players": PLAYERS,
    }
    title = html.escape(attempt.package.item.title)
    return (
        '<!doctype html><html lang="en-GB"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{title}</title>"
        f'<link rel="stylesheet" href="{PLAYERS}/h5p/styles/h5p.css">'
        f'<script src="{PLAYERS}/h5p/main.bundle.js"></script>'
        f'<script src="{PLAYERS}/gsa-h5p-frame.js" data-config="{html.escape(json.dumps(data), quote=True)}">'
        '</script></head><body><div id="h5p-container"></div></body></html>'
    ).encode()


class _Entry:
    """A zip entry read in pieces, closing the zip and its stored file when the response is done."""

    def __init__(self, stored, zipped: zipfile.ZipFile, info: zipfile.ZipInfo):
        self.stored, self.zipped = stored, zipped
        self.handle = zipped.open(info)

    def __iter__(self):
        while chunk := self.handle.read(64 * 1024):
            yield chunk

    def close(self):
        for thing in (self.handle, self.zipped, self.stored):
            try:
                thing.close()
            except Exception:  # noqa: BLE001, S110 - closing what is already closed
                pass


def content_type(name: str) -> str:
    extension = posixpath.splitext(name)[1].lower()
    if extension in HTML_TYPES:
        return "text/html; charset=utf-8"
    kind = TYPES.get(extension) or mimetypes.guess_type(name)[0] or "application/octet-stream"
    if not kind.startswith(SAFE_PREFIXES):
        kind = "application/octet-stream"
    return kind


@require_GET
def play(request, token: str, entry: str = ""):
    attempt = _attempt(token)
    if attempt is None:
        return _refused(404, "This link to the package has run out. Open the package again from the course.")
    item = attempt.package.item
    if attempt.package.standard == ContentPackage.Standard.H5P and entry == "":
        return _secure(HttpResponse(h5p_page(request, attempt)), "text/html; charset=utf-8")
    name = archive.clean_name(entry)
    if name is None or not item.file:
        return _refused(404, "Not in this package.")
    stored = item.file.open("rb")
    try:
        zipped = zipfile.ZipFile(stored)
        info = zipped.getinfo(name)
    except (KeyError, zipfile.BadZipFile, OSError):
        stored.close()
        return _refused(404, "Not in this package.")
    if info.is_dir():
        stored.close()
        return _refused(404, "Not in this package.")
    kind = content_type(name)
    if attempt.package.standard != ContentPackage.Standard.H5P and kind.startswith("text/html"):
        try:
            page = archive.read(zipped, info, limit=MAX_INJECTED_BYTES)
        except archive.PackageRefused:
            return _refused(404, "This page of the package cannot be shown.")
        finally:
            zipped.close()
            stored.close()
        return _secure(HttpResponse(inject(page, scorm_scripts(request))), kind)
    response = StreamingHttpResponse(_Entry(stored, zipped, info))
    response["Content-Length"] = str(info.file_size)
    if kind == "application/octet-stream":
        response["Content-Disposition"] = "attachment"
    return _secure(response, kind)
