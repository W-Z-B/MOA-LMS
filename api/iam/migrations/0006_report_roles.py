# The roles that read reports (items 6.03, 6.04): heads of department, scoped by unit, and the Registrar.

from django.db import migrations, models

NEW = (("head_of_department", "Head of Department"), ("registrar", "Registrar"))


def add_roles(apps, schema_editor):
    Role = apps.get_model("iam", "Role")
    for code, name in NEW:
        Role.objects.update_or_create(code=code, defaults={"name": name})


def remove_roles(apps, schema_editor):
    apps.get_model("iam", "Role").objects.filter(code__in=[code for code, _ in NEW], scopes__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("iam", "0005_email_change"),
    ]

    operations = [
        migrations.AlterField(
            model_name="role",
            name="code",
            field=models.CharField(
                choices=[
                    ("administrator", "System Administrator"),
                    ("course_admin", "Course Administrator"),
                    ("lecturer", "Lecturer or Instructor"),
                    ("student", "Student"),
                    ("auditor", "Auditor"),
                    ("dpo", "Data Protection Officer"),
                    ("head_of_department", "Head of Department"),
                    ("registrar", "Registrar"),
                ],
                max_length=40,
                unique=True,
            ),
        ),
        migrations.RunPython(add_roles, remove_roles),
    ]
