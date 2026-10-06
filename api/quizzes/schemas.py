"""Question types: the shape of each type's data, the shape of a student's response, and what a student sees.

Every question version stores its type-specific settings in one JSON field ("data"). This module is the
single place that says what that JSON may contain. It is pure Python (no database) so the rules are easy
to test; the serializers and the importers both call validate_question().

Shapes (ids are short strings, unique within the question; missing ids are filled in as a, b, c...):

multichoice  {"single": true, "shuffle": true,
              "choices": [{"id", "text", "fraction" -1..1, "feedback"}]}
             single: one choice is worth 1. multiple: the positive fractions add up to 1.
             response {"choice": id} (single) or {"choices": [id, ...]} (multiple)
truefalse    {"correct": true, "feedback_true", "feedback_false"}            response {"answer": bool}
matching     {"pairs": [{"id", "prompt", "answer"}], "extra_answers": [text], "shuffle": true}
             response {"matches": {pair_id: answer_text}}
ordering     {"items": [{"id", "text"}] in the right order, "grading": "absolute_position"|"all_or_nothing"}
             response {"order": [id, ...]}
shortanswer  {"answers": [{"text", "fraction" 0..1, "feedback"}], "case_sensitive": false}
             "*" in an accepted answer matches any run of characters; "\\*" is a literal star.
             response {"text": str}
numerical    {"answers": [{"value" number|null (null accepts any number), "tolerance" >= 0, "fraction",
              "feedback"}], "units": [{"unit", "multiplier"}], "unit_mode": "none"|"optional"|"required",
              "unit_penalty" 0..1}                            response {"value": str|number, "unit": str}
cloze        question text holds gaps written [[1]], [[2]] ...; data {"gaps": {"1": gap}} where gap is
             {"kind": "short", "answers": [{"text", "fraction", "feedback"}], "case_sensitive": false,
              "weight": 1} or {"kind": "numerical", "answers": [{"value", "tolerance", "fraction"}], ...}
             or {"kind": "choice", "answers": [{"text", "fraction", "feedback"}], ...}
             response {"gaps": {"1": str}}
essay        {"min_words": int|null, "max_words": int|null, "response_template", "grader_info"}
             marked by a person; response {"text": str}
file         {"allowed_extensions": ["pdf", ...], "max_size_mb": int, "grader_info"}
             marked by a person; the file is uploaded separately; response {"filename": str}
image_label  {"image_width", "image_height", "mode": "drop_zones"|"markers",
              "labels": [{"id", "text"}],
              "zones": [{"id", "label": label_id, "shape": "rect", "x", "y", "w", "h"}
                        | {"shape": "circle", "x", "y", "r"} | {"shape": "polygon", "points": [[x, y], ...]}]}
             drop_zones: the student sees the zones and puts a label in each:
                 response {"zones": {zone_id: label_id}}
             markers: the zones are hidden; the student drops labels at points:
                 response {"placements": [{"label": label_id, "x", "y"}]}
"""

import math
import re
from string import ascii_lowercase

MULTICHOICE = "multichoice"
TRUEFALSE = "truefalse"
MATCHING = "matching"
ORDERING = "ordering"
SHORTANSWER = "shortanswer"
NUMERICAL = "numerical"
CLOZE = "cloze"
ESSAY = "essay"
FILE = "file"
IMAGE_LABEL = "image_label"

QTYPE_CHOICES = [
    (MULTICHOICE, "Multiple choice"),
    (TRUEFALSE, "True or false"),
    (MATCHING, "Matching"),
    (ORDERING, "Ordering"),
    (SHORTANSWER, "Short answer"),
    (NUMERICAL, "Numerical"),
    (CLOZE, "Fill in the blanks"),
    (ESSAY, "Essay"),
    (FILE, "File response"),
    (IMAGE_LABEL, "Label a diagram"),
]
QTYPES = {code for code, _ in QTYPE_CHOICES}
MANUAL_TYPES = frozenset({ESSAY, FILE})

