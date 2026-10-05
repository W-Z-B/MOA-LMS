"""Marking rules per question type, after Moodle's. Pure functions: no database, no Django.

mark(qtype, data, response) returns a Result whose fraction runs from 0 to 1 (the share of the question's
mark earned), or None when a person must mark the answer (essays and file responses). An empty response
scores 0 and never goes to the marking queue. data has already passed schemas.validate_question.
"""

import math
import re
from dataclasses import dataclass, field

from quizzes import schemas
from quizzes.schemas import parse_number


@dataclass(frozen=True)
class Result:
    fraction: float | None
    feedback: str = ""
    needs_manual: bool = False
    parts: dict = field(default_factory=dict)  # per part detail: gaps, pairs, zones


ZERO = Result(0.0)


def _clamp(value: float) -> float:
    return round(min(1.0, max(0.0, value)), 7)


def normalise(text: str, case_sensitive: bool = False) -> str:
    """Trim and collapse spaces; ignore case unless the question says otherwise."""
    text = " ".join(str(text).split())
    return text if case_sensitive else text.casefold()


def wildcard_match(pattern: str, answer: str, case_sensitive: bool = False) -> bool:
    """Moodle short-answer matching: '*' matches any run of characters, '\\*' is a literal star."""
    pattern, answer = normalise(pattern, case_sensitive), normalise(answer, case_sensitive)
    regex, i = [], 0
    while i < len(pattern):
        if pattern[i] == "\\" and i + 1 < len(pattern) and pattern[i + 1] == "*":
            regex.append(re.escape("*"))
            i += 2
            continue
        regex.append(".*" if pattern[i] == "*" else re.escape(pattern[i]))
        i += 1
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.fullmatch("".join(regex), answer, flags | re.DOTALL) is not None


def _best_text(answers: list[dict], given: str, case_sensitive: bool) -> tuple[float, str]:
    best = None
    for answer in answers:
        if wildcard_match(answer["text"], given, case_sensitive):
            if best is None or answer["fraction"] > best["fraction"]:
                best = answer
    return (best["fraction"], best.get("feedback", "")) if best else (0.0, "")


def _best_number(answers: list[dict], value: float | None) -> tuple[float, str]:
    if value is None:
        return 0.0, ""
    best = None
    for answer in answers:
        target = answer["value"]
        hit = target is None or abs(value - target) <= answer["tolerance"] + 1e-9 * max(1.0, abs(target))
        if hit and (best is None or answer["fraction"] > best["fraction"]):
            best = answer
    return (best["fraction"], best.get("feedback", "")) if best else (0.0, "")


# ---------------------------------------------------------------------------------------------------------
# One function per type


def mark_multichoice(data: dict, response: dict) -> Result:
    by_id = {c["id"]: c for c in data["choices"]}
    if data["single"]:
        choice = by_id.get(response.get("choice"))
        if choice is None:
            return ZERO
        return Result(_clamp(choice["fraction"]), choice["feedback"])
    chosen = [by_id[c] for c in response.get("choices", []) if c in by_id]
    if not chosen:
        return ZERO
    feedback = "\n".join(c["feedback"] for c in chosen if c["feedback"])
    return Result(_clamp(sum(c["fraction"] for c in chosen)), feedback)


def mark_truefalse(data: dict, response: dict) -> Result:
    answer = response.get("answer")
    if not isinstance(answer, bool):
        return ZERO
    feedback = data["feedback_true"] if answer else data["feedback_false"]
    return Result(1.0 if answer == data["correct"] else 0.0, feedback)


def mark_matching(data: dict, response: dict) -> Result:
    matches = response.get("matches", {})
    parts = {p["id"]: matches.get(p["id"]) == p["answer"] for p in data["pairs"]}
    return Result(_clamp(sum(parts.values()) / len(parts)), parts=parts)


def mark_ordering(data: dict, response: dict) -> Result:
    right = [i["id"] for i in data["items"]]
    given = response.get("order", [])
    if not given:
        return ZERO
    if data["grading"] == "all_or_nothing":
        return Result(1.0 if given == right else 0.0)
    parts = {item: index < len(given) and given[index] == item for index, item in enumerate(right)}
    return Result(_clamp(sum(parts.values()) / len(right)), parts=parts)


def mark_shortanswer(data: dict, response: dict) -> Result:
    text = response.get("text", "")
    if not str(text).strip():
        return ZERO
    fraction, feedback = _best_text(data["answers"], text, data["case_sensitive"])
    return Result(_clamp(fraction), feedback)


_NUMBER_AND_UNIT = re.compile(r"^\s*([+-]?[\d.,]+(?:[eE][+-]?\d+)?)\s*(.*?)\s*$")


def split_value_and_unit(value: str, unit: str = "") -> tuple[float | None, str]:
    """'9.8 m/s2' -> (9.8, 'm/s2'). A separately given unit wins."""
    value = str(value)
    if not unit:
        found = _NUMBER_AND_UNIT.match(value)
        if found:
            value, unit = found.group(1), found.group(2)
    return parse_number(value), unit.strip()


def mark_numerical(data: dict, response: dict) -> Result:
    number, unit = split_value_and_unit(response.get("value", ""), response.get("unit", ""))
    if number is None:
        return ZERO
    multipliers = {u["unit"].replace(" ", ""): u["multiplier"] for u in data["units"]}
    known = multipliers.get(unit.replace(" ", ""))
    penalty = 0.0
    if data["unit_mode"] != "none" and known is not None:
        number = number / known  # answers are written in the first (base) unit
    elif data["unit_mode"] == "required":
        penalty = data["unit_penalty"]
    fraction, feedback = _best_number(data["answers"], number)
    if penalty and fraction > 0:
        feedback = (feedback + "\n" if feedback else "") + "The unit was missing or not recognised."
    return Result(_clamp(fraction * (1 - penalty)), feedback)


