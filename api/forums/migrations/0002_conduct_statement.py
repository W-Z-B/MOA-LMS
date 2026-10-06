"""Publish the first conduct statement (item 4.09), so that forums and messages open with rules in force.
GSA confirms or replaces it by publishing a new version (forums.conduct_text)."""

from django.db import migrations
from django.utils import timezone


def publish(apps, schema_editor):
    from forums.conduct_text import BODY

    ConductStatement = apps.get_model("forums", "ConductStatement")
    if not ConductStatement.objects.exists():
        ConductStatement.objects.create(version=1, body=BODY, published_at=timezone.now())


class Migration(migrations.Migration):
    dependencies = [("forums", "0001_initial")]

    operations = [migrations.RunPython(publish, migrations.RunPython.noop)]
