"""Marking rules and question settings per type. Pure: no database."""

import random

import pytest

from quizzes import marking, schemas
from quizzes.schemas import QuestionDataError, validate_question, validate_response


def q(qtype, data, text="Question"):
    return validate_question(qtype, text, data)


def score(qtype, data, response):
    clean = validate_response(qtype, data, response)
    return marking.mark(qtype, data, clean)


# --- multiple choice ------------------------------------------------------------------------------------

SINGLE = {
    "single": True,
    "choices": [
        {"text": "Nitrogen", "fraction": 1, "feedback": "Yes: leaf growth."},
        {"text": "Phosphorus", "fraction": 0.5, "feedback": "Partly."},
        {"text": "Calcium", "fraction": -0.25},
    ],
}


def test_single_choice_marks_by_the_chosen_option_and_never_below_zero():
    data = q("multichoice", SINGLE)
    assert [c["id"] for c in data["choices"]] == ["a", "b", "c"]
    right = score("multichoice", data, {"choice": "a"})
    assert right.fraction == 1.0 and right.feedback == "Yes: leaf growth."
    assert score("multichoice", data, {"choice": "b"}).fraction == 0.5
    assert score("multichoice", data, {"choice": "c"}).fraction == 0.0
    assert score("multichoice", data, {"choice": None}).fraction == 0.0
    assert marking.mark("multichoice", data, None).fraction == 0.0


def test_multiple_answers_add_their_fractions_and_clamp():
    data = q(
        "multichoice",
        {
            "single": False,
            "choices": [
                {"id": "n", "text": "N", "fraction": 0.5},
                {"id": "p", "text": "P", "fraction": 0.5},
                {"id": "x", "text": "Sand", "fraction": -1},
            ],
        },
    )
    assert score("multichoice", data, {"choices": ["n", "p"]}).fraction == 1.0
    assert score("multichoice", data, {"choices": ["n"]}).fraction == 0.5
    assert score("multichoice", data, {"choices": ["n", "x"]}).fraction == 0.0
    assert score("multichoice", data, {"choices": ["n", "p", "x"]}).fraction == 0.0
    assert marking.correct_response("multichoice", data) == {"choices": ["n", "p"]}


def test_multichoice_settings_are_checked():
    with pytest.raises(QuestionDataError, match="full mark"):
        q("multichoice", {"single": True, "choices": [{"text": "a", "fraction": 0.5}, {"text": "b"}]})
    with pytest.raises(QuestionDataError, match="add up to 1"):
        q("multichoice", {"single": False, "choices": [{"text": "a", "fraction": 0.5}, {"text": "b"}]})
    with pytest.raises(QuestionDataError, match="at least 2"):
        q("multichoice", {"choices": [{"text": "a", "fraction": 1}]})
    with pytest.raises(QuestionDataError, match="used twice"):
        q("multichoice", {"choices": [{"id": "a", "text": "x", "fraction": 1}, {"id": "a", "text": "y"}]})
    with pytest.raises(QuestionDataError, match="from -1 to 1"):
        q("multichoice", {"choices": [{"text": "x", "fraction": 2}, {"text": "y", "fraction": 1}]})
    with pytest.raises(QuestionDataError):
        validate_response("multichoice", q("multichoice", SINGLE), {"choice": "z"})


# --- true or false --------------------------------------------------------------------------------------


def test_true_false():
    data = q("truefalse", {"correct": False, "feedback_true": "No.", "feedback_false": "Right."})
    assert score("truefalse", data, {"answer": False}).fraction == 1.0
    wrong = score("truefalse", data, {"answer": True})
    assert wrong.fraction == 0.0 and wrong.feedback == "No."
    with pytest.raises(QuestionDataError):
        q("truefalse", {"correct": "yes"})
    with pytest.raises(QuestionDataError):
        validate_response("truefalse", data, {"answer": "true"})


# --- matching and ordering ------------------------------------------------------------------------------


def test_matching_gives_a_share_per_pair():
    data = q(
        "matching",
        {
            "pairs": [
                {"prompt": "Maize", "answer": "Cereal"},
                {"prompt": "Bora", "answer": "Legume"},
                {"prompt": "Cassava", "answer": "Root crop"},
            ],
            "extra_answers": ["Fruit"],
        },
    )
    full = {"matches": {"a": "Cereal", "b": "Legume", "c": "Root crop"}}
    assert score("matching", data, full).fraction == 1.0
    two = score("matching", data, {"matches": {"a": "Cereal", "b": "Legume", "c": "Fruit"}})
    assert two.fraction == pytest.approx(2 / 3, abs=1e-6) and two.parts == {"a": True, "b": True, "c": False}
    with pytest.raises(QuestionDataError):
        validate_response("matching", data, {"matches": {"a": "Vegetable"}})
    public = schemas.public_data(
        "matching", data, schemas.make_layout("matching", data, shuffle=True, rng=random)
    )
    assert sorted(public["answers"]) == ["Cereal", "Fruit", "Legume", "Root crop"]
    assert "answer" not in public["prompts"][0]


