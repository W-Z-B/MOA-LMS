"""A paper quiz as PDFs (item 3.24): the question paper, the answer sheet and the marking key, for each
version. Built as in certificates.pdf: every piece of text is escaped plain text, and WeasyPrint is given
nothing it may fetch. Question text is kept as cleaned HTML in the bank; here it is reduced to plain words,
so pictures and formatting are not printed (the paper says so where a question has a picture)."""

import html
from html.parser import HTMLParser

from django.conf import settings

from certificates.pdf import _refuse

STYLE = """
@page { size: A4; margin: 15mm 14mm 16mm;
  @bottom-right { content: "Page " counter(page) " of " counter(pages);
  font: 8pt "DejaVu Sans", sans-serif; color: #555; } }
body { font: 10.5pt/1.4 "DejaVu Sans", sans-serif; color: #111; }
h1 { font-size: 15pt; margin: 0 0 2pt; }
.meta { color: #333; margin: 0 0 8pt; }
.who { border: 1pt solid #111; padding: 6pt 8pt; margin: 0 0 10pt; }
.who span { display: inline-block; width: 48%; }
.q { margin: 0 0 9pt; page-break-inside: avoid; }
.q .n { font-weight: bold; }
.q .m { float: right; color: #333; }
ol.opts { list-style: none; padding-left: 14pt; margin: 3pt 0 0; }
ol.opts li { margin: 1pt 0; }
.line { border-bottom: 0.6pt solid #555; height: 16pt; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 0.6pt solid #333; padding: 4pt 5pt; text-align: left; vertical-align: top; }
td.box { height: 20pt; }
.note { font-size: 9pt; color: #333; }
"""


class _Words(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.image = False

    def handle_starttag(self, tag, attrs):
        if tag in {"p", "br", "li", "div", "tr"}:
            self.parts.append(" ")
        if tag == "img":
            self.image = True

    def handle_data(self, data):
        self.parts.append(data)


def plain(markup: str) -> tuple[str, bool]:
    """The words of a piece of cleaned HTML, and whether it held a picture."""
    reader = _Words()
    reader.feed(markup or "")
    return " ".join("".join(reader.parts).split()), reader.image


def _e(text) -> str:
    return html.escape(str(text))


def _head(paper, label: str, what: str) -> str:
    quiz = paper.quiz
    return (
        f"<h1>{_e(quiz.title)}: {_e(what)}</h1>"
        f'<p class="meta">{_e(settings.CERTIFICATE_ORGANISATION)} · {_e(quiz.site.code)} · '
        f"{_e(paper.title)} · "
        f"{paper.sat_on:%d/%m/%Y} · Version {_e(label)}</p>"
    )


def _who() -> str:
    return (
        '<div class="who"><span>Name: ____________________</span>'
        "<span>Student number: __________</span></div>"
    )


def question_paper(paper, label: str, rows: list[dict]) -> str:
    body = [_head(paper, label, "question paper"), _who()]
    body.append(
        '<p class="note">Write your answers on the answer sheet for version '
        f"{_e(label)}. For a question with lettered options, write the letter.</p>"
    )
    for row in rows:
        words, picture = plain(row["text"])
        mark = row["max_mark"].rstrip("0").rstrip(".")
        parts = [
            f'<div class="q"><span class="m">[{_e(mark)} mark{"s" if mark != "1" else ""}]</span>'
            f'<span class="n">{row["number"]}.</span> {_e(words)}'
        ]
        if picture:
            parts.append(
                ' <span class="note">(This question has a picture: your lecturer will show it.)</span>'
            )
        if row["prompts"]:
            parts.append('<ol class="opts">')
            parts += [f"<li>({i}) {_e(plain(p)[0])}</li>" for i, p in enumerate(row["prompts"], start=1)]
            parts.append("</ol><p class='note'>Match each numbered line with one of:</p>")
        if row["options"]:
            parts.append('<ol class="opts">')
            parts += [f"<li>{o['letter']}. {_e(plain(o['text'])[0])}</li>" for o in row["options"]]
            parts.append("</ol>")
        parts.append(f'<p class="note">{_e(row["hint"])}.</p></div>' if row["qtype"] != "essay" else "</div>")
        body.append("".join(parts))
    return _page(paper, label, "".join(body))


def answer_sheet(paper, label: str, rows: list[dict]) -> str:
    body = [_head(paper, label, "answer sheet"), _who()]
    body.append("<table><tr><th>Question</th><th>How to answer</th><th>Your answer</th></tr>")
    for row in rows:
        how = "Write your answer on lined paper and attach it" if row["qtype"] == "essay" else row["hint"]
        body.append(f'<tr><td>{row["number"]}</td><td>{_e(how)}</td><td class="box"></td></tr>')
    body.append("</table>")
    return _page(paper, label, "".join(body))


def marking_key(paper, label: str, rows: list[dict]) -> str:
    body = [_head(paper, label, "marking key (teaching staff only)")]
    body.append("<table><tr><th>Question</th><th>Marks</th><th>Full-mark answer</th></tr>")
    for row in rows:
        key = row["key"] or "Marked by a person"
        body.append(f"<tr><td>{row['number']}</td><td>{_e(row['max_mark'])}</td><td>{_e(key)}</td></tr>")
    body.append("</table>")
    return _page(paper, label, "".join(body))


def _page(paper, label: str, body: str) -> str:
    return (
        f'<!doctype html><html lang="en-GB"><head><meta charset="utf-8">'
        f"<title>{_e(paper.quiz.title)}, version {_e(label)}</title><style>{STYLE}</style></head>"
        f"<body>{body}</body></html>"
    )


def render(page: str) -> bytes:
    from weasyprint import HTML

    return HTML(string=page, url_fetcher=_refuse).write_pdf()