GAP_RE = re.compile(r"\[\[(\d{1,3})\]\]")
MAX_CHOICES = 50
MAX_TEXT = 20_000
# File responses accept the kinds core.uploads can recognise from their contents (item 1.12).
FILE_EXTENSIONS = frozenset({"pdf", "jpg", "jpeg", "png", "webp", "heic", "heif", "docx", "xlsx", "pptx"})
FILE_MAX_MB = 20


class QuestionDataError(ValueError):
    """The question's settings or a student's response do not fit the type. Carries every problem found."""

    def __init__(self, messages):
        self.messages = [messages] if isinstance(messages, str) else list(messages)
        super().__init__("; ".join(self.messages))


# ---------------------------------------------------------------------------------------------------------
# Small checkers


class _Check:
    def __init__(self):
        self.errors: list[str] = []

    def fail(self, message: str) -> None:
        self.errors.append(message)

    def raise_if_any(self) -> None:
        if self.errors:
            raise QuestionDataError(self.errors)


def _text(value, *, required=True, limit=MAX_TEXT) -> str | None:
    if value is None:
        return None if required else ""
    if not isinstance(value, str | int | float) or isinstance(value, bool):
        return None
    value = str(value)
    if len(value) > limit:
        return None
    if required and not value.strip():
        return None
    return value


def _number(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, str):
        return parse_number(value)
    return None


