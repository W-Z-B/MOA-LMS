"""Reading and writing WebVTT captions (item 4.06): what a lecturer puts up, and what they correct."""

import pytest

from video import captions


def test_a_file_is_read_cue_by_cue_without_its_markup():
    text = (
        "\ufeffWEBVTT - lecture one\r\n\r\nNOTE written by hand\r\n\r\nSTYLE\r\n::cue { color: red }\r\n\r\n"
        "intro\r\n00:00:01.000 --> 00:00:04.500 align:start\r\n"
        "<v Lecturer>Good <b>morning</b> &amp; welcome\r\n\r\n"
        "01:02.250 --> 01:05.000\r\nSoil <script>x()</script>pH\r\n"
    )
    cues = captions.parse(text.encode("utf-8"))
    assert cues == [
        captions.Cue(1.0, 4.5, "Good morning & welcome"),
        captions.Cue(62.25, 65.0, "Soil x()pH"),
    ]


@pytest.mark.parametrize(
    ("data", "says"),
    [
        (b"1\n00:00:01.000 --> 00:00:02.000\nHi\n", "first line must be WEBVTT"),
        (b"WEBVTT\n\nnot a timing\nnor this\n", "timing cannot be read"),
        (b"WEBVTT\n\n00:00:05.000 --> 00:00:02.000\nBackwards\n", "must end after it starts"),
        (b"WEBVTT\n\nNOTE only a note\n", "has no cues"),
        (b"WEBVTT\n\n\xff\xfe\n", "UTF-8"),
        (b"WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n" + b"x" * 600 + b"\n", "at most 500 characters"),
        (b"WEBVTT\n" + b" " * captions.MAX_BYTES, "larger than 1 MB"),
    ],
)
def test_a_file_that_is_not_captions_is_refused_in_words(data, says):
    with pytest.raises(captions.CaptionError, match=says):
        captions.parse(data)


def test_too_many_cues_are_refused(monkeypatch):
    monkeypatch.setattr(captions, "MAX_CUES", 2)
    cue = "00:00:01.000 --> 00:00:02.000\nHi\n\n"
    with pytest.raises(captions.CaptionError, match="at most 2 cues"):
        captions.parse("WEBVTT\n\n" + cue * 3)
    with pytest.raises(captions.CaptionError, match="at most 2 cues"):
        captions.from_rows([{"start": 0, "end": 1, "text": "a"}] * 3)


def test_corrected_cues_are_sorted_emptied_ones_dropped_and_written_safely():
    cues = captions.from_rows(
        [
            {"start": 5, "end": 6.5, "text": "Second --> line <i>here</i>"},
            {"start": 0.5, "end": 2, "text": "First\n\nparagraph"},
            {"start": 3, "end": 4, "text": "   "},
        ]
    )
    assert [c.start for c in cues] == [0.5, 5]
    written = captions.write(cues)
    assert written.startswith("WEBVTT\n\n00:00:00.500 --> 00:00:02.000\nFirst\nparagraph\n\n")
    assert "Second --&gt; line here" in written
    assert captions.parse(written)[1].text == "Second --> line here"
    assert captions.stamp(3725.04) == "01:02:05.040"


def test_corrected_cues_must_say_something():
    with pytest.raises(captions.CaptionError, match="at least one"):
        captions.from_rows([{"start": 0, "end": 1, "text": ""}])