def test_ordering_absolute_position_and_all_or_nothing():
    items = [{"id": "1", "text": "Plough"}, {"id": "2", "text": "Harrow"}, {"id": "3", "text": "Sow"}]
    data = q("ordering", {"items": items})
    assert score("ordering", data, {"order": ["1", "2", "3"]}).fraction == 1.0
    assert score("ordering", data, {"order": ["1", "3", "2"]}).fraction == pytest.approx(1 / 3, abs=1e-6)
    strict = q("ordering", {"items": items, "grading": "all_or_nothing"})
    assert score("ordering", strict, {"order": ["1", "3", "2"]}).fraction == 0.0
    with pytest.raises(QuestionDataError):
        validate_response("ordering", data, {"order": ["1", "2"]})
    layout = schemas.make_layout("ordering", data, shuffle=True, rng=random.Random(4))  # noqa: S311
    assert layout["items"] != ["1", "2", "3"]  # never shown already in order


# --- short answer ---------------------------------------------------------------------------------------


def test_short_answer_case_wildcards_and_partial_credit():
    data = q(
        "shortanswer",
        {
            "answers": [
                {"text": "photosynthesis", "fraction": 1, "feedback": "Correct."},
                {"text": "photo*", "fraction": 0.5, "feedback": "Check the spelling."},
            ]
        },
    )
    assert score("shortanswer", data, {"text": "  Photosynthesis "}).fraction == 1.0
    partial = score("shortanswer", data, {"text": "photosinthesis"})
    assert partial.fraction == 0.5 and partial.feedback == "Check the spelling."
    assert score("shortanswer", data, {"text": "respiration"}).fraction == 0.0
    assert score("shortanswer", data, {"text": "   "}).fraction == 0.0
    sensitive = q("shortanswer", {"answers": [{"text": "NaCl"}], "case_sensitive": True})
    assert score("shortanswer", sensitive, {"text": "NaCl"}).fraction == 1.0
    assert score("shortanswer", sensitive, {"text": "nacl"}).fraction == 0.0


def test_wildcard_rules():
    assert marking.wildcard_match("*cell*", "the plant cell wall")
    assert marking.wildcard_match("a\\*b", "a*b")
    assert not marking.wildcard_match("a\\*b", "axb")
    assert not marking.wildcard_match("cell", "cells")
    assert marking.wildcard_match("c.ll", "c.ll") and not marking.wildcard_match("c.ll", "cell")


# --- numerical ------------------------------------------------------------------------------------------


def test_numerical_tolerance_units_and_any_number():
    data = q(
        "numerical",
        {
            "answers": [
                {"value": 2.5, "tolerance": 0.1, "fraction": 1, "feedback": "Right."},
                {"value": 25, "tolerance": 0, "fraction": 0.5, "feedback": "Out by ten."},
            ],
            "units": [{"unit": "t/ha", "multiplier": 1}, {"unit": "kg/ha", "multiplier": 1000}],
            "unit_mode": "required",
            "unit_penalty": 0.2,
        },
    )
    assert score("numerical", data, {"value": "2.45", "unit": "t/ha"}).fraction == 1.0
    assert score("numerical", data, {"value": "2500", "unit": "kg/ha"}).fraction == 1.0
    assert score("numerical", data, {"value": "2.5 t/ha"}).fraction == 1.0
    assert score("numerical", data, {"value": "2,5", "unit": "t/ha"}).fraction == 1.0
    missing = score("numerical", data, {"value": "2.5"})
    assert missing.fraction == pytest.approx(0.8) and "unit" in missing.feedback
    assert score("numerical", data, {"value": "25", "unit": "t/ha"}).fraction == 0.5
    assert score("numerical", data, {"value": "2.7", "unit": "t/ha"}).fraction == 0.0
    assert score("numerical", data, {"value": "about two"}).fraction == 0.0
    anything = q("numerical", {"answers": [{"value": None, "fraction": 1}]})
    assert score("numerical", anything, {"value": "-7"}).fraction == 1.0
    plain = q("numerical", {"answers": [{"value": "9.81", "tolerance": 0.01}]})
    assert plain["unit_mode"] == "none" and score("numerical", plain, {"value": 9.8}).fraction == 1.0
    assert marking.correct_response("numerical", data) == {"value": "2.5", "unit": "t/ha"}
    with pytest.raises(QuestionDataError, match="tolerance"):
        q("numerical", {"answers": [{"value": 1, "tolerance": -1}]})
    with pytest.raises(QuestionDataError, match="required unit"):
        q("numerical", {"answers": [{"value": 1}], "unit_mode": "required"})


