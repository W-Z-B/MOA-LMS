"""Question import and export: Moodle XML (the main one), GIFT and QTI 2.1 (item 3.07, decision D1).

Parsers turn a file into ParsedQuestion records and a list of what was skipped and why. Nothing here
touches the database; services.import_questions validates each record with schemas.validate_question and
saves it.

XML safety. Python's xml.etree (expat) does not fetch external entities, but it does expand entities
declared in an internal DTD, which allows "billion laughs" style memory exhaustion. No dependency is
added for this: every XML input is refused outright if it contains a document type declaration or an
entity declaration (<!DOCTYPE or <!ENTITY, in any case), before it reaches the parser. Moodle, GIFT and
QTI files never need either. Inputs are also capped in size, and zip packages in member count and
uncompressed size.
"""

import io
import re
import xml.etree.ElementTree as ET  # noqa: S405 - guarded by refuse_unsafe_xml() before every parse
import zipfile
from dataclasses import dataclass, field

from quizzes import schemas

MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_ZIP_MEMBERS = 500
MAX_ZIP_UNCOMPRESSED = 20 * 1024 * 1024  # the XML documents in it
MAX_ZIP_ENTRIES = 2000  # every entry, pictures included (core.archives)
FORMATS = ("moodle_xml", "gift", "qti")
EXPORT_FORMATS = ("moodle_xml", "gift")


class FormatError(ValueError):
    """The file as a whole cannot be read."""


@dataclass
class ParsedQuestion:
    qtype: str
    name: str
    text: str
    data: dict
    default_mark: float = 1.0
    general_feedback: str = ""
    tags: list[str] = field(default_factory=list)
    category_path: list[str] = field(default_factory=list)


@dataclass
class ParseResult:
    questions: list[ParsedQuestion] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)  # {"name", "reason"}
    warnings: list[str] = field(default_factory=list)

    def skip(self, name: str, reason: str) -> None:
        self.skipped.append({"name": name or "(no name)", "reason": reason})


