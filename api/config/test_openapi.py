import os

from django.core.management import call_command


def test_openapi_schema_validates_without_warnings():
    """The generated OpenAPI 3.1 document must validate and describe every endpoint.

    fail_on_warn turns a view the generator cannot describe (an untyped field, a function view with no
    schema, an unknown authentication scheme) into a failure, so the published API documentation stays
    complete.
    """
    call_command("spectacular", validate=True, fail_on_warn=True, file=os.devnull)
