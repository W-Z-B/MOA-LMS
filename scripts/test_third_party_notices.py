"""THIRD-PARTY-NOTICES must name every component and where each LGPL or MPL source is obtained (item 7.20).

Run with:  python -m pytest -q -p no:django scripts
"""

import json

from third_party_notices import build, components, licences_of, main

POLICY = {
    "permissive": ["MIT"],
    "exceptions": {
        "python": {
            "psycopg": {
                "licence": "LGPL-3.0-only",
                "reason": "The driver.",
                "source": "https://github.com/psycopg",
            }
        },
        "npm": {},
    },
}


def _bom(tmp_path, name, items):
    path = tmp_path / name
    path.write_text(json.dumps({"bomFormat": "CycloneDX", "components": items}), encoding="utf-8")
    return path


def test_licences_come_from_expressions_identifiers_or_names():
    assert licences_of({"licenses": [{"expression": "MIT OR Apache-2.0"}]}) == "MIT OR Apache-2.0"
    assert licences_of({"licenses": [{"license": {"id": "MIT"}}, {"license": {"name": "MIT"}}]}) == "MIT"
    assert licences_of({}) == "Not stated"


def test_every_component_is_listed_and_the_lgpl_source_is_named(tmp_path):
    python = components(
        _bom(
            tmp_path,
            "py.json",
            [
                {"name": "Django", "version": "5.2", "licenses": [{"license": {"id": "BSD-3-Clause"}}]},
                {"name": "psycopg", "version": "3.3", "licenses": [{"license": {"id": "LGPL-3.0-only"}}]},
            ],
        ),
        "python",
    )
    web = components(
        _bom(tmp_path, "web.json", [{"group": "@scope", "name": "react", "version": "19", "licenses": []}]),
        "npm",
    )
    text, problems = build(python, web, POLICY)
    assert problems == []
    assert "| Django | 5.2 | BSD-3-Clause |" in text and "| @scope/react | 19 | Not stated |" in text
    assert "**psycopg 3.3** (LGPL-3.0-only). The driver.\n  Source: https://github.com/psycopg" in text


def test_a_weak_copyleft_component_without_a_named_source_fails_the_release(tmp_path, capsys):
    py = _bom(
        tmp_path, "py.json", [{"name": "pyphen", "version": "0.17", "licenses": [{"expression": "MPL-1.1"}]}]
    )
    web = _bom(tmp_path, "web.json", [])
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(POLICY), encoding="utf-8")
    out = tmp_path / "NOTICES.md"
    assert main([str(py), str(web), "-o", str(out), "--policy", str(policy)]) == 1
    assert "pyphen 0.17 (MPL-1.1) has no named exception" in capsys.readouterr().err
    assert "| pyphen | 0.17 | MPL-1.1 |" in out.read_text(encoding="utf-8")


def test_programs_beside_the_product_are_listed_and_an_lgpl_one_needs_its_source():
    policy = {
        "exceptions": {
            "python": {},
            "npm": {},
            "programs": {
                "$comment": "ignored",
                "ffmpeg": {"licence": "LGPL-2.1-or-later", "reason": "Video.", "source": "Debian ffmpeg"},
                "openh264": {"licence": "BSD-2-Clause", "reason": "H.264."},
            },
        }
    }
    text, problems = build([], [], policy)
    assert problems == []
    assert (
        "| ffmpeg | LGPL-2.1-or-later | Video. | Debian ffmpeg |" in text
        and "| openh264 | BSD-2-Clause |" in text
    )
    del policy["exceptions"]["programs"]["ffmpeg"]["source"]
    assert build([], [], policy)[1] == ["program ffmpeg (LGPL-2.1-or-later) has no named source"]
