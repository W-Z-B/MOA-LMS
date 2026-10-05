import pytest
from django.core.exceptions import ImproperlyConfigured

from core import crypto


def test_encrypt_decrypt_round_trip():
    token = crypto.encrypt("JBSWY3DPEHPK3PXP")
    assert token != b"JBSWY3DPEHPK3PXP"
    assert crypto.decrypt(token) == "JBSWY3DPEHPK3PXP"


def test_missing_key_is_a_configuration_error(settings):
    settings.FIELD_ENCRYPTION_KEY = ""
    crypto._fernet.cache_clear()
    with pytest.raises(ImproperlyConfigured):
        crypto.encrypt("x")
    crypto._fernet.cache_clear()


@pytest.mark.django_db
def test_seed_is_idempotent(seeded):
    from django.core.management import call_command

    from iam.models import Role
    from integration.models import CampusRef

    before = (Role.objects.count(), CampusRef.objects.count())
    call_command("seed", "--country", "GY", verbosity=0)
    assert (Role.objects.count(), CampusRef.objects.count()) == before == (6, 2)
