"""WebVTT captions: read a file a lecturer puts up, and write the cues a lecturer corrects in the browser.

Only what captions need is kept: each cue's start, end and text. Styling blocks, regions and cue settings
are dropped, and markup in cue text is reduced to plain text, so a caption file can never carry script
into the page. Times are seconds as floats.
"""

import re
from dataclasses import dataclass

MAX_BYTES = 1024 * 1024  # a two-hour lecture's captions are about 150 KB
MAX_CUES = 5000
MAX_CUE_CHARS = 500
TIME = r"(?:(\d{1,3}):)?(\d{2}):(\d{2})[.,](\d{3})"
TIMING = re.compile(rf"^\s*{TIME}\s+-->\s+{TIME}")
TAG = re.compile(r"<[^>]*>")


class CaptionError(ValueError):
    """Why a caption file or a set of cues was refused, in words for the lecturer."""


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str

    def as_dict(self) -> dict:
        return {"start": self.start, "end": self.end, "text": self.text}


def _seconds(hours, minutes, seconds, millis) -> float:
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def stamp(value: float) -> str:
    """12.5 -> 00:00:12.500"""
    millis = round(value * 1000)
    hours, rest = divmod(millis, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    seconds, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def _plain(text: str) -> str:
    text = TAG.sub("", text)
    return text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&nbsp;", " ").strip()


def parse(data: bytes | str) -> list[Cue]:
    """The cues of a WebVTT file. Raises CaptionError when it is not one."""
    if isinstance(data, bytes):
        if len(data) > MAX_BYTES:
            raise CaptionError("The captions file is larger than 1 MB.")
        try:
            data = data.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise CaptionError("Save the captions file as UTF-8 text and put it up again.") from error
    text = data.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    if not re.match(r"^WEBVTT(?:[ \t].*)?(?:\n|$)", text):
        raise CaptionError("This is not a WebVTT captions file: its first line must be WEBVTT.")
    cues: list[Cue] = []
    for block in re.split(r"\n{2,}", text)[1:]:
        lines = [line for line in block.split("\n") if line.strip() != ""]
        if not lines or lines[0].startswith(("NOTE", "STYLE", "REGION")):
            continue
        if not TIMING.match(lines[0]):
            lines = lines[1:]  # a cue identifier
        if not lines:
            continue
        timing = TIMING.match(lines[0])
        if not timing:
            raise CaptionError(f"A cue's timing cannot be read: “{lines[0][:60]}”.")
        start, end = _seconds(*timing.groups()[:4]), _seconds(*timing.groups()[4:])
        cues.append(_checked(start, end, "\n".join(_plain(line) for line in lines[1:])))
        if len(cues) > MAX_CUES:
            raise CaptionError(f"A captions file may have at most {MAX_CUES} cues.")
    if not cues:
        raise CaptionError("The captions file has no cues.")
    return cues


def _checked(start: float, end: float, text: str) -> Cue:
    if start < 0 or end <= start:
        raise CaptionError(f"A cue must end after it starts ({stamp(max(start, 0))}).")
    if len(text) > MAX_CUE_CHARS:
        raise CaptionError(f"A cue may have at most {MAX_CUE_CHARS} characters ({stamp(start)}).")
    return Cue(round(start, 3), round(end, 3), text.strip())


def from_rows(rows: list[dict]) -> list[Cue]:
    """Cues corrected in the browser: [{start, end, text}], in any order; empty text is dropped."""
    if len(rows) > MAX_CUES:
        raise CaptionError(f"Captions may have at most {MAX_CUES} cues.")
    cues = [_checked(float(r["start"]), float(r["end"]), _plain(str(r["text"]))) for r in rows]
    cues = sorted((c for c in cues if c.text), key=lambda c: (c.start, c.end))
    if not cues:
        raise CaptionError("Write at least one caption.")
    return cues


def write(cues: list[Cue]) -> str:
    """The cues as a WebVTT file."""
    blocks = ["WEBVTT"]
    for cue in cues:
        # A blank line would end the cue early; the escaping also keeps "-->" out of the text.
        text = re.sub(r"\n\s*\n", "\n", cue.text)
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        blocks.append(f"{stamp(cue.start)} --> {stamp(cue.end)}\n{text}")
    return "\n\n".join(blocks) + "\n"
