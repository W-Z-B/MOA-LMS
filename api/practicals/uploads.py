"""Evidence from the field: photographs and scanned sheets, checked like every other upload (core.uploads).

Kept here rather than in core.uploads so the practicals module adds no change to that shared file; the
policy is built from the same UploadPolicy and validate_upload, and stored names are random in the same way.
"""

import uuid
from pathlib import PurePath

from django.utils import timezone

from core.uploads import UploadPolicy

# A photograph taken on a phone, or a PDF of a signed sheet. No Office files: evidence is a picture or a scan.
EVIDENCE = UploadPolicy(
    frozenset({"jpeg", "png", "webp", "heic", "pdf"}),
    "UPLOAD_LIMIT_EVIDENCE_MB",
    "a photograph (JPG, PNG, WEBP or HEIC) or a PDF",
)
MAX_PHOTOS_PER_REQUEST = 10


def evidence_name(instance, filename: str) -> str:
    """upload_to for practical evidence: practicals/<year>/<month>/<random>.<ext>."""
    extension = PurePath(filename).suffix.lower()[:10]
    now = timezone.now()
    return f"practicals/{now:%Y}/{now:%m}/{uuid.uuid4().hex}{extension}"