def parse_number(text: str) -> float | None:
    """A number as a person types it: '9.81', ' -3 ', '1,250.5', '0,5' (comma as decimal point), '6.02e23'."""
    if not isinstance(text, str):
        return None
    value = text.strip().replace(" ", "")
    if not value:
        return None
    if (
        "," in value
        and "." not in value
        and value.count(",") == 1
        and not re.fullmatch(r"-?\d{1,3},\d{3}", value)
    ):
        value = value.replace(",", ".")
    else:
        value = value.replace(",", "")
    if not re.fullmatch(r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?", value):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _fraction(value, check: _Check, where: str, *, low=-1.0) -> float:
    number = _number(value)
    if number is None or number < low - 1e-9 or number > 1 + 1e-9:
        check.fail(f"{where}: the fraction must be a number from {int(low)} to 1.")
        return 0.0
    return round(number, 7)


def _ids(items: list[dict], check: _Check, where: str) -> None:
    """Fill in missing ids (a, b, c...) and refuse duplicates."""
    seen = set()
    for index, item in enumerate(items):
        ident = item.get("id")
        if ident in (None, ""):
            ident = _default_id(index, seen)
        ident = str(ident)
        if len(ident) > 20:
            check.fail(f"{where}: an id is longer than 20 characters.")
        if ident in seen:
            check.fail(f"{where}: the id '{ident}' is used twice.")
        seen.add(ident)
        item["id"] = ident


def _default_id(index: int, taken: set) -> str:
    candidate = ascii_lowercase[index] if index < 26 else f"x{index}"
    while candidate in taken:
        index += 1
        candidate = f"x{index}"
    return candidate


def _list_of_dicts(value, check: _Check, where: str, *, minimum=1, maximum=MAX_CHOICES) -> list[dict]:
    if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
        check.fail(f"{where} must be a list of objects.")
        return []
    if len(value) < minimum:
        check.fail(f"{where} needs at least {minimum}.")
    if len(value) > maximum:
        check.fail(f"{where} may hold at most {maximum}.")
    return [dict(v) for v in value[:maximum]]


def _bool(value, default: bool) -> bool:
    return default if value is None else bool(value)


# ---------------------------------------------------------------------------------------------------------
# Question settings


def validate_question(qtype: str, text: str, data) -> dict:
    """Check and normalise a question's type-specific settings. Raises QuestionDataError."""
    if qtype not in QTYPES:
        raise QuestionDataError(f"Unknown question type '{qtype}'.")
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise QuestionDataError("The question settings must be an object.")
    check = _Check()
    cleaned = _VALIDATORS[qtype](text or "", dict(data), check)
    check.raise_if_any()
    return cleaned


def _v_multichoice(text, data, check):
    single = _bool(data.get("single"), True)
    choices = _list_of_dicts(data.get("choices"), check, "Choices", minimum=2)
    _ids(choices, check, "Choices")
    for c in choices:
        c["text"] = _text(c.get("text"))
        if c["text"] is None:
            check.fail(f"Choice '{c['id']}' needs text.")
        c["fraction"] = _fraction(c.get("fraction", 0), check, f"Choice '{c['id']}'")
        c["feedback"] = _text(c.get("feedback"), required=False) or ""
    fractions = [c["fraction"] for c in choices]
    if choices and single and max(fractions) < 1 - 1e-6:
        check.fail("One choice must be worth the full mark (fraction 1).")
    if choices and not single and abs(sum(f for f in fractions if f > 0) - 1) > 0.01:
        check.fail("For several correct answers, the positive fractions must add up to 1.")
    keys = ("id", "text", "fraction", "feedback")
    return {
        "single": single,
        "shuffle": _bool(data.get("shuffle"), True),
        "choices": [{k: c[k] for k in keys} for c in choices],
    }


def _v_truefalse(text, data, check):
    if not isinstance(data.get("correct"), bool):
        check.fail("Say whether the statement is true or false ('correct': true or false).")
    return {
        "correct": bool(data.get("correct")),
        "feedback_true": _text(data.get("feedback_true"), required=False) or "",
        "feedback_false": _text(data.get("feedback_false"), required=False) or "",
    }


def _v_matching(text, data, check):
    pairs = _list_of_dicts(data.get("pairs"), check, "Pairs", minimum=2)
    _ids(pairs, check, "Pairs")
    for p in pairs:
        p["prompt"], p["answer"] = _text(p.get("prompt")), _text(p.get("answer"), limit=500)
        if p["prompt"] is None or p["answer"] is None:
            check.fail(f"Pair '{p['id']}' needs a prompt and an answer.")
    extra = data.get("extra_answers") or []
    if not isinstance(extra, list) or any(_text(e, limit=500) is None for e in extra):
        check.fail("Extra answers must be a list of short texts.")
        extra = []
    return {
        "pairs": [{"id": p["id"], "prompt": p["prompt"], "answer": p["answer"]} for p in pairs],
        "extra_answers": [str(e) for e in extra],
        "shuffle": _bool(data.get("shuffle"), True),
    }


def _v_ordering(text, data, check):
    items = _list_of_dicts(data.get("items"), check, "Items", minimum=2)
    _ids(items, check, "Items")
    for item in items:
        item["text"] = _text(item.get("text"))
        if item["text"] is None:
            check.fail(f"Item '{item['id']}' needs text.")
    grading = data.get("grading") or "absolute_position"
    if grading not in ("absolute_position", "all_or_nothing"):
        check.fail("Grading must be 'absolute_position' or 'all_or_nothing'.")
    return {"items": [{"id": i["id"], "text": i["text"]} for i in items], "grading": grading}


def _text_answers(value, check, where, *, limit=500):
    answers = _list_of_dicts(value, check, where)
    for index, a in enumerate(answers, 1):
        a["text"] = _text(a.get("text"), limit=limit)
        if a["text"] is None:
            check.fail(f"{where} {index} needs text.")
        a["fraction"] = _fraction(a.get("fraction", 1), check, f"{where} {index}", low=0)
        a["feedback"] = _text(a.get("feedback"), required=False) or ""
    if answers and max(a["fraction"] for a in answers) < 1 - 1e-6:
        check.fail(f"{where}: one answer must be worth the full mark (fraction 1).")
    return [{"text": a["text"], "fraction": a["fraction"], "feedback": a["feedback"]} for a in answers]


def _v_shortanswer(text, data, check):
    return {
        "answers": _text_answers(data.get("answers"), check, "Accepted answer"),
        "case_sensitive": _bool(data.get("case_sensitive"), False),
    }


def _numeric_answers(value, check, where):
    answers = _list_of_dicts(value, check, where)
    cleaned = []
    for index, a in enumerate(answers, 1):
        raw = a.get("value")
        number = None if raw in (None, "*") else _number(raw)
        if raw not in (None, "*") and number is None:
            check.fail(f"{where} {index}: the value must be a number (or null to accept any number).")
        tolerance = _number(a.get("tolerance", 0))
        if tolerance is None or tolerance < 0:
            check.fail(f"{where} {index}: the tolerance must be zero or more.")
            tolerance = 0.0
        cleaned.append(
            {
                "value": number,
                "tolerance": tolerance,
                "fraction": _fraction(a.get("fraction", 1), check, f"{where} {index}", low=0),
                "feedback": _text(a.get("feedback"), required=False) or "",
            }
        )
    if cleaned and max(a["fraction"] for a in cleaned) < 1 - 1e-6:
        check.fail(f"{where}: one answer must be worth the full mark (fraction 1).")
    return cleaned


def _v_numerical(text, data, check):
    units = _list_of_dicts(data.get("units") or [], check, "Units", minimum=0)
    cleaned_units = []
    for index, u in enumerate(units, 1):
        name, multiplier = _text(u.get("unit"), limit=30), _number(u.get("multiplier", 1))
        if name is None or multiplier is None or multiplier == 0:
            check.fail(f"Unit {index} needs a name and a non-zero multiplier.")
            continue
        cleaned_units.append({"unit": name.strip(), "multiplier": multiplier})
    mode = data.get("unit_mode") or ("optional" if cleaned_units else "none")
    if mode not in ("none", "optional", "required"):
        check.fail("unit_mode must be 'none', 'optional' or 'required'.")
    if mode == "required" and not cleaned_units:
        check.fail("A required unit needs at least one unit.")
    penalty = _number(data.get("unit_penalty", 0.1))
    if penalty is None or not 0 <= penalty <= 1:
        check.fail("unit_penalty must be from 0 to 1.")
        penalty = 0.0
    return {
        "answers": _numeric_answers(data.get("answers"), check, "Answer"),
        "units": cleaned_units,
        "unit_mode": mode,
        "unit_penalty": penalty,
    }


def _v_cloze(text, data, check):
    in_text = GAP_RE.findall(text)
    gaps = data.get("gaps")
    if not isinstance(gaps, dict) or not gaps:
        check.fail("Fill in the blanks needs gaps: write [[1]], [[2]] ... in the text and set each gap.")
        return {"gaps": {}}
    if len(in_text) != len(set(in_text)):
        check.fail("Each gap number may appear only once in the text.")
    if set(in_text) != set(gaps):
        check.fail("The gaps in the text and the gap settings do not match.")
    cleaned = {}
    for key, gap in gaps.items():
        if not isinstance(gap, dict):
            check.fail(f"Gap {key} must be an object.")
            continue
        kind = gap.get("kind") or "short"
        weight = _number(gap.get("weight", 1))
        if weight is None or weight <= 0:
            check.fail(f"Gap {key}: the weight must be more than zero.")
            weight = 1.0
        if kind == "numerical":
            answers = _numeric_answers(gap.get("answers"), check, f"Gap {key} answer")
        elif kind in ("short", "choice"):
            answers = _text_answers(gap.get("answers"), check, f"Gap {key} answer")
        else:
            check.fail(f"Gap {key}: the kind must be 'short', 'numerical' or 'choice'.")
            continue
        cleaned[str(key)] = {
            "kind": kind,
            "answers": answers,
            "case_sensitive": _bool(gap.get("case_sensitive"), False),
            "weight": weight,
        }
    return {"gaps": cleaned}


def _optional_int(value, check, where):
    if value in (None, ""):
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        check.fail(f"{where} must be a whole number of zero or more.")
        return None
    return value


def _v_essay(text, data, check):
    low = _optional_int(data.get("min_words"), check, "min_words")
    high = _optional_int(data.get("max_words"), check, "max_words")
    if low is not None and high is not None and low > high:
        check.fail("min_words is more than max_words.")
    return {
        "min_words": low,
        "max_words": high,
        "response_template": _text(data.get("response_template"), required=False) or "",
        "grader_info": _text(data.get("grader_info"), required=False) or "",
    }


def _v_file(text, data, check):
    extensions = data.get("allowed_extensions") or ["pdf", "docx", "jpg", "jpeg", "png"]
    if not isinstance(extensions, list):
        check.fail("allowed_extensions must be a list.")
        extensions = []
    cleaned = sorted({str(e).lower().lstrip(".") for e in extensions})
    unknown = [e for e in cleaned if e not in FILE_EXTENSIONS]
    if unknown:
        check.fail(f"These file types are not accepted: {', '.join(unknown)}.")
    size = data.get("max_size_mb", 10)
    if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= FILE_MAX_MB:
        check.fail(f"max_size_mb must be a whole number from 1 to {FILE_MAX_MB}.")
        size = 10
    return {
        "allowed_extensions": cleaned,
        "max_size_mb": size,
        "grader_info": _text(data.get("grader_info"), required=False) or "",
    }


def _v_image_label(text, data, check):
    width, height = _number(data.get("image_width")), _number(data.get("image_height"))
    if not width or not height or width <= 0 or height <= 0:
        check.fail("Give the image's width and height in pixels; zone coordinates are measured on it.")
        width, height = width or 1.0, height or 1.0
    mode = data.get("mode") or "drop_zones"
    if mode not in ("drop_zones", "markers"):
        check.fail("mode must be 'drop_zones' or 'markers'.")
    labels = _list_of_dicts(data.get("labels"), check, "Labels")
    _ids(labels, check, "Labels")
    for label in labels:
        label["text"] = _text(label.get("text"), limit=200)
        if label["text"] is None:
            check.fail(f"Label '{label['id']}' needs text.")
    label_ids = {label["id"] for label in labels}
    zones = _list_of_dicts(data.get("zones"), check, "Zones")
    _ids(zones, check, "Zones")
    cleaned_zones = []
    for z in zones:
        where = f"Zone '{z['id']}'"
        if str(z.get("label")) not in label_ids:
            check.fail(f"{where}: its label is not one of the labels.")
        shape = z.get("shape") or "rect"
        zone = {"id": z["id"], "label": str(z.get("label")), "shape": shape}
        if shape == "rect":
            values = [_number(z.get(k)) for k in ("x", "y", "w", "h")]
            if None in values or values[2] <= 0 or values[3] <= 0:
                check.fail(f"{where}: a rectangle needs x, y, w and h (w and h above zero).")
                continue
            zone.update(zip(("x", "y", "w", "h"), values, strict=True))
        elif shape == "circle":
            values = [_number(z.get(k)) for k in ("x", "y", "r")]
            if None in values or values[2] <= 0:
                check.fail(f"{where}: a circle needs x, y and a radius r above zero.")
                continue
            zone.update(zip(("x", "y", "r"), values, strict=True))
        elif shape == "polygon":
            points = z.get("points")
            ok = (
                isinstance(points, list)
                and len(points) >= 3
                and all(
                    isinstance(p, list | tuple) and len(p) == 2 and None not in (_number(p[0]), _number(p[1]))
                    for p in points
                )
            )
            if not ok:
                check.fail(f"{where}: a polygon needs at least three [x, y] points.")
                continue
            zone["points"] = [[_number(p[0]), _number(p[1])] for p in points]
        else:
            check.fail(f"{where}: the shape must be 'rect', 'circle' or 'polygon'.")
            continue
        cleaned_zones.append(zone)
    return {
        "image_width": width,
        "image_height": height,
        "mode": mode,
        "labels": [{"id": label["id"], "text": label["text"]} for label in labels],
        "zones": cleaned_zones,
    }


_VALIDATORS = {
    MULTICHOICE: _v_multichoice,
    TRUEFALSE: _v_truefalse,
    MATCHING: _v_matching,
    ORDERING: _v_ordering,
    SHORTANSWER: _v_shortanswer,
    NUMERICAL: _v_numerical,
    CLOZE: _v_cloze,
    ESSAY: _v_essay,
    FILE: _v_file,
    IMAGE_LABEL: _v_image_label,
}


# ---------------------------------------------------------------------------------------------------------
# Responses


def validate_response(qtype: str, data: dict, response) -> dict | None:
    """Check the shape of a student's response before it is saved. None clears the answer."""
    if response is None:
        return None
    if not isinstance(response, dict):
        raise QuestionDataError("The answer must be an object.")
    check = _Check()
    cleaned = _RESPONSES[qtype](data, response, check)
    check.raise_if_any()
    return cleaned


def _r_multichoice(data, response, check):
    ids = {c["id"] for c in data["choices"]}
    if data["single"]:
        choice = response.get("choice")
        if choice is not None and str(choice) not in ids:
            check.fail("That choice is not one of the options.")
        return {"choice": None if choice is None else str(choice)}
    chosen = response.get("choices") or []
    if not isinstance(chosen, list) or any(str(c) not in ids for c in chosen):
        check.fail("Choose from the options given.")
        return {"choices": []}
    return {"choices": sorted({str(c) for c in chosen})}


def _r_truefalse(data, response, check):
    answer = response.get("answer")
    if answer is not None and not isinstance(answer, bool):
        check.fail("Answer true or false.")
    return {"answer": answer}


def _r_matching(data, response, check):
    matches = response.get("matches") or {}
    options = {p["answer"] for p in data["pairs"]} | set(data["extra_answers"])
    pair_ids = {p["id"] for p in data["pairs"]}
    if not isinstance(matches, dict):
        check.fail("Matches must map each prompt to an answer.")
        return {"matches": {}}
    for key, value in matches.items():
        if key not in pair_ids or (value is not None and value not in options):
            check.fail("Match each prompt to one of the answers given.")
            break
    return {"matches": {k: v for k, v in matches.items() if v is not None}}


def _r_ordering(data, response, check):
    order = response.get("order") or []
    ids = [i["id"] for i in data["items"]]
    if not isinstance(order, list) or sorted(map(str, order)) != sorted(ids):
        check.fail("Put every item in order, each once.")
        return {"order": []}
    return {"order": [str(o) for o in order]}


def _r_text(data, response, check):
    text = response.get("text", "")
    if not isinstance(text, str) or len(text) > MAX_TEXT:
        check.fail("The answer must be text of reasonable length.")
        return {"text": ""}
    return {"text": text}


def _r_short(data, response, check):
    cleaned = _r_text(data, response, check)
    if len(cleaned["text"]) > 500:
        check.fail("The answer is too long.")
    return cleaned


def _r_numerical(data, response, check):
    value, unit = response.get("value", ""), response.get("unit", "") or ""
    if isinstance(value, bool) or not isinstance(value, str | int | float) or not isinstance(unit, str):
        check.fail("Give the number as text or a number, and the unit as text.")
        return {"value": "", "unit": ""}
    return {"value": str(value)[:60], "unit": unit[:30]}


def _r_cloze(data, response, check):
    gaps = response.get("gaps") or {}
    if not isinstance(gaps, dict) or any(k not in data["gaps"] for k in gaps):
        check.fail("Answer the gaps by their numbers.")
        return {"gaps": {}}
    cleaned = {}
    for key, value in gaps.items():
        if value is None:
            continue
        if not isinstance(value, str | int | float) or isinstance(value, bool) or len(str(value)) > 500:
            check.fail(f"Gap {key}: the answer must be short text.")
            continue
        cleaned[key] = str(value)
    return {"gaps": cleaned}


def _r_file(data, response, check):
    check.fail("Upload the file with the file endpoint for this question.")
    return {}


def _r_image_label(data, response, check):
    label_ids = {label["id"] for label in data["labels"]}
    if data["mode"] == "drop_zones":
        zones = response.get("zones") or {}
        zone_ids = {z["id"] for z in data["zones"]}
        if not isinstance(zones, dict) or any(
            k not in zone_ids or (v is not None and v not in label_ids) for k, v in zones.items()
        ):
            check.fail("Put labels from the list into the zones shown.")
            return {"zones": {}}
        return {"zones": {k: v for k, v in zones.items() if v is not None}}
    placements = response.get("placements") or []
    cleaned = []
    if not isinstance(placements, list) or len(placements) > 4 * len(data["zones"]):
        check.fail("Too many labels placed.")
        return {"placements": []}
    for p in placements:
        x = _number(p.get("x")) if isinstance(p, dict) else None
        y = _number(p.get("y")) if isinstance(p, dict) else None
        if x is None or y is None or p.get("label") not in label_ids:
            check.fail("Each placed label needs a label from the list and x and y on the image.")
            break
        cleaned.append({"label": p["label"], "x": x, "y": y})
    return {"placements": cleaned}


_RESPONSES = {
    MULTICHOICE: _r_multichoice,
    TRUEFALSE: _r_truefalse,
    MATCHING: _r_matching,
    ORDERING: _r_ordering,
    SHORTANSWER: _r_short,
    NUMERICAL: _r_numerical,
    CLOZE: _r_cloze,
    ESSAY: _r_text,
    FILE: _r_file,
    IMAGE_LABEL: _r_image_label,
}


# ---------------------------------------------------------------------------------------------------------
# What a student sees


def make_layout(qtype: str, data: dict, *, shuffle: bool, rng) -> dict:
    """The order options are shown in for one attempt, saved so it never changes on reload."""

    def maybe(items):
        items = list(items)
        if shuffle:
            rng.shuffle(items)
        return items

    if qtype == MULTICHOICE:
        ids = [c["id"] for c in data["choices"]]
        return {"choices": maybe(ids) if data.get("shuffle", True) else ids}
    if qtype == MATCHING:
        answers = sorted({p["answer"] for p in data["pairs"]} | set(data["extra_answers"]))
        rng.shuffle(answers)  # matching answers are always mixed, or the order gives the answer away
        return {"answers": answers}
    if qtype == ORDERING:
        ids = [i["id"] for i in data["items"]]
        shuffled = list(ids)
        for _ in range(10):  # never present the items already in the right order
            rng.shuffle(shuffled)
            if shuffled != ids:
                break
        return {"items": shuffled}
    if qtype == CLOZE:
        return {
            "choices": {
                key: maybe([a["text"] for a in gap["answers"]])
                for key, gap in data["gaps"].items()
                if gap["kind"] == "choice"
            }
        }
    if qtype == IMAGE_LABEL:
        return {"labels": maybe([label["id"] for label in data["labels"]])}
    return {}


def public_data(qtype: str, data: dict, layout: dict | None = None) -> dict:
    """The settings a student may see while answering: never fractions, right answers or zone labels."""
    layout = layout or {}
    if qtype == MULTICHOICE:
        by_id = {c["id"]: c for c in data["choices"]}
        order = layout.get("choices") or list(by_id)
        return {"single": data["single"], "choices": [{"id": i, "text": by_id[i]["text"]} for i in order]}
    if qtype == MATCHING:
        answers = layout.get("answers") or sorted(
            {p["answer"] for p in data["pairs"]} | set(data["extra_answers"])
        )
        return {"prompts": [{"id": p["id"], "text": p["prompt"]} for p in data["pairs"]], "answers": answers}
    if qtype == ORDERING:
        by_id = {i["id"]: i for i in data["items"]}
        order = layout.get("items") or sorted(by_id)
        return {"items": [{"id": i, "text": by_id[i]["text"]} for i in order]}
    if qtype == NUMERICAL:
        return {"units": [u["unit"] for u in data["units"]], "unit_mode": data["unit_mode"]}
    if qtype == CLOZE:
        choices = layout.get("choices", {})
        gaps = {}
        for key, gap in data["gaps"].items():
            gaps[key] = {"kind": gap["kind"]}
            if gap["kind"] == "choice":
                gaps[key]["choices"] = choices.get(key) or [a["text"] for a in gap["answers"]]
        return {"gaps": gaps}
    if qtype == ESSAY:
        return {k: data[k] for k in ("min_words", "max_words", "response_template")}
    if qtype == FILE:
        return {k: data[k] for k in ("allowed_extensions", "max_size_mb")}
    if qtype == IMAGE_LABEL:
        by_id = {label["id"]: label for label in data["labels"]}
        order = layout.get("labels") or list(by_id)
        shown = {
            "image_width": data["image_width"],
            "image_height": data["image_height"],
            "mode": data["mode"],
            "labels": [{"id": i, "text": by_id[i]["text"]} for i in order],
        }
        if data["mode"] == "drop_zones":  # positions only; which label belongs where stays hidden
            shown["zones"] = [{k: v for k, v in z.items() if k != "label"} for z in data["zones"]]
        return shown
    return {}
