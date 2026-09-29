"""Model field that stores text encrypted at rest and returns plain text in Python."""

from django import forms
from django.db import models

from core.crypto import decrypt, encrypt


class EncryptedTextField(models.BinaryField):
    """A text value encrypted with the application key before it reaches the database.

    Reads return the decrypted string. Writes accept a string. Values are stored as bytes,
    so they cannot be filtered or ordered on in SQL; look-ups use other columns.
    """

    description = "Text encrypted at rest with the application key"

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("editable", True)
        super().__init__(*args, **kwargs)

    def from_db_value(self, value, expression, connection):
        if value is None:
            return None
        return decrypt(bytes(value))

    def to_python(self, value):
        if value is None or isinstance(value, str):
            return value
        return decrypt(bytes(value))

    def get_prep_value(self, value):
        if value is None or value == "":
            return None
        if isinstance(value, bytes | memoryview):
            return bytes(value)
        return encrypt(str(value))

    def value_to_string(self, obj):
        return self.value_from_object(obj) or ""

    def formfield(self, **kwargs):
        defaults = {"form_class": forms.CharField, "max_length": 255}
        defaults.update(kwargs)
        return models.Field.formfield(self, **defaults)
