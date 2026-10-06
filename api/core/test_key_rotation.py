"""Changing the field encryption key (ASVS 1.6.3, 6.2.4): a list of keys, rotate_field_key, and an audit chain
that still verifies the entries sealed under the old key (core.crypto, audit.chain)."""

from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.db import connection

from audit import chain
from audit.models import AuditLog
from core import crypto
from iam.models import TotpDevice

OLD, NEW = "test-only-key", "a-brand-new-key"


def use_keys(settings, keys, retired=()):
    settings.FIELD_ENCRYPTION_KEYS = list(keys)
    settings.AUDIT_CHAIN_RETIRED_KEYS = list(retired)
    crypto._fernet.cache_clear()


def stored_token(device) -> bytes:
    with connection.cursor() as cursor:
        cursor.execute("SELECT secret FROM iam_totpdevice WHERE id = %s", [device.pk])
        return bytes(cursor.fetchone()[0])


@pytest.mark.django_db
def test_the_key_is_changed_without_losing_a_value_or_the_audit_chain(settings, make_user):
    use_keys(settings, [OLD])
    device = TotpDevice.objects.create(user=make_user("asha"), secret="JBSWY3DPEHPK3PXP")
    AuditLog.objects.create(action="test", entity="core.before")  # sealed under the old key
    assert crypto.is_current(stored_token(device))

    # 1. The new key first, the old one after: old values still open, new ones use the new key.
    use_keys(settings, [NEW, OLD])
    assert TotpDevice.objects.get(pk=device.pk).secret == "JBSWY3DPEHPK3PXP"
    assert not crypto.is_current(stored_token(device))
    later = TotpDevice.objects.create(user=make_user("ravi"), secret="KRSXG5CT" + "MVRXEZLU")
    assert crypto.is_current(stored_token(later))
    out = StringIO()
    call_command("rotate_field_key", "--check", stdout=out)
    assert "iam.totpdevice.secret: 1" in out.getvalue() and "1 value(s) still on an old key" in out.getvalue()
    assert not crypto.is_current(stored_token(device))  # --check changes nothing

    # 2. Every value encrypted again with the new key, recorded in the audit log without any value.
    call_command("rotate_field_key", stdout=StringIO())
    assert crypto.is_current(stored_token(device))
    entry = AuditLog.objects.get(action="field_key_rotated")
    assert entry.after == {"re_encrypted": {"iam.totpdevice.secret": 1}, "keys_in_use": 2}
    assert "JBSWY3" not in str(entry.after)
    out = StringIO()
    call_command("rotate_field_key", "--check", stdout=out)
    assert "0 value(s)" in out.getvalue()

    # 3. The old key leaves the list: values open with the new key alone, and the chain still verifies with
    #    the old key kept for that only.
    use_keys(settings, [NEW], retired=[OLD])
    assert TotpDevice.objects.get(pk=device.pk).secret == "JBSWY3DPEHPK3PXP"
    AuditLog.objects.create(action="test", entity="core.after")
    assert chain.verify().intact

    # Without the retired key, the entries sealed before the change can no longer be checked.
    use_keys(settings, [NEW])
    first = AuditLog.objects.order_by("id").first()
    assert chain.walk()[3] == first.id


@pytest.mark.django_db
def test_a_retired_key_cannot_seal_entries_written_after_the_change(settings):
    """Whoever still holds the old key cannot add an entry after newer ones: keys only get newer."""
    use_keys(settings, [OLD])
    AuditLog.objects.create(action="test", entity="core.one")
    use_keys(settings, [NEW, OLD])
    AuditLog.objects.create(action="test", entity="core.two")
    use_keys(settings, [OLD])  # someone with the old key writes a row
    forged = AuditLog.objects.create(action="test", entity="core.forged")
    use_keys(settings, [NEW], retired=[OLD])
    assert chain.walk()[3] == forged.id
    assert not chain.verify().intact


@pytest.mark.django_db
def test_a_value_no_key_opens_stops_the_command(settings, make_user):
    use_keys(settings, ["a-key-that-is-gone"])
    TotpDevice.objects.create(user=make_user("devi"), secret="JBSWY3DPEHPK3PXP")
    use_keys(settings, [NEW])
    with pytest.raises(CommandError, match="opens with none of the keys"):
        call_command("rotate_field_key", stdout=StringIO())


def test_one_key_or_a_list(settings):
    settings.FIELD_ENCRYPTION_KEYS = []
    settings.FIELD_ENCRYPTION_KEY = "single"
    assert crypto.keys() == ["single"] and crypto.current_key() == "single"
    settings.FIELD_ENCRYPTION_KEYS = "first, second"
    assert crypto.keys() == ["first", "second"] and crypto.current_key() == "first"
    settings.AUDIT_CHAIN_RETIRED_KEYS = ["second", "third"]
    assert len(crypto.chain_keys()) == 3  # each key once
    settings.FIELD_ENCRYPTION_KEYS, settings.FIELD_ENCRYPTION_KEY, settings.AUDIT_CHAIN_RETIRED_KEYS = (
        [],
        "",
        [],
    )
    with pytest.raises(Exception, match="not set"):
        crypto.chain_keys()
    with pytest.raises(CommandError, match="not set"):
        call_command("rotate_field_key", stdout=StringIO())
    crypto._fernet.cache_clear()