_UNSAFE_XML = re.compile(r"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)


def refuse_unsafe_xml(text: str) -> None:
    if _UNSAFE_XML.search(text):
        raise FormatError("The file declares a document type or entities, which are not accepted for safety.")


def parse_xml(text: str) -> ET.Element:
    refuse_unsafe_xml(text)
    try:
        return ET.fromstring(text)  # noqa: S314 - DTDs and entities refused above
    except ET.ParseError as error:
        raise FormatError(f"The file is not well-formed XML ({error}).") from error


def decode(content: bytes | str) -> str:
    if isinstance(content, str):
        text = content
    else:
        if len(content) > MAX_IMPORT_BYTES:
            raise FormatError("The file is larger than 5 MB.")
        for encoding in ("utf-8-sig", "cp1252"):
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:  # pragma: no cover - cp1252 decodes nearly anything
            raise FormatError("The file's text encoding cannot be read; save it as UTF-8.")
    if len(text) > MAX_IMPORT_BYTES:
        raise FormatError("The file is larger than 5 MB.")
    return text


def parse(fmt: str, content: bytes | str, filename: str = "") -> ParseResult:
    if fmt == "moodle_xml":
        return parse_moodle_xml(decode(content))
    if fmt == "gift":
        return parse_gift(decode(content))
    if fmt == "qti":
        return parse_qti(content, filename)
    raise FormatError(f"Unknown format '{fmt}'. Use one of: {', '.join(FORMATS)}.")


# ---------------------------------------------------------------------------------------------------------
# Moodle XML


def _child_text(element, path: str, default: str = "") -> str:
    found = element.find(path)
    if found is None:
        return default
    text = found.find("text")
    node = text if text is not None else found
    return (node.text or "").strip() if node.text is not None else default


def _fraction(value) -> float:
    try:
        return round(float(value or 0) / 100, 7)
    except ValueError:
        return 0.0


def _moodle_answers(question) -> list[dict]:
    return [
        {
            "text": _child_text(a, "."),
            "fraction": _fraction(a.get("fraction")),
            "feedback": _child_text(a, "feedback"),
            "element": a,
        }
        for a in question.findall("answer")
    ]


def _bool_text(value: str, default=False) -> bool:
    value = (value or "").strip().lower()
    if not value:
        return default
    return value in ("1", "true", "yes")


def category_path(raw: str) -> list[str]:
    parts = [p.strip() for p in raw.split("/") if p.strip()]
    while parts and (parts[0].startswith("$") or parts[0].lower() == "top"):
        parts.pop(0)
    return parts


def parse_moodle_xml(text: str) -> ParseResult:
    root = parse_xml(text)
    if root.tag != "quiz":
        raise FormatError("This is not a Moodle XML question file (the root element must be <quiz>).")
    result, category = ParseResult(), []
    for number, question in enumerate(root.findall("question"), 1):
        qtype = question.get("type", "")
        if qtype == "category":
            category = category_path(_child_text(question, "category"))
            continue
        name = _child_text(question, "name") or f"Question {number}"
        if "@@PLUGINFILE@@" in _child_text(question, "questiontext"):
            result.warnings.append(f"{name}: embedded images were not imported; add them again.")
        handler = _MOODLE_IMPORTERS.get(qtype)
        if handler is None:
            reason = (
                "A description is not a question."
                if qtype == "description"
                else (f"The Moodle question type '{qtype}' is not supported.")
            )
            result.skip(name, reason)
            continue
        try:
            parsed_type, data = handler(question)
        except FormatError as error:
            result.skip(name, str(error))
            continue
        try:
            default_mark = float(_child_text(question, "defaultgrade", "1") or 1)
        except ValueError:
            default_mark = 1.0
        result.questions.append(
            ParsedQuestion(
                qtype=parsed_type,
                name=name[:200],
                text=_child_text(question, "questiontext"),
                data=data,
                default_mark=default_mark if default_mark > 0 else 1.0,
                general_feedback=_child_text(question, "generalfeedback"),
                tags=[t for t in (_child_text(tag, ".") for tag in question.findall("tags/tag")) if t][:20],
                category_path=category,
            )
        )
    return result


def _m_multichoice(q):
    answers = _moodle_answers(q)
    return schemas.MULTICHOICE, {
        "single": _bool_text(_child_text(q, "single"), True),
        "shuffle": _bool_text(_child_text(q, "shuffleanswers"), True),
        "choices": [
            {"text": a["text"], "fraction": a["fraction"], "feedback": a["feedback"]} for a in answers
        ],
    }


def _m_truefalse(q):
    answers = {a["text"].lower(): a for a in _moodle_answers(q)}
    if "true" not in answers or "false" not in answers:
        raise FormatError("A true or false question needs both a 'true' and a 'false' answer.")
    return schemas.TRUEFALSE, {
        "correct": answers["true"]["fraction"] > answers["false"]["fraction"],
        "feedback_true": answers["true"]["feedback"],
        "feedback_false": answers["false"]["feedback"],
    }


def _m_shortanswer(q):
    return schemas.SHORTANSWER, {
        "answers": [
            {"text": a["text"], "fraction": a["fraction"], "feedback": a["feedback"]}
            for a in _moodle_answers(q)
            if a["fraction"] > 0
        ],
        "case_sensitive": _bool_text(_child_text(q, "usecase")),
    }


def _m_numerical(q):
    answers = []
    for a in _moodle_answers(q):
        if a["fraction"] <= 0:
            continue
        tolerance = _child_text(a["element"], "tolerance", "0") or "0"
        answers.append(
            {
                "value": None if a["text"] == "*" else a["text"],
                "tolerance": tolerance,
                "fraction": a["fraction"],
                "feedback": a["feedback"],
            }
        )
    units = [
        {"unit": _child_text(u, "unit_name"), "multiplier": _child_text(u, "multiplier", "1") or "1"}
        for u in q.findall("units/unit")
    ]
    show = _child_text(q, "showunits", "3")
    grading = _child_text(q, "unitgradingtype", "0")
    if not units or show == "3":
        mode = "none"
    else:
        mode = "required" if grading in ("1", "2") else "optional"
    try:
        penalty = float(_child_text(q, "unitpenalty", "0.1") or 0.1)
    except ValueError:
        penalty = 0.1
    return schemas.NUMERICAL, {
        "answers": answers,
        "units": units if mode != "none" else [],
        "unit_mode": mode,
        "unit_penalty": penalty,
    }


def _m_matching(q):
    pairs, extra = [], []
    for sub in q.findall("subquestion"):
        prompt, answer = _child_text(sub, "."), _child_text(sub, "answer")
        if prompt:
            pairs.append({"prompt": prompt, "answer": answer})
        elif answer:
            extra.append(answer)
    return schemas.MATCHING, {
        "pairs": pairs,
        "extra_answers": extra,
        "shuffle": _bool_text(_child_text(q, "shuffleanswers"), True),
    }


def _m_essay(q):
    response_format = _child_text(q, "responseformat", "editor")
    attachments = _child_text(q, "attachmentsrequired", "0") or _child_text(q, "attachments", "0")
    grader_info = _child_text(q, "graderinfo")
    if response_format == "noinline" and attachments not in ("", "0"):
        types = _child_text(q, "filetypeslist")
        extensions = [t.strip().lstrip(".").lower() for t in re.split(r"[,;\s]+", types) if t.strip()]
        extensions = [e for e in extensions if e in schemas.FILE_EXTENSIONS] or None
        return schemas.FILE, {"allowed_extensions": extensions, "grader_info": grader_info}
    return schemas.ESSAY, {
        "response_template": _child_text(q, "responsetemplate"),
        "grader_info": grader_info,
    }


def _m_ordering(q):
    answers = _moodle_answers(q)
    grading = _child_text(q, "gradingtype", "0")
    return schemas.ORDERING, {
        "items": [{"text": a["text"]} for a in answers],
        "grading": "all_or_nothing" if grading == "-1" else "absolute_position",
    }


_CLOZE = re.compile(r"\{(\d*):([A-Z_]+):((?:\\.|[^\\}])*)\}")
_CLOZE_TYPES = {
    "SHORTANSWER": ("short", False), "SA": ("short", False), "MW": ("short", False),
    "SHORTANSWER_C": ("short", True), "SAC": ("short", True), "MWC": ("short", True),
    "NUMERICAL": ("numerical", False), "NM": ("numerical", False),
    "MULTICHOICE": ("choice", False), "MC": ("choice", False), "MULTICHOICE_V": ("choice", False),
    "MCV": ("choice", False), "MULTICHOICE_H": ("choice", False), "MCH": ("choice", False),
    "MULTICHOICE_S": ("choice", False), "MCS": ("choice", False), "MULTICHOICE_VS": ("choice", False),
    "MCVS": ("choice", False), "MULTICHOICE_HS": ("choice", False), "MCHS": ("choice", False),
}  # fmt: skip


def _split_unescaped(text: str, separator: str) -> list[str]:
    parts, current, i = [], [], 0
    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text):
            current.append(text[i : i + 2])
            i += 2
            continue
        if text[i] == separator:
            parts.append("".join(current))
            current = []
        else:
            current.append(text[i])
        i += 1
    parts.append("".join(current))
    return parts


