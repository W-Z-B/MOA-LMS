#!/usr/bin/env python3
"""Licence gate for the Python packages the product ships (ADR 0002).

Every package pinned in api/requirements.txt must be installed in the running interpreter and carry a
permissive licence, or be a named exception in scripts/licence-policy.json. Packages that only appear in
requirements-dev.txt never ship and are not checked. Programs run beside the product as separate processes
(FFmpeg, ADR 0002 point 6) are named under "programs"; where one is installed, what it says of its own licence
and build is checked too.

Run where the runtime packages are installed, from the repository root:
    python scripts/check_licences.py
or against the Compose image:
    docker compose run --rm -v "$PWD:/repo" -w /repo api python scripts/check_licences.py

Standard library only, so it can run in any image. Exit status 1 lists every package that fails.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POLICY_FILE = ROOT / "scripts" / "licence-policy.json"
REQUIREMENTS = ROOT / "api" / "requirements.txt"

# Trove classifiers and free-text licence fields, mapped to the identifiers the policy uses.
ALIASES = {
    "mit license": "MIT",
    "mit": "MIT",
    "bsd license": "BSD",
    "bsd": "BSD",
    "bsd 3-clause": "BSD-3-Clause",
    "apache software license": "Apache-2.0",
    "apache 2.0": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "apache-2.0": "Apache-2.0",
    "isc license (iscl)": "ISC",
    "python software foundation license": "PSF-2.0",
    "historical permission notice and disclaimer (hpnd)": "HPND",
    "the unlicense (unlicense)": "Unlicense",
    "zlib/libpng license": "Zlib",
    "postgresql license": "PostgreSQL",
}
COPYLEFT = re.compile(r"\b(A?GPL|LGPL|MPL|EPL|EUPL|SSPL|BUSL|CDDL|OSL)\b|General Public|Mozilla", re.I)


def normalise_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def pinned_packages(path: Path) -> list[str]:
    """Names pinned with == in a pip-compile output file (continuation and comment lines skipped)."""
    names = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]*\])?==", line)
        if match:
            names.append(normalise_name(match.group(1)))
    return names


def to_id(text: str) -> str:
    return ALIASES.get(text.strip().lower(), text.strip())


def spdx_ok(expression: str, allowed: set[str]) -> bool:
    """Whether an SPDX licence expression can be met using allowed licences only.

    Follows SPDX precedence: brackets first, then WITH, AND, OR. An operand of several words is read as
    one licence name through ALIASES, so free text such as "BSD 3-Clause OR Apache-2.0" also works. An
    expression that cannot be parsed is refused, so a person reviews it.
    """
    tokens = re.findall(r"\(|\)|[^\s()]+", expression)
    pos = 0

    def peek() -> str | None:
        return tokens[pos] if pos < len(tokens) else None

    def take() -> str:
        nonlocal pos
        pos += 1
        return tokens[pos - 1]

    def keyword(*words: str) -> bool:
        token = peek()
        return token is not None and token.upper() in words

    def factor() -> bool:
        if peek() == "(":
            take()
            value = either()
            if peek() != ")":
                raise ValueError("unbalanced brackets")
            take()
            return value
        words = []
        while peek() not in (None, "(", ")") and not keyword("AND", "OR", "WITH"):
            words.append(take())
        if not words:
            raise ValueError("missing licence")
        value = to_id(" ".join(words)) in allowed
        if keyword("WITH"):  # an exception widens what the licence allows; it never makes it permissive
            take()
            while peek() not in (None, "(", ")") and not keyword("AND", "OR"):
                take()
        return value

    def both() -> bool:
        value = factor()
        while keyword("AND"):
            take()
            value = factor() and value
        return value

    def either() -> bool:
        value = both()
        while keyword("OR"):
            take()
            value = both() or value
        return value

    try:
        result = either()
    except ValueError:
        return False
    return result and pos == len(tokens)


def declared(dist: metadata.Distribution) -> tuple[str, list[str]]:
    """The licence a package declares: (SPDX expression or '', identifiers from classifiers and fields)."""
    meta = dist.metadata
    expression = (meta.get("License-Expression") or "").strip()
    found = []
    for classifier in meta.get_all("Classifier") or []:
        if classifier.startswith("License ::"):
            found.append(classifier.split("::")[-1].strip())
    text = (meta.get("License") or "").strip()
    if text and "\n" not in text and len(text) <= 60:
        found.append(text)
    return expression, found


def verdict(name: str, dist: metadata.Distribution, policy: dict) -> tuple[bool, str]:
    allowed = set(policy["permissive"])
    exception = policy["exceptions"]["python"].get(name)
    expression, found = declared(dist)
    if exception:
        return True, f"exception: {exception['licence']} ({exception['reason']})"
    if expression:
        ok = spdx_ok(expression, allowed)
        return ok, expression
    for text in found:  # a free-text field written as an expression: "BSD 3-Clause OR Apache-2.0"
        if re.search(r"\s(OR|AND)\s", text) and spdx_ok(text, allowed):
            return True, text
    ids = [to_id(item) for item in found]
    if not ids:
        return False, "no licence declared; review it and add an exception if it is acceptable"
    permissive = [i for i in ids if i in allowed]
    copyleft = [i for i in ids if COPYLEFT.search(i)]
    if permissive and not copyleft:
        return True, "; ".join(sorted(set(ids)))
    if copyleft:
        return False, "copyleft: " + "; ".join(sorted(set(ids)))
    return False, "not recognised: " + "; ".join(sorted(set(ids)))


def program_verdict(entry: dict, run=subprocess.run, which=shutil.which) -> tuple[bool, str]:
    """Whether an installed program says what its policy entry requires of it. Not installed: not checked."""
    check = entry.get("check")
    if not check:
        return True, f"named: {entry['licence']}"
    if which(check["command"][0]) is None:
        return True, "not installed here; not checked"
    said = run(check["command"], capture_output=True, text=True, check=False)  # noqa: S603 - from the policy file
    words = " ".join((said.stdout + said.stderr).split())
    if check["must_say"] not in words:
        return False, f"does not say it is {entry['licence']} ({check['must_say']!r} missing)"
    if check.get("build"):
        built = run(check["build"], capture_output=True, text=True, check=False)  # noqa: S603
        wrong = [flag for flag in check.get("must_not_say", []) if flag in built.stdout + built.stderr]
        if wrong:
            return False, "built with " + ", ".join(wrong)
    return True, entry["licence"]


def main() -> int:
    policy = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
    installed = {normalise_name(d.metadata["Name"]): d for d in metadata.distributions()}
    failures, rows = [], []
    for name in pinned_packages(REQUIREMENTS):
        dist = installed.get(name)
        if dist is None:
            failures.append(f"{name}: pinned in requirements.txt but not installed here")
            continue
        ok, why = verdict(name, dist, policy)
        rows.append(f"{'ok  ' if ok else 'FAIL'} {name} {dist.version}: {why}")
        if not ok:
            failures.append(f"{name} {dist.version}: {why}")
    packages = len(rows)
    # Programs run beside the product (ADR 0002, point 6): checked where they are installed.
    for name, entry in policy["exceptions"].get("programs", {}).items():
        if name.startswith("$"):
            continue
        ok, why = program_verdict(entry)
        rows.append(f"{'ok  ' if ok else 'FAIL'} program {name}: {why}")
        if not ok:
            failures.append(f"program {name}: {why}")
    print("\n".join(rows))
    if failures:
        print("\nLicence policy (ADR 0002) not met:\n  " + "\n  ".join(failures), file=sys.stderr)
        return 1
    print(f"\n{packages} shipped Python packages and the programs beside them meet the licence policy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
