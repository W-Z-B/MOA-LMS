"""The licence gate must refuse what the policy forbids, not only pass what it allows.

Run with:  python -m pytest -q -p no:django scripts
"""

from email.message import Message

import pytest
from check_licences import ALIASES, program_verdict, spdx_ok, verdict

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


FFMPEG = {
    "licence": "LGPL-2.1-or-later",
    "check": {
        "command": ["ffmpeg", "-L"],
        "must_say": "Lesser General Public",
        "build": ["ffmpeg", "-buildconf"],
        "must_not_say": ["--enable-gpl", "--enable-nonfree"],
    },
}


def answers(licence: str, build: str):
    """A stand-in for subprocess.run: the program's licence text, then its build configuration."""
    from subprocess import CompletedProcess

    def run(command, **kwargs):
        text = build if "-buildconf" in command else licence
        return CompletedProcess(command, 0, stdout=text, stderr="")

    return run


def test_a_program_beside_the_product_must_say_its_licence_and_build():
    found = lambda name: f"/usr/local/bin/{name}"  # noqa: E731
    lgpl = "under the terms of the GNU Lesser General\nPublic License as published"
    ok = program_verdict(FFMPEG, run=answers(lgpl, "--disable-network --enable-libopenh264"), which=found)
    assert ok == (True, "LGPL-2.1-or-later")
    gpl_build = program_verdict(FFMPEG, run=answers(lgpl, "--enable-gpl --enable-libx264"), which=found)
    assert gpl_build == (False, "built with --enable-gpl")
    gpl_text = program_verdict(FFMPEG, run=answers("GNU General Public License version 2", ""), which=found)
    assert gpl_text[0] is False and "LGPL-2.1-or-later" in gpl_text[1]


def test_a_program_not_installed_here_or_without_a_check_is_only_named():
    assert program_verdict(FFMPEG, which=lambda name: None) == (True, "not installed here; not checked")
    assert program_verdict({"licence": "MIT"}) == (True, "named: MIT")