def _unescape(text: str) -> str:
    return re.sub(r"\\(.)", r"\1", text).strip()


def parse_cloze_text(text: str) -> tuple[str, dict]:
    """Moodle embedded answers: '{1:SHORTANSWER:=ans#feedback~%50%partial}' becomes [[1]] and a gap."""
    gaps, counter = {}, 0

    def replace(match):
        nonlocal counter
        weight, kind_code, body = match.group(1), match.group(2), match.group(3)
        if kind_code not in _CLOZE_TYPES:
            raise FormatError(f"The embedded answer type '{kind_code}' is not supported.")
        kind, case_sensitive = _CLOZE_TYPES[kind_code]
        counter += 1
        answers = []
        for raw in _split_unescaped(body, "~"):
            if not raw.strip():
                continue
            fraction = 0.0
            if raw.startswith("="):
                fraction, raw = 1.0, raw[1:]
            else:
                found = re.match(r"%(-?\d+(?:\.\d+)?)%", raw)
                if found:
                    fraction, raw = float(found.group(1)) / 100, raw[found.end() :]
            answer_text, *feedback = _split_unescaped(raw, "#")
            answer = {"fraction": max(0.0, fraction), "feedback": _unescape(feedback[0]) if feedback else ""}
            if kind == "numerical":
                value, _, tolerance = _unescape(answer_text).partition(":")
                answer.update({"value": None if value == "*" else value, "tolerance": tolerance or 0})
            else:
                answer["text"] = _unescape(answer_text)
            if kind == "choice" or answer["fraction"] > 0:
                answers.append(answer)
        gaps[str(counter)] = {
            "kind": kind,
            "answers": answers,
            "case_sensitive": case_sensitive,
            "weight": int(weight) if weight else 1,
        }
        return f"[[{counter}]]"

    return _CLOZE.sub(replace, text), gaps


_MOODLE_IMPORTERS = {
    "multichoice": _m_multichoice,
    "truefalse": _m_truefalse,
    "shortanswer": _m_shortanswer,
    "numerical": _m_numerical,
    "matching": _m_matching,
    "essay": _m_essay,
    "ordering": _m_ordering,
}


def _moodle_cloze(question):
    text, gaps = parse_cloze_text(_child_text(question, "questiontext"))
    if not gaps:
        raise FormatError("The embedded answers question has no gaps.")
    holder = question.find("questiontext/text")
    if holder is None:
        holder = question.find("questiontext")
    holder.text = text  # the gap markers replace the embedded answers
    return schemas.CLOZE, {"gaps": gaps}


_MOODLE_IMPORTERS["cloze"] = _moodle_cloze


# ---------------------------------------------------------------------------------------------------------
# Moodle XML export


def _text_el(parent, tag: str, value: str, fmt: str | None = "html"):
    element = ET.SubElement(parent, tag)
    if fmt:
        element.set("format", fmt)
    ET.SubElement(element, "text").text = value or ""
    return element


