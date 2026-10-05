"""Work handed in before submission history (item 2.21) becomes each submission's first attempt, with a
receipt, so every submission has a history from the start."""

import hashlib
import secrets

from django.db import migrations

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _receipt():
    body = "".join(secrets.choice(ALPHABET) for _ in range(10))
    return f"GSA-{body[:5]}-{body[5:]}"


def _file_sha(field) -> str:
    digest = hashlib.sha256()
    try:
        with field.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
    except (OSError, ValueError):
        return ""
    return digest.hexdigest()


def first_attempts(apps, schema_editor):
    Submission = apps.get_model("assessments", "Submission")
    Attempt = apps.get_model("assessments", "SubmissionAttempt")
    File = apps.get_model("assessments", "SubmissionFile")
    for submission in Submission.objects.filter(attempts__isnull=True):
        files = []
        if submission.file:
            name = submission.original_name or submission.file.name.rsplit("/", 1)[-1]
            files.append((name, _file_sha(submission.file)))
        digest = hashlib.sha256()
        digest.update(b"text\0" + submission.text.encode("utf-8") + b"\0")
        for name, sha in files:
            digest.update(b"file\0" + name.encode("utf-8") + b"\0" + sha.encode("ascii") + b"\0")
        attempt = Attempt.objects.create(
            submission=submission,
            number=1,
            submitted_by_id=submission.student_id,
            submitted_at=submission.submitted_at,
            text=submission.text,
            is_late=submission.is_late,
            receipt=_receipt(),
            content_hash=digest.hexdigest(),
        )
        for name, sha in files:
            File.objects.create(
                attempt=attempt, position=1, file=submission.file.name, original_name=name, sha256=sha
            )


class Migration(migrations.Migration):
    dependencies = [("assessments", "0004_marking_rubrics")]

    operations = [migrations.RunPython(first_attempts, migrations.RunPython.noop)]
