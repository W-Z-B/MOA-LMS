# The early-alert rules GSA starts with (item 6.05). Course administrators change the thresholds.

from django.db import migrations

RULES = (("missed_work", 2, 28), ("falling_marks", 15, 28), ("no_visits", 14, 0))


def add_rules(apps, schema_editor):
    AlertRule = apps.get_model("insights", "AlertRule")
    for kind, threshold, window in RULES:
        AlertRule.objects.get_or_create(kind=kind, defaults={"threshold": threshold, "window_days": window})


class Migration(migrations.Migration):

    dependencies = [
        ("insights", "0001_initial"),
    ]

    operations = [migrations.RunPython(add_rules, migrations.RunPython.noop)]