def _answer_el(parent, fraction: float, text: str, feedback: str = "", fmt="html"):
    answer = ET.SubElement(parent, "answer", {"fraction": _percent(fraction), "format": fmt})
    ET.SubElement(answer, "text").text = text
    _text_el(answer, "feedback", feedback)
    return answer


def _percent(fraction: float) -> str:
    return f"{fraction * 100:.7f}".rstrip("0").rstrip(".") or "0"


def _num(value) -> str:
    return "*" if value is None else f"{value:g}"


def export_moodle_xml(items) -> tuple[str, list[dict]]:
    """items: (question, version, category path list). Returns the XML and what could not be exported."""
    root, skipped, last_category = ET.Element("quiz"), [], None
    for question, version, path in items:
        builder = _MOODLE_EXPORTERS.get(question.qtype)
        if builder is None:
            skipped.append({"name": question.name, "reason": "Moodle XML has no equivalent for this type."})
            continue
        if path != last_category:
            category = ET.SubElement(root, "question", {"type": "category"})
            _text_el(category, "category", "/".join(["$course$", "top", *path]), fmt=None)
            last_category = path
        qtype = "essay" if question.qtype == schemas.FILE else question.qtype  # Moodle: an essay with files
        element = ET.SubElement(root, "question", {"type": qtype})
        _text_el(element, "name", question.name, fmt=None)
        text = version.text
        if question.qtype == schemas.CLOZE:
            text = _cloze_text(version.text, version.data)
        _text_el(element, "questiontext", text)
        _text_el(element, "generalfeedback", version.general_feedback)
        ET.SubElement(element, "defaultgrade").text = f"{version.default_mark:.7f}"
        builder(element, version.data)
        if question.tags:
            tags = ET.SubElement(element, "tags")
            for tag in question.tags:
                _text_el(tags, "tag", tag, fmt=None)
    ET.indent(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n", skipped


def _x_multichoice(el, data):
    ET.SubElement(el, "single").text = "true" if data["single"] else "false"
    ET.SubElement(el, "shuffleanswers").text = "true" if data["shuffle"] else "false"
    ET.SubElement(el, "answernumbering").text = "abc"
    for c in data["choices"]:
        _answer_el(el, c["fraction"], c["text"], c["feedback"])


def _x_truefalse(el, data):
    _answer_el(el, 1.0 if data["correct"] else 0.0, "true", data["feedback_true"], fmt="moodle_auto_format")
    _answer_el(el, 0.0 if data["correct"] else 1.0, "false", data["feedback_false"], fmt="moodle_auto_format")


def _x_shortanswer(el, data):
    ET.SubElement(el, "usecase").text = "1" if data["case_sensitive"] else "0"
    for a in data["answers"]:
        _answer_el(el, a["fraction"], a["text"], a["feedback"], fmt="moodle_auto_format")


def _x_numerical(el, data):
    for a in data["answers"]:
        answer = _answer_el(el, a["fraction"], _num(a["value"]), a["feedback"], fmt="moodle_auto_format")
        ET.SubElement(answer, "tolerance").text = f"{a['tolerance']:g}"
    if data["units"]:
        units = ET.SubElement(el, "units")
        for u in data["units"]:
            unit = ET.SubElement(units, "unit")
            ET.SubElement(unit, "multiplier").text = f"{u['multiplier']:g}"
            ET.SubElement(unit, "unit_name").text = u["unit"]
    mode = data["unit_mode"]
    ET.SubElement(el, "unitgradingtype").text = "1" if mode == "required" else "0"
    ET.SubElement(el, "unitpenalty").text = f"{data['unit_penalty']:g}"
    ET.SubElement(el, "showunits").text = "3" if mode == "none" else "0"


def _x_matching(el, data):
    ET.SubElement(el, "shuffleanswers").text = "true" if data["shuffle"] else "false"
    for p in data["pairs"]:
        sub = _text_el(el, "subquestion", p["prompt"])
        _text_el(sub, "answer", p["answer"], fmt=None)
    for extra in data["extra_answers"]:
        sub = _text_el(el, "subquestion", "")
        _text_el(sub, "answer", extra, fmt=None)


def _x_essay(el, data):
    ET.SubElement(el, "responseformat").text = "editor"
    ET.SubElement(el, "responserequired").text = "1"
    ET.SubElement(el, "attachments").text = "0"
    _text_el(el, "graderinfo", data["grader_info"])
    _text_el(el, "responsetemplate", data["response_template"])


def _x_file(el, data):
    ET.SubElement(el, "responseformat").text = "noinline"
    ET.SubElement(el, "attachments").text = "1"
    ET.SubElement(el, "attachmentsrequired").text = "1"
    ET.SubElement(el, "filetypeslist").text = ",".join(f".{e}" for e in data["allowed_extensions"])
    _text_el(el, "graderinfo", data["grader_info"])


def _x_ordering(el, data):
    ET.SubElement(el, "gradingtype").text = "-1" if data["grading"] == "all_or_nothing" else "0"
    for item in data["items"]:
        _answer_el(el, 1.0, item["text"], fmt="moodle_auto_format")


def _x_cloze(el, data):
    pass  # the answers are embedded in the question text


_CLOZE_CODE = {"short": "SHORTANSWER", "numerical": "NUMERICAL", "choice": "MULTICHOICE"}


def _cloze_escape(text: str) -> str:
    return re.sub(r"([}~#\\/])", r"\\\1", str(text))


def _cloze_text(text: str, data: dict) -> str:
    def gap(match):
        g = data["gaps"].get(match.group(1))
        if g is None:
            return match.group(0)
        code = _CLOZE_CODE[g["kind"]] + ("_C" if g["kind"] == "short" and g["case_sensitive"] else "")
        parts = []
        for a in g["answers"]:
            prefix = "=" if a["fraction"] >= 1 else f"%{_percent(a['fraction'])}%"
            value = (
                f"{_num(a['value'])}:{a['tolerance']:g}"
                if g["kind"] == "numerical"
                else _cloze_escape(a["text"])
            )
            feedback = f"#{_cloze_escape(a['feedback'])}" if a.get("feedback") else ""
            parts.append(f"{prefix}{value}{feedback}")
        weight = int(g["weight"]) if float(g["weight"]).is_integer() else 1
        return "{" + f"{weight}:{code}:" + "~".join(parts) + "}"

    return schemas.GAP_RE.sub(gap, text)


_MOODLE_EXPORTERS = {
    schemas.MULTICHOICE: _x_multichoice,
    schemas.TRUEFALSE: _x_truefalse,
    schemas.SHORTANSWER: _x_shortanswer,
    schemas.NUMERICAL: _x_numerical,
    schemas.MATCHING: _x_matching,
    schemas.ESSAY: _x_essay,
    schemas.FILE: _x_file,
    schemas.ORDERING: _x_ordering,
    schemas.CLOZE: _x_cloze,
}


# ---------------------------------------------------------------------------------------------------------
# GIFT


def _gift_blocks(text: str) -> list[str]:
    lines = [line for line in text.replace("\r\n", "\n").split("\n") if not line.lstrip().startswith("//")]
    blocks, current = [], []
    for line in lines:
        if line.strip():
            current.append(line)
        elif current:
            blocks.append("\n".join(current))
            current = []
    if current:
        blocks.append("\n".join(current))
    return blocks


def _find_unescaped(text: str, char: str, start: int = 0) -> int:
    i = start
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == char:
            return i
        i += 1
    return -1


def _gift_unescape(text: str) -> str:
    text = text.replace("\\n", "\n")
    return re.sub(r"\\([~=#{}:\\])", r"\1", text).strip()


def _strip_format(text: str) -> str:
    return re.sub(r"^\s*\[(html|moodle|plain|markdown)\]", "", text, flags=re.IGNORECASE)


def _gift_tokens(body: str) -> list[tuple[str, str]]:
    """Split an answer block into (marker, content) where marker is '=' or '~'."""
    tokens, current, marker, i = [], [], None, 0
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body):
            current.append(body[i : i + 2])
            i += 2
            continue
        if ch in "=~":
            if marker is not None:
                tokens.append((marker, "".join(current)))
            marker, current = ch, []
        else:
            current.append(ch)
        i += 1
    if marker is not None:
        tokens.append((marker, "".join(current)))
    return tokens


