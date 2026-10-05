"""A certificate as a PDF (item 5.08, ported from the HRMS letters/pdf.py): the School's heading, the wording,
and its reference and check code on the page.

The page is built from escaped text only, and the PDF engine is given nothing it may fetch: no image, font,
style sheet or page from any address, so a certificate can never be made to reach out to a server. GSA's crest
is not yet held as artwork (neither the HRMS nor the LMS has it); the School's name stands as the heading, in
the crest's place, until it is supplied as an inline image.
"""

import html
import re

from django.conf import settings

STYLE = """
@page {
  size: A4 landscape;
  margin: 16mm;
  @bottom-center {
    content: "Reference REF";
    font: 8pt "DejaVu Sans", sans-serif;
    color: #555;
  }
}
body { font: 13pt/1.5 "DejaVu Serif", serif; color: #111; text-align: center; }
.frame { border: 3pt double #2f6b46; padding: 14mm 18mm; height: 150mm; }
.crest { font: bold 11pt "DejaVu Sans", sans-serif; letter-spacing: 3pt; color: #2f6b46; }
.org { font: bold 20pt "DejaVu Sans", sans-serif; color: #2f6b46; margin: 2pt 0 14pt; }
h1 { font: bold 26pt "DejaVu Serif", serif; margin: 0 0 12pt; }
.name { font: bold 22pt "DejaVu Serif", serif; margin: 8pt 0; }
p { margin: 0 0 8pt; }
ul { text-align: left; display: inline-block; margin: 0 0 8pt; }
.sign { margin-top: 18pt; font-size: 11pt; }
.foot { margin-top: 14pt; font: 8.5pt "DejaVu Sans", sans-serif; color: #444; }
"""
SAFE_REFERENCE = re.compile(r"^[A-Za-z0-9/-]{1,30}$")


def _refuse(url, *args, **kwargs):
    raise ValueError(f"A certificate fetches nothing, so not {url!r}.")


def page(*, template, values: dict[str, str], body_html: str, check_code: str) -> str:
    """The whole certificate as an HTML page, every piece of text escaped. The foot says how to check it is
    genuine: with its reference and code on the School's checking page (item 5.09)."""
    escape = html.escape
    reference = values["reference"]
    if not SAFE_REFERENCE.match(reference):
        raise ValueError("A reference holds only letters, digits, / and -.")
    signatory = "<br>".join(escape(v) for v in (template.signatory_name, template.signatory_title) if v)
    how = (
        f"To check that this certificate is genuine, go to {escape(settings.CERTIFICATE_CHECK_URL)} and "
        f"enter its reference, {escape(reference)}, and the code {escape(check_code)}."
    )
    expiry = f"<p>Valid until {escape(values['expires_on'])}.</p>" if values.get("expires_on") else ""
    return f"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<title>{escape(template.heading)}: {escape(values["full_name"])}</title>
<meta name="author" content="{escape(settings.CERTIFICATE_ORGANISATION)}">
<style>{STYLE.replace("REF", reference)}</style>
</head>
<body>
<div class="frame">
<div class="crest">GUYANA · AGRICULTURE</div>
<div class="org">{escape(settings.CERTIFICATE_ORGANISATION)}</div>
<h1>{escape(template.heading)}</h1>
<div class="name">{escape(values["full_name"])}</div>
{body_html}
{expiry}
<div class="sign">{signatory}</div>
<div class="foot">Reference {escape(reference)} · issued {escape(values["today"])}. {how}</div>
</div>
</body>
</html>"""


def render(html_page: str) -> bytes:
    from weasyprint import HTML  # loaded only when a certificate is made: it is large

    return HTML(string=html_page, url_fetcher=_refuse).write_pdf()
