"""The wording of a certificate (ported from the HRMS letters/markup.py): paragraphs, lists and bold, with
fields in double braces.

A paragraph ends at a blank line; a paragraph whose every line starts "- " is a list; **words** are bold;
{{full_name}} is a field. The wording is parsed before anything is merged into it, so a value can never
change the certificate's shape, and every piece of text is escaped when it becomes HTML.
"""

import html
import re

FIELD = re.compile(r"\{\{\s*([a-z][a-z0-9_]*)\s*\}\}")
BOLD = re.compile(r"\*\*(.+?)\*\*")


def fields_in(*texts: str) -> list[str]:
    """The fields the texts use, each once, in the order they first appear."""
    seen: list[str] = []
    for text in texts:
        for key in FIELD.findall(text):
            if key not in seen:
                seen.append(key)
    return seen


def unclosed(text: str) -> bool:
    """Whether braces are left once the well-formed fields are taken out: a field typed wrongly."""
    rest = FIELD.sub("", text)
    return "{" in rest or "}" in rest


def _runs(line: str) -> list[dict]:
    return [{"text": part, "bold": i % 2 == 1} for i, part in enumerate(BOLD.split(line)) if part]


def parse(body: str) -> list[dict]:
    """The blocks of the wording: paragraphs of lines, or lists of items, each a list of runs of text."""
    blocks = []
    for chunk in re.split(r"\n[ \t]*\n", body.replace("\r\n", "\n").strip()):
        lines = [line.strip() for line in chunk.split("\n") if line.strip()]
        if not lines:
            continue
        if all(line.startswith("- ") for line in lines):
            blocks.append({"type": "list", "items": [_runs(line[2:].strip()) for line in lines]})
        else:
            blocks.append({"type": "paragraph", "lines": [_runs(line) for line in lines]})
    return blocks


def fill(text: str, values: dict[str, str]) -> str:
    return FIELD.sub(lambda m: values.get(m.group(1), ""), text)


def merge(blocks: list[dict], values: dict[str, str]) -> list[dict]:
    """The blocks with every field replaced by its value."""

    def runs(line):
        return [{"text": fill(run["text"], values), "bold": run["bold"]} for run in line]

    merged = []
    for block in blocks:
        if block["type"] == "list":
            merged.append({"type": "list", "items": [runs(item) for item in block["items"]]})
        else:
            merged.append({"type": "paragraph", "lines": [runs(line) for line in block["lines"]]})
    return merged


def to_html(blocks: list[dict]) -> str:
    def runs(line):
        return "".join(
            f"<strong>{html.escape(run['text'])}</strong>" if run["bold"] else html.escape(run["text"])
            for run in line
        )

    out = []
    for block in blocks:
        if block["type"] == "list":
            out.append("<ul>" + "".join(f"<li>{runs(item)}</li>" for item in block["items"]) + "</ul>")
        else:
            out.append("<p>" + "<br>".join(runs(line) for line in block["lines"]) + "</p>")
    return "\n".join(out)