def _weight(content: str) -> tuple[float | None, str]:
    found = re.match(r"\s*%(-?\d+(?:\.\d+)?)%", content)
    if found:
        return float(found.group(1)) / 100, content[found.end() :]
    return None, content


def _feedback(content: str) -> tuple[str, str]:
    cut = _find_unescaped(content, "#")
    if cut < 0:
        return content, ""
    return content[:cut], content[cut + 1 :]


def parse_gift(text: str) -> ParseResult:
    result, category = ParseResult(), []
    for number, block in enumerate(_gift_blocks(text), 1):
        stripped = block.strip()
        if stripped.startswith("$CATEGORY:"):
            category = category_path(stripped[len("$CATEGORY:") :].strip())
            continue
        name = ""
        if stripped.startswith("::"):
            end = stripped.find("::", 2)
            if end > 0:
                name, stripped = _gift_unescape(stripped[2:end]), stripped[end + 2 :]
        open_at = _find_unescaped(stripped, "{")
        close_at = _find_unescaped(stripped, "}", open_at + 1) if open_at >= 0 else -1
        if open_at < 0 or close_at < 0:
            result.skip(
                name or f"Question {number}", "No answer block {...} was found (descriptions are skipped)."
            )
            continue
        before, body, after = stripped[:open_at], stripped[open_at + 1 : close_at], stripped[close_at + 1 :]
        question_text = _gift_unescape(_strip_format(before))
        if after.strip():  # missing-word format: the answers sit inside the sentence
            question_text = f"{question_text} _____ {_gift_unescape(after)}".strip()
        name = name or re.sub(r"<[^>]+>", "", question_text)[:60] or f"Question {number}"
        try:
            qtype, data = _gift_answers(body)
        except FormatError as error:
            result.skip(name, str(error))
            continue
        result.questions.append(
            ParsedQuestion(
                qtype=qtype, name=name[:200], text=question_text, data=data, category_path=category
            )
        )
    return result


