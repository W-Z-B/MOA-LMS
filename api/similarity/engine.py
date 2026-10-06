"""How work is compared (item 3.20; ADR 0021 says why this method).

1. The text is normalised: quotations are taken out (a passage in quotation marks is the student saying it
   is someone else's), then it is split into words, compared without case or punctuation.
2. Every run of K words (a shingle) is hashed. The hashes of the assignment's own instructions are left out,
   so copying the question is never counted.
3. Winnowing (Schleimer, Wilkerson and Aiken, 2003; the method of MOSS) keeps the smallest hash of every
   window of W shingles. That keeps about 2/(W+1) of them and guarantees that any shared passage of at least
   W + K - 1 words leaves at least one shared fingerprint. Kept fingerprints go in an indexed table.
4. A new document looks up its fingerprints in that index: the documents that share the most are the
   candidates. Each candidate is then compared in full, shingle by shingle, to find the passages exactly.

All of it runs on GSA's server; nothing leaves it.
"""

import hashlib
import re
from dataclasses import dataclass, field

from django.utils.html import strip_tags

K = 5  # words in a shingle
W = 8  # shingles in a winnowing window: shared passages of 12 words or more are always found
MAX_CANDIDATES = 20  # documents compared in full for one check
MIN_SHARED_FINGERPRINTS = 2  # fewer shared fingerprints than this is not worth a full comparison
MIN_PASSAGE_WORDS = 8  # shorter shared runs are common phrases, not passages
MAX_PASSAGES = 25  # shown for one match
MAX_PASSAGE_CHARS = 1500

WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)*")
# Text in double quotation marks of any style, up to a long paragraph: an unbalanced mark takes nothing.
QUOTED = re.compile(r"[\"“”„«»]([^\"“”„«»]{1,1500})[\"“”„«»]")


def without_quotations(text: str) -> str:
    return QUOTED.sub(" ", text)


def words_of(text: str) -> list[str]:
    """The words of a text, quotations taken out, as written (case kept for showing passages)."""
    return WORD.findall(without_quotations(text))


def _key(words: list[str]) -> list[str]:
    return [w.casefold().replace("’", "'") for w in words]


def _hash(run: list[str]) -> int:
    digest = hashlib.blake2b(" ".join(run).encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)  # fits PostgreSQL's bigint


def shingles(words: list[str]) -> list[int]:
    """The hash of every run of K words, in order; shingle i covers words i to i + K - 1."""
    keys = _key(words)
    return [_hash(keys[i : i + K]) for i in range(len(keys) - K + 1)]


def winnow(hashes: list[int], window: int = W) -> list[tuple[int, int]]:
    """(hash, position) of the smallest hash in every window, the rightmost on a tie, each kept once."""
    if not hashes:
        return []
    if len(hashes) <= window:
        smallest = min(range(len(hashes)), key=lambda i: (hashes[i], -i))
        return [(hashes[smallest], smallest)]
    kept, last = [], -1
    for start in range(len(hashes) - window + 1):
        chosen = min(range(start, start + window), key=lambda i: (hashes[i], -i))
        if chosen != last:
            kept.append((hashes[chosen], chosen))
            last = chosen
    return kept


def instruction_hashes(instructions: str) -> set[int]:
    """Every shingle of the assignment's own instructions: never counted as shared."""
    return set(shingles(words_of(strip_tags(instructions or ""))))


@dataclass
class Comparison:
    """What document A shares with document B, from A's side and from B's."""

    shared_a: int = 0
    shared_b: int = 0
    ranges_a: list[list[int]] = field(default_factory=list)
    ranges_b: list[list[int]] = field(default_factory=list)
    passages: list[dict] = field(default_factory=list)  # {"a": [start, end], "b": [start, end]}


def _merge(ranges: list[list[int]]) -> list[list[int]]:
    merged: list[list[int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def covered(ranges: list[list[int]]) -> int:
    return sum(end - start for start, end in _merge(ranges))


def compare(a_words: list[str], b_words: list[str], excluded: set[int] | None = None) -> Comparison:
    """Find every passage A and B share: runs of shingles that follow on in both, at least
    MIN_PASSAGE_WORDS long. Ranges are [start, end) word positions."""
    excluded = excluded or set()
    a_hashes, b_hashes = shingles(a_words), shingles(b_words)
    where_b: dict[int, list[int]] = {}
    for j, value in enumerate(b_hashes):
        if value not in excluded:
            places = where_b.setdefault(value, [])
            if len(places) < 50:  # a run repeated more often than this is boilerplate, not a passage
                places.append(j)
    runs: dict[tuple[int, int], list[int]] = {}  # (last i, last j) -> [first i, first j, last i, last j]
    for i, value in enumerate(a_hashes):
        for j in where_b.get(value, ()):
            run = runs.pop((i - 1, j - 1), None)
            run = [run[0], run[1], i, j] if run else [i, j, i, j]
            runs[(i, j)] = run
    passages = []
    for first_i, first_j, last_i, last_j in runs.values():
        length = last_i - first_i + K
        if length >= MIN_PASSAGE_WORDS:
            passages.append({"a": [first_i, last_i + K], "b": [first_j, last_j + K]})
    passages.sort(key=lambda p: (-(p["a"][1] - p["a"][0]), p["a"][0]))
    result = Comparison(passages=passages)
    result.ranges_a = _merge([p["a"] for p in passages])
    result.ranges_b = _merge([p["b"] for p in passages])
    result.shared_a, result.shared_b = covered(result.ranges_a), covered(result.ranges_b)
    return result


def passage_text(words: list[str], span: list[int]) -> str:
    text = " ".join(words[span[0] : span[1]])
    return text if len(text) <= MAX_PASSAGE_CHARS else text[: MAX_PASSAGE_CHARS - 1] + "…"
