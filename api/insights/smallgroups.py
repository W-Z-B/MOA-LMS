"""Small groups hidden in reports that leave a course (item 6.06, gap G3).

GSA's classes are small: a total or an average over three students tells a head of department, or anyone the
report is passed to, about those three. Every report that leaves a course passes its rows through hide_small
before they are shown or exported, so the rule is in one place and tested once.

A row's group is the number of people its figures are about. When it is above zero and below
REPORT_MIN_GROUP, the row's figures (and the size itself) are replaced by None and the row says it was
hidden. Zero is shown: nobody is described by it. When rows add up to a total that is shown, hiding a single
row is not enough, since it could be worked out by subtraction; the next smallest row is hidden with it.
"""

from collections.abc import Iterable

from django.conf import settings

HIDDEN = "hidden"


def minimum() -> int:
    return max(1, settings.REPORT_MIN_GROUP)


def too_small(size: int | None) -> bool:
    return size is not None and 0 < size < minimum()


def _hide(row: dict, size_key: str, fields: Iterable[str]) -> None:
    for name in (size_key, *fields):
        row[name] = None
    row[HIDDEN] = True


def hide_small(
    rows: list[dict], *, size_key: str, fields: Iterable[str], totalled: bool = False
) -> list[dict]:
    """Hide the figures of every row whose group is too small, in place, and return the rows.

    fields: the figures worked out from the group, hidden with it. totalled: the rows add up to a total
    shown beside them, so a lone hidden row takes the next smallest with it (complementary hiding).
    """
    fields = tuple(fields)
    hidden = 0
    for row in rows:
        row.setdefault(HIDDEN, False)
        if too_small(row.get(size_key)):
            _hide(row, size_key, fields)
            hidden += 1
    if totalled and hidden == 1:
        shown = [row for row in rows if not row[HIDDEN] and (row.get(size_key) or 0) > 0]
        if shown:
            _hide(min(shown, key=lambda row: row[size_key]), size_key, fields)
    return rows


def hide_total(total: dict, *, size_key: str, fields: Iterable[str]) -> dict:
    """The same rule for a single total row."""
    return hide_small([total], size_key=size_key, fields=fields)[0]