def _gift_answers(body: str):
    content = body.strip()
    if not content:
        return schemas.ESSAY, {}
    head, *feedbacks = _split_unescaped(content, "#")
    if head.strip().upper() in ("T", "TRUE", "F", "FALSE") and not content.startswith("#"):
        correct = head.strip().upper().startswith("T")
        wrong_fb = _gift_unescape(feedbacks[0]) if feedbacks else ""
        right_fb = _gift_unescape(feedbacks[1]) if len(feedbacks) > 1 else ""
        return schemas.TRUEFALSE, {
            "correct": correct,
            "feedback_true": right_fb if correct else wrong_fb,
            "feedback_false": wrong_fb if correct else right_fb,
        }
    if content.startswith("#"):
        return schemas.NUMERICAL, {"answers": _gift_numeric(content[1:]), "units": [], "unit_mode": "none"}
    tokens = _gift_tokens(content)
    if not tokens:
        raise FormatError("The answer block could not be read.")
    if all(marker == "=" and "->" in value for marker, value in tokens):
        pairs, extra = [], []
        for _, value in tokens:
            prompt, _, answer = value.partition("->")
            if _gift_unescape(prompt):
                pairs.append({"prompt": _gift_unescape(prompt), "answer": _gift_unescape(answer)})
            else:
                extra.append(_gift_unescape(answer))
        return schemas.MATCHING, {"pairs": pairs, "extra_answers": extra}
    answers = []
    for marker, value in tokens:
        weight, value = _weight(value)
        answer_text, feedback = _feedback(value)
        fraction = weight if weight is not None else (1.0 if marker == "=" else 0.0)
        answers.append(
            {
                "marker": marker,
                "text": _gift_unescape(answer_text),
                "fraction": fraction,
                "feedback": _gift_unescape(feedback),
            }
        )
    if all(a["marker"] == "=" for a in answers):
        return schemas.SHORTANSWER, {
            "answers": [
                {k: a[k] for k in ("text", "fraction", "feedback")} for a in answers if a["fraction"] > 0
            ]
        }
    positives = [a for a in answers if a["fraction"] > 0]
    single = not (len(positives) > 1 and all(a["fraction"] < 1 for a in positives))
    return schemas.MULTICHOICE, {
        "single": single,
        "choices": [{k: a[k] for k in ("text", "fraction", "feedback")} for a in answers],
    }


def _gift_numeric(body: str) -> list[dict]:
    tokens = _gift_tokens(body) if "=" in body else [("=", body)]
    answers = []
    for _, value in tokens:
        weight, value = _weight(value)
        value, feedback = _feedback(value)
        value = _gift_unescape(value)
        if ".." in value:
            low, _, high = value.partition("..")
            try:
                low_n, high_n = float(low), float(high)
            except ValueError as error:
                raise FormatError(f"The numeric range '{value}' cannot be read.") from error
            number, tolerance = (low_n + high_n) / 2, abs(high_n - low_n) / 2
        else:
            number_text, _, tolerance_text = value.partition(":")
            number = None if number_text.strip() == "*" else number_text.strip()
            tolerance = tolerance_text.strip() or 0
        answers.append(
            {
                "value": number,
                "tolerance": tolerance,
                "fraction": 1.0 if weight is None else weight,
                "feedback": _gift_unescape(feedback),
            }
        )
    return [a for a in answers if a["fraction"] > 0]


def _gift_escape(text: str) -> str:
    return re.sub(r"([~=#{}:\\])", r"\\\1", str(text)).replace("\n", "\\n")


def export_gift(items) -> tuple[str, list[dict]]:
    out, skipped, last_category = [], [], None
    for question, version, path in items:
        body = _gift_body(question.qtype, version.data)
        if body is None:
            skipped.append({"name": question.name, "reason": "GIFT has no equivalent for this type."})
            continue
        if path != last_category:
            out.append(f"$CATEGORY: {'/'.join(['$course$', 'top', *path])}\n")
            last_category = path
        out.append(f"::{_gift_escape(question.name)}::[html]{_gift_escape(version.text)} {{{body}}}\n")
    return "\n".join(out), skipped


