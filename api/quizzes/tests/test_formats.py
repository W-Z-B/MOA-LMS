"""Moodle XML, GIFT and QTI 2.1 import and export. Pure: no database."""
# ruff: noqa: E501 - fixture files keep their natural line lengths

import io
import zipfile
from types import SimpleNamespace

import pytest

from quizzes import formats, marking
from quizzes.schemas import validate_question

MOODLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<quiz>
  <question type="category"><category><text>$course$/top/Soils/Horizons</text></category></question>
  <question type="multichoice">
    <name><text>Topsoil</text></name>
    <questiontext format="html"><text><![CDATA[<p>Which horizon is topsoil?</p>]]></text></questiontext>
    <generalfeedback format="html"><text>The A horizon.</text></generalfeedback>
    <defaultgrade>2.0000000</defaultgrade>
    <single>true</single><shuffleanswers>true</shuffleanswers>
    <answer fraction="100" format="html"><text>A</text><feedback format="html"><text>Yes</text></feedback></answer>
    <answer fraction="0" format="html"><text>C</text><feedback format="html"><text>No</text></feedback></answer>
    <tags><tag><text>soil</text></tag></tags>
  </question>
  <question type="truefalse">
    <name><text>Clay holds water</text></name>
    <questiontext format="html"><text>Clay holds water well.</text></questiontext>
    <answer fraction="100" format="moodle_auto_format"><text>true</text><feedback><text>Right</text></feedback></answer>
    <answer fraction="0" format="moodle_auto_format"><text>false</text><feedback><text>Wrong</text></feedback></answer>
  </question>
  <question type="shortanswer">
    <name><text>Process</text></name>
    <questiontext format="html"><text>Name the process.</text></questiontext>
    <usecase>0</usecase>
    <answer fraction="100"><text>photosynthesis</text><feedback><text></text></feedback></answer>
    <answer fraction="50"><text>photo*</text><feedback><text>Spelling</text></feedback></answer>
  </question>
  <question type="numerical">
    <name><text>Yield</text></name>
    <questiontext format="html"><text>Yield in t/ha?</text></questiontext>
    <answer fraction="100"><text>2.5</text><tolerance>0.1</tolerance><feedback><text></text></feedback></answer>
    <units><unit><multiplier>1</multiplier><unit_name>t/ha</unit_name></unit>
           <unit><multiplier>1000</multiplier><unit_name>kg/ha</unit_name></unit></units>
    <unitgradingtype>1</unitgradingtype><unitpenalty>0.2</unitpenalty><showunits>0</showunits>
  </question>
  <question type="matching">
    <name><text>Crops</text></name>
    <questiontext format="html"><text>Match.</text></questiontext>
    <subquestion format="html"><text>Maize</text><answer><text>Cereal</text></answer></subquestion>
    <subquestion format="html"><text>Bora</text><answer><text>Legume</text></answer></subquestion>
    <subquestion format="html"><text></text><answer><text>Fruit</text></answer></subquestion>
  </question>
  <question type="essay">
    <name><text>Rotation</text></name>
    <questiontext format="html"><text>Explain crop rotation.</text></questiontext>
    <responseformat>editor</responseformat>
    <graderinfo format="html"><text>Look for pest cycles.</text></graderinfo>
  </question>
  <question type="essay">
    <name><text>Report upload</text></name>
    <questiontext format="html"><text>Upload your field report.</text></questiontext>
    <responseformat>noinline</responseformat><attachments>1</attachments><attachmentsrequired>1</attachmentsrequired>
    <filetypeslist>.pdf,.docx,.exe</filetypeslist>
  </question>
  <question type="cloze">
    <name><text>Gaps</text></name>
    <questiontext format="html"><text>Plants need {1:SHORTANSWER:=water#Yes~%50%H2O} and pH {2:NUMERICAL:=7:0.5}
     in {1:MULTICHOICE:=soil~moon dust}.</text></questiontext>
  </question>
  <question type="ordering">
    <name><text>Steps</text></name>
    <questiontext format="html"><text>Order the steps.</text></questiontext>
    <answer fraction="1"><text>Plough</text></answer>
    <answer fraction="2"><text>Harrow</text></answer>
    <answer fraction="3"><text>Sow</text></answer>
  </question>
  <question type="description">
    <name><text>Intro</text></name>
    <questiontext format="html"><text>Read this first.</text></questiontext>
  </question>
  <question type="calculated">
    <name><text>Formula</text></name>
    <questiontext format="html"><text>{a} + {b}</text></questiontext>
  </question>
</quiz>"""


def by_name(result):
    return {q.name: q for q in result.questions}


def test_moodle_xml_import_covers_the_main_types():
    result = formats.parse("moodle_xml", MOODLE_XML.encode())
    found = by_name(result)
    assert {q.qtype for q in result.questions} == {
        "multichoice", "truefalse", "shortanswer", "numerical", "matching", "essay", "file", "cloze", "ordering",
    }  # fmt: skip
    assert {s["name"]: s["reason"] for s in result.skipped} == {
        "Intro": "A description is not a question.",
        "Formula": "The Moodle question type 'calculated' is not supported.",
    }
    topsoil = found["Topsoil"]
    assert topsoil.category_path == ["Soils", "Horizons"] and topsoil.default_mark == 2.0
    assert topsoil.tags == ["soil"] and topsoil.general_feedback == "The A horizon."
    assert "<p>Which horizon" in topsoil.text
    # Every imported record passes the same validation as a hand-made question.
    cleaned = {q.name: validate_question(q.qtype, q.text, q.data) for q in result.questions}
    assert cleaned["Topsoil"]["choices"][0] == {"id": "a", "text": "A", "fraction": 1.0, "feedback": "Yes"}
    assert cleaned["Clay holds water"]["correct"] is True
    assert cleaned["Yield"]["unit_mode"] == "required" and cleaned["Yield"]["units"][1]["multiplier"] == 1000
    assert cleaned["Crops"]["extra_answers"] == ["Fruit"]
    assert cleaned["Report upload"]["allowed_extensions"] == ["docx", "pdf"]
    assert cleaned["Rotation"]["grader_info"] == "Look for pest cycles."
    assert [i["text"] for i in cleaned["Steps"]["items"]] == ["Plough", "Harrow", "Sow"]
    gaps = found["Gaps"]
    assert gaps.text.count("[[") == 3
    assert cleaned["Gaps"]["gaps"]["2"]["answers"][0]["value"] == 7.0
    assert cleaned["Gaps"]["gaps"]["3"]["kind"] == "choice"
    right = marking.mark("cloze", cleaned["Gaps"], {"gaps": {"1": "Water", "2": "7.3", "3": "soil"}})
    assert right.fraction == 1.0


def test_moodle_xml_round_trip():
    result = formats.parse("moodle_xml", MOODLE_XML)
    items = []
    for parsed in result.questions:
        data = validate_question(parsed.qtype, parsed.text, parsed.data)
        question = SimpleNamespace(name=parsed.name, qtype=parsed.qtype, tags=parsed.tags)
        version = SimpleNamespace(text=parsed.text, data=data, general_feedback="", default_mark=1)
        items.append((question, version, parsed.category_path))
    xml, skipped = formats.export_moodle_xml(items)
    assert skipped == []
    again = formats.parse("moodle_xml", xml)
    assert sorted(q.name for q in again.questions) == sorted(q.name for q in result.questions)
    first, second = by_name(result), by_name(again)
    for name in first:
        a = validate_question(first[name].qtype, first[name].text, first[name].data)
        b = validate_question(second[name].qtype, second[name].text, second[name].data)
        assert a == b, name
    image = SimpleNamespace(name="Diagram", qtype="image_label", tags=[])
    _, skipped = formats.export_moodle_xml([(image, SimpleNamespace(), [])])
    assert skipped[0]["name"] == "Diagram"


@pytest.mark.parametrize(
    "payload",
    [
        '<?xml version="1.0"?><!DOCTYPE quiz [<!ENTITY a "aaaa">]><quiz>&a;</quiz>',
        '<!doctype quiz SYSTEM "http://example.com/x.dtd"><quiz/>',
        '<quiz><!ENTITY x "y"></quiz>',
    ],
)
def test_xml_with_a_dtd_or_entities_is_refused(payload):
    with pytest.raises(formats.FormatError, match="not accepted for safety"):
        formats.parse("moodle_xml", payload)
    with pytest.raises(formats.FormatError, match="not accepted for safety"):
        formats.parse_qti(payload.encode())


def test_unreadable_files():
    with pytest.raises(formats.FormatError, match="well-formed"):
        formats.parse("moodle_xml", "<quiz><question>")
    with pytest.raises(formats.FormatError, match="root element"):
        formats.parse("moodle_xml", "<questions/>")
    with pytest.raises(formats.FormatError, match="larger than 5 MB"):
        formats.parse("gift", b"x" * (formats.MAX_IMPORT_BYTES + 1))
    with pytest.raises(formats.FormatError, match="Unknown format"):
        formats.parse("blackboard", "")


GIFT = r"""
// Soil questions
$CATEGORY: $course$/top/Soils

::Topsoil::Which horizon is topsoil? {=A#Yes ~C#No ~%50%O}

::Clay::Clay holds water well. {T#It does hold water#Correct}

::Process::Name the process. {=photosynthesis =%50%photo*#Spelling}

::Pi::Pi to two places? {#3.14:0.005}

::Range::A number from 1 to 5. {#1..5}

::Crops::Match. {=Maize -> Cereal =Bora -> Legume = -> Fruit}

::Rotation::Explain crop rotation. {}

::Multi::Which are nutrients? {~%50%Nitrogen ~%50%Potash ~%-100%Sand}

The {=sun ~moon} gives plants energy.

::Escaped::Is 1\:2 a ratio\? {=yes \= ratio}

::Broken::No answer block here.
"""


def test_gift_import():
    result = formats.parse("gift", GIFT)
    found = by_name(result)
    assert found["Topsoil"].qtype == "multichoice" and found["Topsoil"].category_path == ["Soils"]
    topsoil = validate_question("multichoice", "x", found["Topsoil"].data)
    assert [(c["text"], c["fraction"], c["feedback"]) for c in topsoil["choices"]] == [
        ("A", 1.0, "Yes"), ("C", 0.0, "No"), ("O", 0.5, ""),
    ]  # fmt: skip
    clay = found["Clay"].data
    assert clay == {"correct": True, "feedback_true": "Correct", "feedback_false": "It does hold water"}
    assert found["Process"].qtype == "shortanswer" and found["Process"].data["answers"][1]["fraction"] == 0.5
    pi = validate_question("numerical", "x", found["Pi"].data)
    assert pi["answers"][0]["value"] == 3.14 and pi["answers"][0]["tolerance"] == 0.005
    ranged = validate_question("numerical", "x", found["Range"].data)
    assert ranged["answers"][0]["value"] == 3.0 and ranged["answers"][0]["tolerance"] == 2.0
    crops = validate_question("matching", "x", found["Crops"].data)
    assert crops["extra_answers"] == ["Fruit"] and crops["pairs"][1]["answer"] == "Legume"
    assert found["Rotation"].qtype == "essay"
    multi = validate_question("multichoice", "x", found["Multi"].data)
    assert multi["single"] is False
    missing_word = next(q for q in result.questions if "_____" in q.text)
    assert missing_word.text == "The _____ gives plants energy." and missing_word.qtype == "multichoice"
    escaped = found["Escaped"]
    assert escaped.text == "Is 1:2 a ratio\\?" or escaped.text.startswith("Is 1:2 a ratio")
    assert escaped.data["answers"][0]["text"] == "yes = ratio"
    assert [s["name"] for s in result.skipped] == ["Broken"]


def test_gift_round_trip():
    result = formats.parse("gift", GIFT)
    items = [
        (
            SimpleNamespace(name=q.name, qtype=q.qtype, tags=[]),
            SimpleNamespace(text=q.text, data=validate_question(q.qtype, q.text, q.data)),
            q.category_path,
        )
        for q in result.questions
    ]
    text, skipped = formats.export_gift(items)
    assert skipped == []
    again = by_name(formats.parse("gift", text))
    for question, version, _ in items:
        other = again[question.name]
        assert validate_question(other.qtype, other.text, other.data) == version.data, question.name


QTI_SINGLE = """<?xml version="1.0" encoding="UTF-8"?>
<assessmentItem xmlns="http://www.imsglobal.org/xsd/imsqti_v2p1" identifier="q1" title="Soil pH">
  <responseDeclaration identifier="RESPONSE" cardinality="single" baseType="identifier">
    <correctResponse><value>B</value></correctResponse>
  </responseDeclaration>
  <itemBody>
    <p>What is neutral pH?</p>
    <choiceInteraction responseIdentifier="RESPONSE" shuffle="true" maxChoices="1">
      <prompt>Choose one.</prompt>
      <simpleChoice identifier="A">5</simpleChoice>
      <simpleChoice identifier="B">7</simpleChoice>
      <simpleChoice identifier="C">9</simpleChoice>
    </choiceInteraction>
  </itemBody>
</assessmentItem>"""

QTI_MULTIPLE = """<assessmentItem xmlns="http://www.imsglobal.org/xsd/imsqti_v2p1" identifier="q2" title="Nutrients">
  <responseDeclaration identifier="RESPONSE" cardinality="multiple" baseType="identifier">
    <correctResponse><value>N</value><value>K</value></correctResponse>
  </responseDeclaration>
  <itemBody>
    <choiceInteraction responseIdentifier="RESPONSE" maxChoices="0">
      <prompt>Which are macronutrients?</prompt>
      <simpleChoice identifier="N">Nitrogen</simpleChoice>
      <simpleChoice identifier="K">Potassium</simpleChoice>
      <simpleChoice identifier="S">Sand</simpleChoice>
    </choiceInteraction>
  </itemBody>
</assessmentItem>"""

QTI_MAPPED = """<assessmentItem xmlns="http://www.imsglobal.org/xsd/imsqti_v2p1" identifier="q3" title="Mapped">
  <responseDeclaration identifier="R" cardinality="single" baseType="identifier">
    <correctResponse><value>A</value></correctResponse>
    <mapping defaultValue="0"><mapEntry mapKey="A" mappedValue="2"/><mapEntry mapKey="B" mappedValue="1"/></mapping>
  </responseDeclaration>
  <itemBody><choiceInteraction responseIdentifier="R" maxChoices="1">
    <simpleChoice identifier="A">Best</simpleChoice><simpleChoice identifier="B">Half</simpleChoice>
  </choiceInteraction></itemBody>
</assessmentItem>"""


def test_qti_multiple_choice_single_multiple_and_mapped():
    single = formats.parse("qti", QTI_SINGLE.encode()).questions[0]
    data = validate_question(single.qtype, single.text, single.data)
    assert single.name == "Soil pH" and "neutral pH" in single.text and "Choose one." in single.text
    assert marking.mark("multichoice", data, {"choice": "B"}).fraction == 1.0
    assert marking.mark("multichoice", data, {"choice": "A"}).fraction == 0.0
    multiple = formats.parse("qti", QTI_MULTIPLE).questions[0]
    data = validate_question(multiple.qtype, multiple.text, multiple.data)
    assert data["single"] is False
    assert marking.mark("multichoice", data, {"choices": ["N", "K"]}).fraction == 1.0
    assert marking.mark("multichoice", data, {"choices": ["N", "K", "S"]}).fraction == 0.5
    mapped = formats.parse("qti", QTI_MAPPED).questions[0]
    data = validate_question(mapped.qtype, mapped.text, mapped.data)
    assert [c["fraction"] for c in data["choices"]] == [1.0, 0.5]


def test_qti_package_zip_and_unsupported_items():
    unsupported = QTI_SINGLE.replace("choiceInteraction", "hotspotInteraction").replace("q1", "q9")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("imsmanifest.xml", "<manifest/>")
        package.writestr("items/q1.xml", QTI_SINGLE)
        package.writestr("items/q2.xml", QTI_MULTIPLE)
        package.writestr("items/q9.xml", unsupported)
        package.writestr("items/old.xml", "<questestinterop/>")
        package.writestr("items/bad.xml", '<!DOCTYPE x [<!ENTITY a "b">]><x/>')
    result = formats.parse("qti", buffer.getvalue(), "package.zip")
    assert sorted(q.name for q in result.questions) == ["Nutrients", "Soil pH"]
    reasons = {s["name"]: s["reason"] for s in result.skipped}
    assert "hotspotInteraction" in reasons["Soil pH"] or any("hotspot" in r for r in reasons.values())
    assert reasons["items/old.xml"] == "QTI 1.2 is not supported; export as QTI 2.1."
    assert "safety" in reasons["items/bad.xml"]


def test_qti_text_entry_and_extended_text():
    text_entry = QTI_SINGLE.replace(
        """<choiceInteraction responseIdentifier="RESPONSE" shuffle="true" maxChoices="1">
      <prompt>Choose one.</prompt>
      <simpleChoice identifier="A">5</simpleChoice>
      <simpleChoice identifier="B">7</simpleChoice>
      <simpleChoice identifier="C">9</simpleChoice>
    </choiceInteraction>""",
        '<textEntryInteraction responseIdentifier="RESPONSE"/>',
    ).replace("<value>B</value>", "<value>seven</value>")
    parsed = formats.parse("qti", text_entry).questions[0]
    assert parsed.qtype == "shortanswer" and parsed.data["answers"] == [{"text": "seven", "fraction": 1.0}]
    essay = text_entry.replace("textEntryInteraction", "extendedTextInteraction")
    assert formats.parse("qti", essay).questions[0].qtype == "essay"


def test_cloze_text_parser_handles_escapes_and_weights():
    text, gaps = formats.parse_cloze_text(r"Ratio {2:SA:=1\:2#ok} and {:MC:=a~b}")
    assert text == "Ratio [[1]] and [[2]]"
    assert gaps["1"]["weight"] == 2 and gaps["1"]["answers"][0]["text"] == "1:2"
    assert gaps["2"]["kind"] == "choice" and len(gaps["2"]["answers"]) == 2
    with pytest.raises(formats.FormatError, match="not supported"):
        formats.parse_cloze_text("{1:MULTIRESPONSE:=a~b}")
