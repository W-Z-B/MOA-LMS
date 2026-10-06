"""Page text: cleaning what the editor sends, and checking it is accessible (items 2.12 and 2.13).

A page body is stored as HTML, cleaned on the server against an allow-list whatever the editor sent:
headings (h2 to h4: the page title is the h1), paragraphs, lists, tables, bold and italic, links to web
addresses and e-mail only, images that are files on the LMS itself, code, quotations, and maths kept as
TeX in a `data-math` attribute (`<span data-math="...">` inline, `<div data-math="...">` displayed) for
the web app to draw with KaTeX. Anything else is removed, keeping its text.

An image must say what it shows (alternative text): a page with an image without it is refused. Other
accessibility problems are reported as warnings for the lecturer to fix.
"""

import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlsplit

import nh3

TAGS = {
    "h2",
    "h3",
    "h4",
    "p",
    "br",
    "ul",
    "ol",
    "li",
    "table",
    "caption",
    "thead",
    "tbody",
    "tfoot",
    "tr",
    "th",
    "td",
    "strong",
    "em",
    "a",
    "img",
    "code",
    "pre",
    "blockquote",
    "span",
    "div",
}
ATTRIBUTES = {
    "a": {"href", "title"},
    "img": {"src", "alt", "width", "height"},
    "th": {"scope", "colspan", "rowspan"},
    "td": {"colspan", "rowspan"},
    "ol": {"start"},
    "span": {"data-math"},
    "div": {"data-math"},
}
LINK_SCHEMES = {"http", "https", "mailto"}
# The only images a page may show: files put up on the LMS, fetched through the checked download link.
OWN_FILE = re.compile(r"^/api/v1/content/(\d+)/download/$")
SCOPES = {"row", "col", "rowgroup", "colgroup"}
MAX_TEX = 2000

# Link text that says nothing about where the link goes, for a screen-reader user listing the links.
VAGUE_LINK_TEXT = {"click here", "here", "click", "read more", "more", "link", "this link", "this", "go"}


def _keep(tag: str, attribute: str, value: str) -> str | None:
    """Decide each attribute the allow-list lets through: None removes it."""
    if attribute == "href":
        scheme = urlsplit(value.strip()).scheme.lower()
        return value.strip() if scheme in LINK_SCHEMES else None
    if attribute == "src":
        return value.strip() if OWN_FILE.match(value.strip()) else None
    if attribute in ("width", "height", "colspan", "rowspan", "start"):
        return value if value.isdigit() and len(value) <= 4 else None
    if attribute == "scope":
        return value if value in SCOPES else None
    if attribute == "data-math":
        return value[:MAX_TEX]
    return value


def clean(body: str) -> str:
    """The body with everything outside the allow-list removed. Safe to place in a page as it is."""
    return nh3.clean(
        body or "",
        tags=TAGS,
        clean_content_tags={"script", "style", "template", "iframe", "object", "noscript"},
        attributes=ATTRIBUTES,
        attribute_filter=_keep,
        url_schemes=LINK_SCHEMES,
        link_rel="noopener noreferrer",
        strip_comments=True,
    ).strip()


def text_to_html(text: str) -> str:
    """Plain text as HTML paragraphs: a blank line starts a new paragraph, a line break is kept."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", (text or "").replace("\r\n", "\n")) if p.strip()]
    return "".join(f"<p>{html.escape(p).replace(chr(10), '<br>')}</p>" for p in paragraphs)


def image_item_ids(body: str) -> set[int]:
    """Ids of the content items whose files a body shows as images."""
    return {int(m) for m in re.findall(r'<img[^>]*\ssrc="/api/v1/content/(\d+)/download/"', body or "")}


def replace_image_ids(body: str, mapping: dict[int, int]) -> str:
    """The body with images pointing at copies of the files, for content copied to another site."""

    def swap(match):
        old = int(match.group(1))
        return f"/api/v1/content/{mapping.get(old, old)}/download/"

    return re.sub(r"/api/v1/content/(\d+)/download/", swap, body or "")


@dataclass
class Issue:
    code: str
    detail: str
    severity: str = "warning"  # "error" refuses the page; "warning" is reported and saved

    def as_dict(self) -> dict:
        return {"code": self.code, "detail": self.detail, "severity": self.severity}


@dataclass
class _Table:
    rows: int = 0
    first_row_headers: bool = False
    has_head: bool = False


class _Reader(HTMLParser):
    """Walks a body once, noting what the accessibility check needs."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.images: list[tuple[str | None, str | None]] = []  # (src, alt)
        self.headings: list[int] = []  # levels in order
        self.links: list[tuple[str, str]] = []  # (href, text)
        self.tables: list[_Table] = []
        self._link: list[str] | None = None
        self._open_tables: list[_Table] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "img":
            self.images.append((attrs.get("src"), attrs.get("alt")))
            if self._link is not None and (attrs.get("alt") or "").strip():
                self._link[1] += " " + attrs["alt"]  # an image's text names the link it is in
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.headings.append(int(tag[1]))
        elif tag == "a":
            self._link = [attrs.get("href") or "", ""]
        elif tag == "table":
            self._open_tables.append(_Table())
        elif tag == "thead" and self._open_tables:
            self._open_tables[-1].has_head = True
        elif tag == "tr" and self._open_tables:
            self._open_tables[-1].rows += 1
        elif tag == "th" and self._open_tables and self._open_tables[-1].rows == 1:
            self._open_tables[-1].first_row_headers = True

    def handle_endtag(self, tag):
        if tag == "a" and self._link is not None:
            self.links.append((self._link[0], self._link[1]))
            self._link = None
        elif tag == "table" and self._open_tables:
            self.tables.append(self._open_tables.pop())

    def handle_data(self, data):
        if self._link is not None:
            self._link[1] += data


def check(body: str) -> list[Issue]:
    """Accessibility problems in a page body, in the order they appear by kind."""
    reader = _Reader()
    reader.feed(body or "")
    reader.close()
    issues: list[Issue] = []
    for number, (src, alt) in enumerate(reader.images, start=1):
        if alt is None or not alt.strip():
            issues.append(
                Issue(
                    "missing_alt",
                    f"Image {number} has no alternative text. Say in a few words what the image shows, "
                    "for students who cannot see it.",
                    "error",
                )
            )
        if not src:
            issues.append(
                Issue(
                    "image_not_on_lms",
                    f"Image {number} is not a file on this course. Put the picture up as a file first, then "
                    "add it to the page; pictures from other websites are not shown.",
                    "error",
                )
            )
    level = 1  # the page title
    for heading in reader.headings:
        if heading > level + 1:
            issues.append(
                Issue(
                    "heading_skipped",
                    f"A level {heading} heading follows a level {level} heading. Use headings in order "
                    "(the page title, then level 2, then level 3) so the page can be followed by structure.",
                )
            )
        level = heading
    for href, text in reader.links:
        words = " ".join(text.split()).strip().lower().rstrip(".")
        if not words:
            issues.append(
                Issue("empty_link", f"A link to {href or 'nowhere'} has no text. Say where the link goes.")
            )
        elif words in VAGUE_LINK_TEXT:
            issues.append(
                Issue(
                    "vague_link",
                    f'The link text "{text.strip()}" does not say where it goes. Use words such as '
                    '"Ministry of Agriculture planting guide" instead.',
                )
            )
    for number, table in enumerate(reader.tables, start=1):
        if not (table.has_head or table.first_row_headers):
            issues.append(
                Issue(
                    "table_without_headers",
                    f"Table {number} has no header row. Make the first row headers so each column is named.",
                )
            )
    return issues


def errors(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if i.severity == "error"]