def _gift_choice(fraction: float, text: str, feedback: str, *, single: bool) -> str:
    if single and fraction >= 1:
        prefix = "="
    elif single and fraction <= 0:
        prefix = "~"
    else:
        prefix = f"~%{_percent(fraction)}%"
    return f"{prefix}{_gift_escape(text)}" + (f"#{_gift_escape(feedback)}" if feedback else "")


def _gift_body(qtype: str, data: dict) -> str | None:
    if qtype == schemas.MULTICHOICE:
        return " ".join(
            _gift_choice(c["fraction"], c["text"], c["feedback"], single=data["single"])
            for c in data["choices"]
        )
    if qtype == schemas.TRUEFALSE:
        right, wrong = (
            (data["feedback_true"], data["feedback_false"])
            if data["correct"]
            else (data["feedback_false"], data["feedback_true"])
        )
        feedback = f"#{_gift_escape(wrong)}#{_gift_escape(right)}" if (right or wrong) else ""
        return ("TRUE" if data["correct"] else "FALSE") + feedback
    if qtype == schemas.SHORTANSWER:
        return " ".join(
            ("=" if a["fraction"] >= 1 else f"=%{_percent(a['fraction'])}%")
            + _gift_escape(a["text"])
            + (f"#{_gift_escape(a['feedback'])}" if a["feedback"] else "")
            for a in data["answers"]
        )
    if qtype == schemas.NUMERICAL:
        if data["unit_mode"] == "required":
            return None
        return "#" + " ".join(
            ("=" if a["fraction"] >= 1 else f"=%{_percent(a['fraction'])}%")
            + f"{_num(a['value'])}:{a['tolerance']:g}"
            for a in data["answers"]
        )
    if qtype == schemas.MATCHING:
        pairs = [f"={_gift_escape(p['prompt'])} -> {_gift_escape(p['answer'])}" for p in data["pairs"]]
        return " ".join(pairs + [f"= -> {_gift_escape(e)}" for e in data["extra_answers"]])
    if qtype == schemas.ESSAY:
        return ""
    return None


# ---------------------------------------------------------------------------------------------------------
# QTI 2.1 (assessmentItem documents, alone or in a content package zip)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find_all(element, name: str):
    return [e for e in element.iter() if _local(e.tag) == name]


def _inner_html(element) -> str:
    """The element's content as plain HTML without namespace prefixes."""
    parts = [element.text or ""]
    for child in element:
        markup = ET.tostring(child, encoding="unicode")
        markup = re.sub(r"\s+xmlns(:\w+)?=\"[^\"]*\"", "", markup)
        markup = re.sub(r"<(/?)\w+:", r"<\1", markup)
        parts.append(markup)
    return "".join(parts).strip()


def parse_qti(content: bytes | str, filename: str = "") -> ParseResult:
    result = ParseResult()
    packaged = isinstance(content, bytes) and content[:2] == b"PK"
    if packaged:
        documents = _zip_documents(content)
    else:
        documents = [(filename or "item.xml", decode(content))]
    for name, text in documents:
        try:
            root = parse_xml(text)
        except FormatError as error:
            if not packaged:
                raise
            result.skip(name, str(error))
            continue
        local = _local(root.tag)
        if local == "questestinterop":
            result.skip(name, "QTI 1.2 is not supported; export as QTI 2.1.")
            continue
        items = [root] if local == "assessmentItem" else _find_all(root, "assessmentItem")
        if not items and local in ("manifest", "assessmentTest"):
            continue  # package metadata; the items are separate files
        if not items:
            result.skip(name, "No QTI 2.1 assessmentItem was found.")
            continue
        for item in items:
            _qti_item(item, result)
    return result


def _zip_documents(content: bytes) -> list[tuple[str, str]]:
    from django.conf import settings

    from core import archives

    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as error:
        raise FormatError("The zip package cannot be opened.") from error
    try:  # the package as a whole (pictures too), as for SCORM packages: count, size, zip bombs
        infos = archives.checked(
            archive, max_entries=MAX_ZIP_ENTRIES, max_bytes=settings.PACKAGE_MAX_UNPACKED_MB * archives.MB
        )
    except archives.ArchiveRefused as refused:
        raise FormatError(str(refused)) from refused
    members = [m for m in infos if m.filename.lower().endswith(".xml") and not m.is_dir()]
    if len(members) > MAX_ZIP_MEMBERS:
        raise FormatError(f"The package holds more than {MAX_ZIP_MEMBERS} files.")
    if sum(m.file_size for m in members) > MAX_ZIP_UNCOMPRESSED:
        raise FormatError("The package is larger than 20 MB when unpacked.")
    documents = []
    for member in members:
        if member.filename.lower().endswith("imsmanifest.xml"):
            continue
        with archive.open(member) as handle:
            data = handle.read(MAX_ZIP_UNCOMPRESSED + 1)
        documents.append((member.filename, decode(data[: MAX_IMPORT_BYTES + 1])))
    return documents


