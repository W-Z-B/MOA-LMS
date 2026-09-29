import os

from django.core.management import call_command


def test_openapi_schema_validates():
    """The generated OpenAPI 3.1 document must validate; a broken serializer or view breaks this."""
    call_command("spectacular", validate=True, file=os.devnull)
