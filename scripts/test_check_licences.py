"""The licence gate must refuse what the policy forbids, not only pass what it allows.

Run with:  python -m pytest -q -p no:django scripts
"""

from email.message import Message

import pytest
from check_licences import ALIASES, spdx_ok, verdict

POLICY = {
    "permissive": ["MIT", "BSD", "BSD-3-Clause", "Apache-2.0", "PSF-2.0"],
    "exceptions": {"python": {"psycopg": {"licence": "LGPL-3.0-only", "reason": "driver"}}, "npm": {}},
}
ALLOWED = set(POLICY["permissive"])


class FakeDist:
    def __init__(self, *, expression="", text="", classifiers=()):
        self.version = "1.0"
        self.metadata = Message()
        if expression:
            self.metadata["License-Expression"] = expression
        if text:
            self.metadata["License"] = text
        for classifier in classifiers:
            self.metadata["Classifier"] = f"License :: OSI Approved :: {classifier}"


@pytest.mark.parametrize(
    ("expression", "ok"),
    [
        ("MIT", True),
        ("Apache-2.0 OR BSD-3-Clause", True),
        ("Apache-2.0 OR GPL-2.0-only", True),
        ("MIT AND GPL-3.0-only", False),
        ("GPL-3.0-or-later", False),
        ("(MIT OR AGPL-3.0-only) AND LGPL-2.1-only", False),
        ("BSD 3-Clause OR Apache-2.0", True),
    ],
)
def test_spdx_expressions(expression, ok):
    assert spdx_ok(expression, ALLOWED) is ok


def test_copyleft_classifier_is_refused():
    ok, why = verdict("somelib", FakeDist(classifiers=["GNU General Public License v3 (GPLv3)"]), POLICY)
    assert not ok and why.startswith("copyleft")


def test_dual_permissive_classifiers_pass_but_a_copyleft_option_needs_review():
    assert verdict("dateutil", FakeDist(classifiers=["BSD License", "Apache Software License"]), POLICY)[0]
    assert not verdict(
        "mixed", FakeDist(classifiers=["MIT License", "Mozilla Public License 2.0 (MPL 2.0)"]), POLICY
    )[0]


def test_a_package_that_declares_nothing_is_refused():
    ok, why = verdict("mystery", FakeDist(), POLICY)
    assert not ok and "no licence declared" in why


def test_an_unrecognised_licence_is_refused():
    assert not verdict("odd", FakeDist(text="Business Source License 1.1"), POLICY)[0]


def test_named_exception_passes_with_its_reason():
    ok, why = verdict("psycopg", FakeDist(expression="LGPL-3.0-only"), POLICY)
    assert ok and "exception" in why


def test_free_text_expression_field_is_understood():
    assert verdict("uritemplate", FakeDist(text="BSD 3-Clause OR Apache-2.0"), POLICY)[0]
    assert ALIASES["bsd 3-clause"] == "BSD-3-Clause"