def _qti_values(declaration) -> tuple[list[str], dict[str, float]]:
    correct = []
    for block in _find_all(declaration, "correctResponse"):
        correct.extend((v.text or "").strip() for v in _find_all(block, "value"))
    mapping = {}
    for entry in _find_all(declaration, "mapEntry"):
        try:
            mapping[entry.get("mapKey", "")] = float(entry.get("mappedValue", "0"))
        except ValueError:
            continue
    return correct, mapping


def _qti_item(item, result: ParseResult) -> None:
    name = item.get("title") or item.get("identifier") or "QTI item"
    declarations = {d.get("identifier"): d for d in _find_all(item, "responseDeclaration")}
    body = next(iter(_find_all(item, "itemBody")), None)
    if body is None:
        result.skip(name, "The item has no itemBody.")
        return
    interactions = [e for e in body.iter() if _local(e.tag).endswith("Interaction")]
    if len(interactions) != 1:
        result.skip(name, "Only items with exactly one interaction are supported.")
        return
    interaction = interactions[0]
    kind = _local(interaction.tag)
    declaration = declarations.get(interaction.get("responseIdentifier"))
    correct, mapping = _qti_values(declaration) if declaration is not None else ([], {})
    prompt = next((e for e in interaction if _local(e.tag) == "prompt"), None)
    text_parts = []
    for child in body:
        if child is interaction or interaction in list(child.iter()):
            continue
        text_parts.append(_inner_html_wrapped(child))
    if prompt is not None:
        text_parts.append(_inner_html(prompt))
    text = "\n".join(p for p in text_parts if p.strip())
    if kind in ("choiceInteraction", "orderInteraction"):
        choices = [c for c in interaction if _local(c.tag) == "simpleChoice"]
        if kind == "orderInteraction":
            by_id = {c.get("identifier"): _inner_html(c) for c in choices}
            order = [i for i in correct if i in by_id] or list(by_id)
            result.questions.append(
                ParsedQuestion(
                    schemas.ORDERING, name[:200], text, {"items": [{"text": by_id[i]} for i in order]}
                )
            )
            return
        single = interaction.get("maxChoices", "1") == "1"
        fractions = _qti_fractions(choices, correct, mapping, single)
        result.questions.append(
            ParsedQuestion(
                schemas.MULTICHOICE,
                name[:200],
                text,
                {
                    "single": single,
                    "shuffle": interaction.get("shuffle", "false") == "true",
                    "choices": [
                        {
                            "id": c.get("identifier"),
                            "text": _inner_html(c),
                            "fraction": fractions[c.get("identifier")],
                        }
                        for c in choices
                    ],
                },
            )
        )
        return
    if kind == "textEntryInteraction":
        answers = [{"text": v, "fraction": 1.0} for v in correct]
        answers += [
            {"text": k, "fraction": min(1.0, v)} for k, v in mapping.items() if v > 0 and k not in correct
        ]
        result.questions.append(ParsedQuestion(schemas.SHORTANSWER, name[:200], text, {"answers": answers}))
        return
    if kind == "extendedTextInteraction":
        result.questions.append(ParsedQuestion(schemas.ESSAY, name[:200], text, {}))
        return
    result.skip(name, f"The QTI interaction '{kind}' is not supported.")


def _inner_html_wrapped(element) -> str:
    markup = ET.tostring(element, encoding="unicode")
    markup = re.sub(r"\s+xmlns(:\w+)?=\"[^\"]*\"", "", markup)
    return re.sub(r"<(/?)\w+:", r"<\1", markup).strip()


def _qti_fractions(choices, correct: list[str], mapping: dict, single: bool) -> dict[str, float]:
    ids = [c.get("identifier") for c in choices]
    if mapping and any(v > 0 for v in mapping.values()):
        positive = [v for v in mapping.values() if v > 0]
        scale = max(positive) if single else sum(positive)
        return {i: max(-1.0, min(1.0, round(mapping.get(i, 0.0) / scale, 7))) for i in ids}
    right = [i for i in ids if i in correct]
    if not right:
        return {i: 0.0 for i in ids}
    if single:
        return {i: 1.0 if i in right else 0.0 for i in ids}
    share = round(1 / len(right), 7)
    return {i: share if i in right else -share for i in ids}