def test_parse_number():
    assert schemas.parse_number("1,250.5") == 1250.5
    assert schemas.parse_number("0,5") == 0.5
    assert schemas.parse_number("6.02e23") == 6.02e23
    assert schemas.parse_number("12abc") is None
    assert schemas.parse_number("") is None


# --- fill in the blanks ---------------------------------------------------------------------------------


CLOZE_TEXT = "Plants take in [[1]] through the leaves; pH of [[2]] is neutral; soil type: [[3]]."
CLOZE = {
    "gaps": {
        "1": {"answers": [{"text": "carbon dioxide"}, {"text": "CO2", "fraction": 1}]},
        "2": {"kind": "numerical", "answers": [{"value": 7, "tolerance": 0.2}], "weight": 2},
        "3": {
            "kind": "choice",
            "answers": [{"text": "Clay", "fraction": 1}, {"text": "Moon dust", "fraction": 0}],
        },
    }
}


def test_cloze_marks_each_gap_by_weight():
    data = q("cloze", CLOZE, CLOZE_TEXT)
    full = score("cloze", data, {"gaps": {"1": "co2", "2": "7.1", "3": "Clay"}})
    assert full.fraction == 1.0
    half = score("cloze", data, {"gaps": {"1": "oxygen", "2": "7", "3": "Moon dust"}})
    assert half.fraction == pytest.approx(0.5) and half.parts == {"1": 0, "2": 1.0, "3": 0}
    assert score("cloze", data, {"gaps": {}}).fraction == 0.0
    public = schemas.public_data("cloze", data)
    assert public["gaps"]["3"]["choices"] == ["Clay", "Moon dust"] and "answers" not in public["gaps"]["1"]
    assert marking.correct_response("cloze", data)["gaps"] == {"1": "carbon dioxide", "2": "7", "3": "Clay"}


def test_cloze_gaps_must_match_the_text():
    with pytest.raises(QuestionDataError, match="do not match"):
        q("cloze", CLOZE, "Only [[1]] here.")
    with pytest.raises(QuestionDataError, match="needs gaps"):
        q("cloze", {"gaps": {}}, "No gaps.")
    data = q("cloze", CLOZE, CLOZE_TEXT)
    with pytest.raises(QuestionDataError):
        validate_response("cloze", data, {"gaps": {"9": "x"}})


# --- essay and file -------------------------------------------------------------------------------------


def test_essay_and_file_go_to_a_person_unless_blank():
    essay = q("essay", {"min_words": 50, "max_words": 300})
    result = score("essay", essay, {"text": "Crop rotation breaks pest cycles."})
    assert result.fraction is None and result.needs_manual
    assert score("essay", essay, {"text": "  "}).fraction == 0.0
    assert marking.correct_response("essay", essay) is None
    with pytest.raises(QuestionDataError, match="more than"):
        q("essay", {"min_words": 10, "max_words": 5})
    upload = q("file", {"allowed_extensions": [".PDF", "jpg"], "max_size_mb": 5})
    assert upload["allowed_extensions"] == ["jpg", "pdf"]
    assert marking.mark("file", upload, {"filename": "report.pdf"}).needs_manual
    with pytest.raises(QuestionDataError, match="not accepted"):
        q("file", {"allowed_extensions": ["exe"]})
    with pytest.raises(QuestionDataError, match="max_size_mb"):
        q("file", {"max_size_mb": 500})
    with pytest.raises(QuestionDataError, match="file endpoint"):
        validate_response("file", upload, {"filename": "x.pdf"})


# --- label a diagram ------------------------------------------------------------------------------------


DIAGRAM = {
    "image_width": 400,
    "image_height": 300,
    "labels": [
        {"id": "root", "text": "Root"},
        {"id": "leaf", "text": "Leaf"},
        {"id": "stem", "text": "Stem"},
    ],
    "zones": [
        {"id": "z1", "label": "root", "shape": "rect", "x": 150, "y": 220, "w": 100, "h": 60},
        {"id": "z2", "label": "leaf", "shape": "circle", "x": 300, "y": 60, "r": 40},
        {
            "id": "z3",
            "label": "stem",
            "shape": "polygon",
            "points": [[190, 100], [210, 100], [210, 200], [190, 200]],
        },
    ],
}


