"""seed_load: the fictional class of the load test (item 7.08)."""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from courses.models import CourseSite, Membership
from iam.models import TotpDevice
from quizzes.models import Quiz


@pytest.mark.django_db
def test_seed_load_makes_a_class_and_a_quiz_open_now(monkeypatch):
    with pytest.raises(CommandError):
        call_command("seed_load", "--students", "3")  # --fictional is required
    monkeypatch.setenv("LOAD_USER_PASSWORD", "short")
    with pytest.raises(CommandError):
        call_command("seed_load", "--fictional")
    monkeypatch.setenv("LOAD_USER_PASSWORD", "load-test-only-password")
    monkeypatch.setenv("LOAD_TOTP_SECRET", "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP")
    for _ in range(2):  # idempotent
        call_command("seed_load", "--fictional", "--students", "3", "--questions", "4", verbosity=0)
    site = CourseSite.objects.get(code="LOAD101-2026-27-S1-MRP")
    assert Membership.objects.filter(site=site, role="student").count() == 3
    quiz = Quiz.objects.get(site=site)
    assert quiz.is_published and quiz.slots.count() == 4 and site.modules.count() == 4
    assert TotpDevice.objects.filter(user__username="load.lecturer").exists()
