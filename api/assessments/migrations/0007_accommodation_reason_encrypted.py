"""An accommodation's reason, often a health matter, encrypted at rest (ASVS 6.1.2): copied into an encrypted
field, the plain one removed, and the new one given its name."""

from django.db import migrations

import core.fields


def encrypt_reasons(apps, schema_editor):
    Accommodation = apps.get_model("assessments", "Accommodation")
    for row in Accommodation.objects.exclude(reason=""):
        row.reason_encrypted = row.reason  # the field encrypts on save
        row.save(update_fields=["reason_encrypted"])


def decrypt_reasons(apps, schema_editor):
    Accommodation = apps.get_model("assessments", "Accommodation")
    for row in Accommodation.objects.exclude(reason_encrypted=None):
        row.reason = row.reason_encrypted or ""
        row.save(update_fields=["reason"])


class Migration(migrations.Migration):
    dependencies = [("assessments", "0006_first_attempts")]

    operations = [
        migrations.AddField(
            model_name="accommodation",
            name="reason_encrypted",
            field=core.fields.EncryptedTextField(blank=True, null=True),
        ),
        migrations.RunPython(encrypt_reasons, decrypt_reasons),
        migrations.RemoveField(model_name="accommodation", name="reason"),
        migrations.RenameField(model_name="accommodation", old_name="reason_encrypted", new_name="reason"),
        migrations.AlterField(
            model_name="accommodation",
            name="reason",
            field=core.fields.EncryptedTextField(
                blank=True, help_text="Why; seen only by course administrators", null=True
            ),
        ),
    ]
