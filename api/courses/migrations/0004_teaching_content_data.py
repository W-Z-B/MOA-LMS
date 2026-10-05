"""Existing content under the new rules (items 2.12, 2.17, 2.19, 2.20).

Page bodies were plain text: each becomes escaped HTML paragraphs, so it reads exactly as before.
Files and links put up before licences were recorded are marked "not yet known" for their lecturer to
settle; pages are GSA's own. File sizes are read from the store for the storage allowance. The GSA
standard layout is added as the default course template.
"""

from django.db import migrations

from courses.richtext import text_to_html
from courses.site_templates import gsa_standard


def forwards(apps, schema_editor):
    ContentItem = apps.get_model("courses", "ContentItem")
    SiteTemplate = apps.get_model("courses", "SiteTemplate")
    for item in ContentItem.objects.exclude(body=""):
        item.body = text_to_html(item.body)
        item.save(update_fields=["body"])
    ContentItem.objects.filter(kind__in=["file", "link"]).update(licence="unknown")
    for item in ContentItem.objects.exclude(file=""):
        try:
            item.file_size = item.file.size
        except (FileNotFoundError, OSError):
            continue
        item.save(update_fields=["file_size"])
    SiteTemplate.objects.get_or_create(
        name="GSA standard layout",
        defaults={
            "description": "Course overview, course outline, one module for each teaching week, and "
            "assessment. Pages come in as drafts for the lecturer to fill in.",
            "structure": gsa_standard(),
            "is_default": True,
        },
    )


class Migration(migrations.Migration):
    dependencies = [("courses", "0003_teaching_content")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