def mark_cloze(data: dict, response: dict) -> Result:
    given = response.get("gaps", {})
    total = earned = 0.0
    parts = {}
    for key, gap in data["gaps"].items():
        answer = given.get(key, "")
        if gap["kind"] == "numerical":
            fraction, _ = _best_number(gap["answers"], parse_number(str(answer)))
        elif gap["kind"] == "choice":
            fraction = next((a["fraction"] for a in gap["answers"] if a["text"] == answer), 0.0)
        else:
            fraction, _ = (
                _best_text(gap["answers"], answer, gap["case_sensitive"]) if str(answer).strip() else (0, "")
            )
        parts[key] = round(fraction, 7)
        earned += gap["weight"] * fraction
        total += gap["weight"]
    return Result(_clamp(earned / total) if total else 0.0, parts=parts)


def mark_manual(data: dict, response: dict) -> Result:
    blank = not any(str(v).strip() for v in response.values() if v is not None)
    return ZERO if blank else Result(None, needs_manual=True)


def point_in_zone(zone: dict, x: float, y: float) -> bool:
    if zone["shape"] == "rect":
        return zone["x"] <= x <= zone["x"] + zone["w"] and zone["y"] <= y <= zone["y"] + zone["h"]
    if zone["shape"] == "circle":
        return math.hypot(x - zone["x"], y - zone["y"]) <= zone["r"]
    inside, points = False, zone["points"]  # ray casting
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1], strict=True):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def mark_image_label(data: dict, response: dict) -> Result:
    zones = data["zones"]
    if data["mode"] == "drop_zones":
        placed = response.get("zones", {})
        parts = {z["id"]: placed.get(z["id"]) == z["label"] for z in zones}
        return Result(_clamp(sum(parts.values()) / len(zones)), parts=parts)
    # Markers: each placement can satisfy one zone of its label. A placement that satisfies nothing
    # cancels a correct one, so scattering every label everywhere earns nothing (as in Moodle).
    satisfied: dict[str, bool] = {z["id"]: False for z in zones}
    wrong = 0
    for p in response.get("placements", []):
        target = next(
            (
                z
                for z in zones
                if not satisfied[z["id"]] and z["label"] == p["label"] and point_in_zone(z, p["x"], p["y"])
            ),
            None,
        )
        if target is None:
            wrong += 1
        else:
            satisfied[target["id"]] = True
    right = sum(satisfied.values())
    return Result(_clamp((right - wrong) / len(zones)), parts=satisfied)


MARKERS = {
    schemas.MULTICHOICE: mark_multichoice,
    schemas.TRUEFALSE: mark_truefalse,
    schemas.MATCHING: mark_matching,
    schemas.ORDERING: mark_ordering,
    schemas.SHORTANSWER: mark_shortanswer,
    schemas.NUMERICAL: mark_numerical,
    schemas.CLOZE: mark_cloze,
    schemas.ESSAY: mark_manual,
    schemas.FILE: mark_manual,
    schemas.IMAGE_LABEL: mark_image_label,
}


def mark(qtype: str, data: dict, response: dict | None) -> Result:
    """Mark one response. An unanswered question scores 0."""
    if not response:
        return ZERO
    return MARKERS[qtype](data, response)


def correct_response(qtype: str, data: dict) -> dict | None:
    """A response that earns the full mark, for review once the quiz allows right answers to be shown."""
    if qtype == schemas.MULTICHOICE:
        if data["single"]:
            return {"choice": max(data["choices"], key=lambda c: c["fraction"])["id"]}
        return {"choices": sorted(c["id"] for c in data["choices"] if c["fraction"] > 0)}
    if qtype == schemas.TRUEFALSE:
        return {"answer": data["correct"]}
    if qtype == schemas.MATCHING:
        return {"matches": {p["id"]: p["answer"] for p in data["pairs"]}}
    if qtype == schemas.ORDERING:
        return {"order": [i["id"] for i in data["items"]]}
    if qtype == schemas.SHORTANSWER:
        return {"text": max(data["answers"], key=lambda a: a["fraction"])["text"]}
    if qtype == schemas.NUMERICAL:
        best = max(data["answers"], key=lambda a: a["fraction"])
        unit = data["units"][0]["unit"] if data["units"] and data["unit_mode"] != "none" else ""
        value = "" if best["value"] is None else f"{best['value']:g}"
        return {"value": value, "unit": unit}
    if qtype == schemas.CLOZE:
        gaps = {}
        for key, gap in data["gaps"].items():
            best = max(gap["answers"], key=lambda a: a["fraction"])
            if gap["kind"] == "numerical":
                gaps[key] = "" if best["value"] is None else f"{best['value']:g}"
            else:
                gaps[key] = best["text"]
        return {"gaps": gaps}
    if qtype == schemas.IMAGE_LABEL:
        if data["mode"] == "drop_zones":
            return {"zones": {z["id"]: z["label"] for z in data["zones"]}}
        return {"placements": [{"label": z["label"], **_centre(z)} for z in data["zones"]]}
    return None  # essays and files have no single right answer


def _centre(zone: dict) -> dict:
    if zone["shape"] == "rect":
        return {"x": zone["x"] + zone["w"] / 2, "y": zone["y"] + zone["h"] / 2}
    if zone["shape"] == "circle":
        return {"x": zone["x"], "y": zone["y"]}
    xs, ys = [p[0] for p in zone["points"]], [p[1] for p in zone["points"]]
    return {"x": sum(xs) / len(xs), "y": sum(ys) / len(ys)}