def test_drop_zone_diagram_marks_zone_by_zone_and_hides_the_answers():
    data = q("image_label", DIAGRAM)
    assert score("image_label", data, {"zones": {"z1": "root", "z2": "leaf", "z3": "stem"}}).fraction == 1.0
    one = score("image_label", data, {"zones": {"z1": "root", "z2": "stem"}})
    assert one.fraction == pytest.approx(1 / 3, abs=1e-6)
    public = schemas.public_data("image_label", data)
    assert all("label" not in z for z in public["zones"]) and len(public["labels"]) == 3
    with pytest.raises(QuestionDataError):
        validate_response("image_label", data, {"zones": {"z9": "root"}})


def test_marker_diagram_uses_coordinates_and_penalises_scattering():
    data = q("image_label", {**DIAGRAM, "mode": "markers"})
    right = [
        {"label": "root", "x": 200, "y": 250},
        {"label": "leaf", "x": 310, "y": 70},
        {"label": "stem", "x": 200, "y": 150},
    ]
    assert score("image_label", data, {"placements": right}).fraction == 1.0
    assert score("image_label", data, {"placements": right[:2]}).fraction == pytest.approx(2 / 3, abs=1e-6)
    scattered = right + [{"label": "root", "x": 10, "y": 10}]
    assert score("image_label", data, {"placements": scattered}).fraction == pytest.approx(2 / 3, abs=1e-6)
    assert "zones" not in schemas.public_data("image_label", data)
    assert score("image_label", data, marking.correct_response("image_label", data)).fraction == 1.0


def test_diagram_settings_are_checked():
    with pytest.raises(QuestionDataError, match="not one of the labels"):
        q("image_label", {**DIAGRAM, "zones": [{"id": "z", "label": "bark", "x": 1, "y": 1, "w": 1, "h": 1}]})
    with pytest.raises(QuestionDataError, match="width and height"):
        q("image_label", {**DIAGRAM, "image_width": 0})
    with pytest.raises(QuestionDataError, match="polygon"):
        q("image_label", {**DIAGRAM, "zones": [{"label": "root", "shape": "polygon", "points": [[1, 1]]}]})


def test_point_in_zone_shapes():
    assert marking.point_in_zone({"shape": "rect", "x": 0, "y": 0, "w": 10, "h": 10}, 10, 0)
    assert not marking.point_in_zone({"shape": "circle", "x": 0, "y": 0, "r": 5}, 4, 4)
    triangle = {"shape": "polygon", "points": [[0, 0], [10, 0], [0, 10]]}
    assert marking.point_in_zone(triangle, 2, 2) and not marking.point_in_zone(triangle, 8, 8)


# --- every type -----------------------------------------------------------------------------------------


SAMPLES = {
    "multichoice": ("Q", SINGLE),
    "truefalse": ("Q", {"correct": True}),
    "matching": ("Q", {"pairs": [{"prompt": "a", "answer": "1"}, {"prompt": "b", "answer": "2"}]}),
    "ordering": ("Q", {"items": [{"text": "a"}, {"text": "b"}]}),
    "shortanswer": ("Q", {"answers": [{"text": "x"}]}),
    "numerical": ("Q", {"answers": [{"value": 1}]}),
    "cloze": (CLOZE_TEXT, CLOZE),
    "image_label": ("Q", DIAGRAM),
}


@pytest.mark.parametrize("qtype", sorted(SAMPLES))
def test_the_right_answer_always_earns_full_marks(qtype):
    text, raw = SAMPLES[qtype]
    data = q(qtype, raw, text)
    right = marking.correct_response(qtype, data)
    assert marking.mark(qtype, data, validate_response(qtype, data, right)).fraction == 1.0


@pytest.mark.parametrize("qtype", sorted(schemas.QTYPES))
def test_public_data_never_carries_fractions_or_feedback(qtype):
    text, raw = SAMPLES.get(qtype, ("Q", {}))
    data = q(qtype, raw, text)
    flat = repr(schemas.public_data(qtype, data))
    for secret in ("fraction", "feedback", "'correct'", "'answer'", "grader_info", "'label':"):
        assert secret not in flat


def test_unknown_type_and_bad_settings():
    with pytest.raises(QuestionDataError, match="Unknown"):
        validate_question("calculated", "x", {})
    with pytest.raises(QuestionDataError, match="object"):
        validate_question("essay", "x", ["not", "a", "dict"])
    with pytest.raises(QuestionDataError, match="object"):
        validate_response("essay", q("essay", {}), "text")
