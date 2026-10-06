"""IMS Common Cartridge 1.3: a course's content out, and a cartridge's content in (item 6.08).

Export. Modules become the cartridge's organisation; pages are web pages (wiki_content/), files keep their
original names (web_resources/), links are web links, packages are kept as their zip files, assignments are
web pages giving the instructions, due date and marks, and quizzes are QTI 1.2 assessments for the question
types QTI can carry (single and multiple choice, true or false, short answer, essay). A README.txt in the
cartridge lists what could not go in. Each item's licence and source travel in its resource's metadata.

Import. Every top-level part of the organisation becomes a module of the course, added after its present
modules; web pages become pages (cleaned as the editor's pages are, without their pictures), other files
become file items if they are kinds a course may hold, web links become links, and QTI assessments become
questions in a question bank of the course, in a category named after the assessment. Everything comes in as
a draft with its licence "not yet known", unless the cartridge says (as the LMS's own cartridges do).
Discussion topics, outside tools and anything else are listed as not imported.
"""

import posixpath
import re
import xml.etree.ElementTree as ET  # noqa: S405 - only builds XML; parsing goes through common.xml
import zipfile
from datetime import datetime

from django.utils import timezone

from courses.models import ContentItem
from interchange.common import Builder, ImportRefused, Report, ZipSource, child, children, local, text, xml
from quizzes import schemas
from quizzes.formats import ParsedQuestion, ParseResult

CP = "http://www.imsglobal.org/xsd/imsccv1p3/imscp_v1p1"
LOM = "http://ltsc.ieee.org/xsd/imsccv1p3/LOM/resource"
LOMM = "http://ltsc.ieee.org/xsd/imsccv1p3/LOM/manifest"
WL = "http://www.imsglobal.org/xsd/imsccv1p3/imswl_v1p3"
QTI_TYPE = "imsqti_xmlv1p2/imscc_xmlv1p3/assessment"
LICENCE_WORDS = dict(ContentItem.Licence.choices)
OPEN_WORDS = dict(ContentItem.OpenLicence.choices)


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")[:80] or "file"


def _page(title: str, body: str) -> str:
    from html import escape

    return (
        f'<!DOCTYPE html>\n<html lang="en-GB"><head><meta charset="utf-8"><title>{escape(title)}</title>'
        f"</head><body><h1>{escape(title)}</h1>\n{body}\n</body></html>\n"
    )


def rights_of(item) -> str:
    """The item's licence and source as words, written into the resource's metadata."""
    words = LICENCE_WORDS.get(item.licence, "")
    if item.licence == ContentItem.Licence.OPEN_LICENCE and item.open_licence:
        words = f"{words}: {OPEN_WORDS.get(item.open_licence, item.open_licence)}"
    return f"{words}. Source: {item.source}" if item.source else words


def licence_from(words: str) -> dict:
    """Back from rights_of; anything else is "not yet known", with the words kept as the source."""
    if not words:
        return {}
    head, _, source = words.partition(". Source: ")
    name, _, which = head.partition(": ")
    licence = next((code for code, label in LICENCE_WORDS.items() if label == name), None)
    if licence is None:
        return {"licence": ContentItem.Licence.UNKNOWN, "source": words[:2000]}
    found = {"licence": licence, "source": source[:2000]}
    if licence == ContentItem.Licence.OPEN_LICENCE:
        found["open_licence"] = next((c for c, label in OPEN_WORDS.items() if label == which), "other")
    return found


class _Manifest:
    def __init__(self, title: str):
        ET.register_namespace("", CP)
        ET.register_namespace("lomimscc", LOMM)
        ET.register_namespace("lom", LOM)
        self.root = ET.Element(f"{{{CP}}}manifest", {"identifier": "GSA_LMS_EXPORT"})
        metadata = ET.SubElement(self.root, f"{{{CP}}}metadata")
        ET.SubElement(metadata, f"{{{CP}}}schema").text = "IMS Common Cartridge"
        ET.SubElement(metadata, f"{{{CP}}}schemaversion").text = "1.3.0"
        lom = ET.SubElement(metadata, f"{{{LOMM}}}lom")
        general = ET.SubElement(lom, f"{{{LOMM}}}general")
        ET.SubElement(ET.SubElement(general, f"{{{LOMM}}}title"), f"{{{LOMM}}}string").text = title
        organizations = ET.SubElement(self.root, f"{{{CP}}}organizations")
        organization = ET.SubElement(
            organizations, f"{{{CP}}}organization", {"identifier": "ORG", "structure": "rooted-hierarchy"}
        )
        self.top = ET.SubElement(organization, f"{{{CP}}}item", {"identifier": "ROOT"})
        self.resources = ET.SubElement(self.root, f"{{{CP}}}resources")

    def folder(self, identifier: str, title: str):
        folder = ET.SubElement(self.top, f"{{{CP}}}item", {"identifier": identifier})
        ET.SubElement(folder, f"{{{CP}}}title").text = title
        return folder

    def entry(
        self, folder, identifier: str, title: str, kind: str, href: str | None, files: list[str], rights=""
    ):
        item = ET.SubElement(
            folder, f"{{{CP}}}item", {"identifier": f"I_{identifier}", "identifierref": identifier}
        )
        ET.SubElement(item, f"{{{CP}}}title").text = title
        attrs = {"identifier": identifier, "type": kind}
        if href:
            attrs["href"] = href
        resource = ET.SubElement(self.resources, f"{{{CP}}}resource", attrs)
        if rights:
            lom = ET.SubElement(ET.SubElement(resource, f"{{{CP}}}metadata"), f"{{{LOM}}}lom")
            rights_el = ET.SubElement(lom, f"{{{LOM}}}rights")
            ET.SubElement(ET.SubElement(rights_el, f"{{{LOM}}}description"), f"{{{LOM}}}string").text = rights
        for name in files:
            ET.SubElement(resource, f"{{{CP}}}file", {"href": name})

    def xml(self) -> bytes:
        ET.indent(self.root)
        return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(self.root, encoding="utf-8")


def export(site, stream) -> dict:
    """Write the site's content to `stream` as a .imscc file. Returns what was written and left out."""
    from assessments.models import Assignment

    manifest = _Manifest(site.title)
    left_out: list[str] = []
    counts = {"items": 0, "assignments": 0, "quizzes": 0, "questions": 0}
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as out:
        for module in site.modules.prefetch_related("items"):
            folder = manifest.folder(f"M_{module.id}", module.title)
            for item in module.items.all():
                if item.under_review:
                    left_out.append(f"{item.title}: under review for takedown")
                    continue
                rid, rights = f"R_{item.id}", rights_of(item)
                if item.kind == ContentItem.Kind.PAGE:
                    name = f"wiki_content/page-{item.id}.html"
                    out.writestr(name, _page(item.title, item.body))
                    manifest.entry(folder, rid, item.title, "webcontent", name, [name], rights)
                elif item.kind == ContentItem.Kind.LINK:
                    name = f"{rid}.xml"
                    link = ET.Element(f"{{{WL}}}webLink")
                    ET.SubElement(link, f"{{{WL}}}title").text = item.title
                    ET.SubElement(link, f"{{{WL}}}url", {"href": item.url, "target": "_blank"})
                    out.writestr(
                        name,
                        b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(link, encoding="utf-8"),
                    )
                    manifest.entry(folder, rid, item.title, "imswl_xmlv1p3", None, [name], rights)
                elif item.file:
                    original = item.original_name or item.file.name.rsplit("/", 1)[-1]
                    name = f"web_resources/{item.id}/{_slug(original)}"
                    try:
                        with item.file.open("rb") as handle:
                            out.writestr(name, handle.read())
                    except FileNotFoundError:
                        left_out.append(f"{item.title}: its file is missing from storage")
                        continue
                    manifest.entry(folder, rid, item.title, "webcontent", name, [name], rights)
                else:
                    left_out.append(f"{item.title}: nothing to export")
                    continue
                counts["items"] += 1
        assignments = list(Assignment.objects.filter(site=site).order_by("due_at", "id"))
        if assignments:
            folder = manifest.folder("M_ASSIGNMENTS", "Assignments")
            for work in assignments:
                name = f"assignments/assignment-{work.id}.html"
                due = timezone.localtime(work.due_at).strftime("%d/%m/%Y %H:%M")
                body = f"<p>Due {due}. Marked out of {work.max_mark}.</p>\n{work.instructions or ''}"
                out.writestr(name, _page(work.title, body))
                manifest.entry(folder, f"A_{work.id}", work.title, "webcontent", name, [name])
                counts["assignments"] += 1
        quizzes = list(site.quizzes.prefetch_related("slots__question"))
        if quizzes:
            folder = manifest.folder("M_QUIZZES", "Quizzes")
            for quiz in quizzes:
                assessment, written, skipped = qti_assessment(quiz)
                left_out.extend(f"{quiz.title}: {reason}" for reason in skipped)
                if not written:
                    left_out.append(f"{quiz.title}: no question QTI can carry")
                    continue
                name = f"Q_{quiz.id}/assessment.xml"
                out.writestr(name, assessment)
                manifest.entry(folder, f"Q_{quiz.id}", quiz.title, QTI_TYPE, None, [name])
                counts["quizzes"] += 1
                counts["questions"] += written
        out.writestr("imsmanifest.xml", manifest.xml())
        stamp = datetime.now().astimezone().strftime("%d/%m/%Y %H:%M")
        notes = [f"{site.code} {site.title}, exported from the GSA LMS on {stamp}.", ""]
        notes += ["Left out:", *[f"- {line}" for line in left_out]] if left_out else ["Nothing was left out."]
        out.writestr("README.txt", "\n".join(notes) + "\n")
    return {**counts, "left_out": left_out}


# ---------------------------------------------------------------------------------------------------------
# QTI 1.2 (the Common Cartridge profile)

PROFILES = {
    "multiple_choice": "cc.multiple_choice.v0p1",
    "multiple_response": "cc.multiple_response.v0p1",
    "true_false": "cc.true_false.v0p1",
    "fib": "cc.fib.v0p1",
    "essay": "cc.essay.v0p1",
}


def _material(parent, value: str):
    material = ET.SubElement(parent, "material")
    ET.SubElement(material, "mattext", {"texttype": "text/html"}).text = value or ""


def _choice_item(item, presentation, choices, single: bool):
    lid = ET.SubElement(
        presentation,
        "response_lid",
        {"ident": "response1", "rcardinality": "Single" if single else "Multiple"},
    )
    render = ET.SubElement(lid, "render_choice")
    for number, choice in enumerate(choices, 1):
        label = ET.SubElement(render, "response_label", {"ident": str(number)})
        _material(label, choice["text"])
    processing = ET.SubElement(item, "resprocessing")
    outcomes = ET.SubElement(processing, "outcomes")
    ET.SubElement(
        outcomes, "decvar", {"maxvalue": "100", "minvalue": "0", "varname": "SCORE", "vartype": "Decimal"}
    )
    right = [str(n) for n, c in enumerate(choices, 1) if float(c.get("fraction", 0)) > 0]
    condition = ET.SubElement(processing, "respcondition", {"continue": "No"})
    variable = ET.SubElement(condition, "conditionvar")
    holder = variable if single or len(right) == 1 else ET.SubElement(variable, "and")
    for ident in right if not single else right[:1]:
        ET.SubElement(holder, "varequal", {"respident": "response1"}).text = ident
    if not single:
        for n in range(1, len(choices) + 1):
            if str(n) not in right:
                ET.SubElement(
                    ET.SubElement(holder, "not"), "varequal", {"respident": "response1"}
                ).text = str(n)
    ET.SubElement(condition, "setvar", {"action": "Set", "varname": "SCORE"}).text = "100"


def qti_assessment(quiz) -> tuple[bytes, int, list[str]]:
    """The quiz's fixed questions as a QTI 1.2 assessment. Random slots and other types are listed."""
    root = ET.Element("questestinterop")
    assessment = ET.SubElement(root, "assessment", {"ident": f"QUIZ_{quiz.id}", "title": quiz.title})
    section = ET.SubElement(assessment, "section", {"ident": "root_section"})
    written, skipped = 0, []
    for slot in quiz.slots.all():
        question = slot.question
        if question is None:
            skipped.append("questions drawn at random are not exported")
            continue
        version = question.latest
        data = version.data if version else {}
        qtype = question.qtype
        if qtype == schemas.MULTICHOICE:
            profile = "multiple_choice" if data.get("single", True) else "multiple_response"
        elif qtype == schemas.TRUEFALSE:
            profile = "true_false"
        elif qtype == schemas.SHORTANSWER:
            profile = "fib"
        elif qtype == schemas.ESSAY:
            profile = "essay"
        else:
            skipped.append(f"“{question.name}” is a kind of question QTI 1.2 cannot carry")
            continue
        item = ET.SubElement(section, "item", {"ident": f"Q{question.id}", "title": question.name})
        meta = ET.SubElement(
            ET.SubElement(ET.SubElement(item, "itemmetadata"), "qtimetadata"), "qtimetadatafield"
        )
        ET.SubElement(meta, "fieldlabel").text = "cc_profile"
        ET.SubElement(meta, "fieldentry").text = PROFILES[profile]
        presentation = ET.SubElement(item, "presentation")
        _material(presentation, version.text)
        if profile in ("multiple_choice", "multiple_response"):
            _choice_item(item, presentation, data.get("choices", []), profile == "multiple_choice")
        elif profile == "true_false":
            choices = [{"text": "True", "fraction": 1 if data.get("correct") else 0},
                       {"text": "False", "fraction": 0 if data.get("correct") else 1}]  # fmt: skip
            _choice_item(item, presentation, choices, True)
        elif profile == "fib":
            ET.SubElement(
                ET.SubElement(presentation, "response_str", {"ident": "response1", "rcardinality": "Single"}),
                "render_fib",
            )
            processing = ET.SubElement(item, "resprocessing")
            ET.SubElement(
                ET.SubElement(processing, "outcomes"),
                "decvar",
                {"maxvalue": "100", "minvalue": "0", "varname": "SCORE", "vartype": "Decimal"},
            )
            for answer in data.get("answers", []):
                if float(answer.get("fraction", 0)) < 1:
                    continue
                condition = ET.SubElement(processing, "respcondition", {"continue": "No"})
                ET.SubElement(
                    ET.SubElement(condition, "conditionvar"),
                    "varequal",
                    {"respident": "response1", "case": "Yes" if data.get("case_sensitive") else "No"},
                ).text = answer["text"]
                ET.SubElement(condition, "setvar", {"action": "Set", "varname": "SCORE"}).text = "100"
        else:
            ET.SubElement(
                ET.SubElement(presentation, "response_str", {"ident": "response1", "rcardinality": "Single"}),
                "render_fib",
            )
        written += 1
    ET.indent(root)
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="utf-8"), written, skipped


def parse_qti(root, category: str) -> ParseResult:
    """Questions from a Common Cartridge QTI 1.2 assessment, for quizzes.services.import_questions."""
    result = ParseResult()
    for item in root.iter():
        if local(item.tag) != "item":
            continue
        name = item.get("title") or "Imported question"
        profile = ""
        for field in item.iter():
            if local(field.tag) == "qtimetadatafield" and text(field, "fieldlabel") == "cc_profile":
                profile = text(field, "fieldentry")
        presentation = child(item, "presentation")
        prompt = text(child(presentation, "material"), "mattext") if presentation is not None else ""
        labels = [
            (label.get("ident"), text(child(label, "material"), "mattext"))
            for label in (presentation.iter() if presentation is not None else [])
            if local(label.tag) == "response_label"
        ]
        right, banned = set(), set()
        for condition in item.iter():
            if local(condition.tag) != "respcondition":
                continue
            score = text(condition, "setvar")
            if score in ("", "0"):
                continue
            for equal in condition.iter():
                if local(equal.tag) == "varequal":
                    right.add((equal.text or "").strip())
            for negated in condition.iter():
                if local(negated.tag) == "not":
                    banned |= {(e.text or "").strip() for e in negated.iter() if local(e.tag) == "varequal"}
        right -= banned
        try:
            if profile in ("cc.multiple_choice.v0p1", "cc.multiple_response.v0p1"):
                single = profile == "cc.multiple_choice.v0p1"
                share = 1 / max(len(right), 1)
                data = {
                    "single": single,
                    "shuffle": True,
                    "choices": [
                        {
                            "text": words,
                            "fraction": (1 if single else share) if ident in right else 0,
                            "feedback": "",
                        }
                        for ident, words in labels
                    ],
                }
                qtype = schemas.MULTICHOICE
            elif profile == "cc.true_false.v0p1":
                correct = next((words for ident, words in labels if ident in right), "")
                data, qtype = {"correct": correct.strip().lower() == "true"}, schemas.TRUEFALSE
            elif profile == "cc.fib.v0p1":
                data = {
                    "answers": [{"text": t, "fraction": 1, "feedback": ""} for t in sorted(right) if t],
                    "case_sensitive": False,
                }
                qtype = schemas.SHORTANSWER
            elif profile == "cc.essay.v0p1":
                data, qtype = {}, schemas.ESSAY
            else:
                result.skip(name, f"The question kind “{profile or 'unknown'}” is not imported.")
                continue
        except (TypeError, ValueError):
            result.skip(name, "The question cannot be read.")
            continue
        result.questions.append(
            ParsedQuestion(qtype=qtype, name=name[:200], text=prompt, data=data, category_path=[category])
        )
    return result


def import_cartridge(site, upload, request) -> dict:
    """Bring a cartridge's content into the site as drafts. Returns the report."""
    from quizzes.models import QuestionBank
    from quizzes.services import import_questions

    source = ZipSource(upload)
    if not source.has("imsmanifest.xml"):
        raise ImportRefused("This is not a Common Cartridge: it has no imsmanifest.xml at its top.")
    root = xml(source.read("imsmanifest.xml"), "The manifest")
    if local(root.tag) != "manifest":
        raise ImportRefused("imsmanifest.xml is not a content package manifest.")
    report = Report()
    build = Builder(site, request, report)
    resources = {r.get("identifier"): r for r in children(child(root, "resources"), "resource")}
    organization = next(iter(children(child(root, "organizations"), "organization")), None)
    top = children(organization, "item")
    parts = children(top[0], "item") if len(top) == 1 and not top[0].get("identifierref") else top
    bank = None

    def resource_files(resource) -> list[str]:
        names = [f.get("href") for f in children(resource, "file") if f.get("href")]
        if resource.get("href"):
            names.insert(0, resource.get("href"))
        cleaned = []
        for name in names:
            path = posixpath.normpath(name)
            if source.has(path):
                cleaned.append(path)
        return cleaned

    def bring(module, node):
        nonlocal bank
        title = text(node, "title") or "Untitled"
        ref = node.get("identifierref")
        if not ref:
            for inner in children(node, "item"):
                bring(module, inner)
            if not children(node, "item"):
                report.skip(title, "A heading with nothing under it.")
            return
        resource = resources.get(ref)
        if resource is None:
            report.skip(title, "The cartridge names a resource it does not hold.")
            return
        kind = resource.get("type") or ""
        rights = licence_from(
            text(child(child(child(resource, "metadata"), "lom"), "rights"), "description/string")
        )
        files = resource_files(resource)
        if kind == "webcontent":
            if not files:
                report.skip(title, "Its file is not in the cartridge.")
                return
            first = files[0]
            if posixpath.splitext(first)[1].lower() in (".html", ".htm"):
                html = source.read(first).decode("utf-8", "replace")
                body = re.search(r"<body[^>]*>(.*)</body>", html, re.IGNORECASE | re.DOTALL)
                content = body.group(1) if body else html
                content = re.sub(
                    r"^\s*<h1[^>]*>.*?</h1>", "", content, count=1, flags=re.IGNORECASE | re.DOTALL
                )
                build.page(module, title, content, **rights)
            else:
                build.file(module, title, posixpath.basename(first), source.read(first), **rights)
        elif kind.startswith("imswl_xmlv1p"):
            link = xml(source.read(files[0]), title) if files else None
            url = (
                child(link, "url").get("href") if link is not None and child(link, "url") is not None else ""
            ) or ""
            build.link(module, title, url.strip(), **rights)
        elif "assessment" in kind and "qti" in kind.lower():
            if not files:
                report.skip(title, "Its questions are not in the cartridge.")
                return
            parsed = parse_qti(xml(source.read(files[0]), title), title)
            if bank is None:
                bank = QuestionBank.objects.create(
                    site=site,
                    name=f"Imported for {site.code}"[:160],
                    created_by=request.user,
                    updated_by=request.user,
                )
            done = import_questions(bank, parsed, request=request)
            report.questions += len(done["imported"])
            report.skipped.extend({"title": s["name"], "reason": s["reason"]} for s in done["skipped"])
            report.warnings.append(
                f"{title}: its questions are in the question bank “{bank.name}”; build the quiz from them."
            )
        elif kind.startswith("imsdt"):
            report.skip(
                title, "Discussion topics are not imported; start the discussion in the course's forums."
            )
        elif "lti" in kind.lower():
            report.skip(title, "Outside tools (LTI) are not imported.")
        else:
            report.skip(title, f"Resources of type “{kind}” are not imported.")

    for part in parts:
        title = text(part, "title") or "Imported"
        if part.get("identifierref"):
            module = build.module(title)
            bring(module, part)
            continue
        module = build.module(title)
        for node in children(part, "item"):
            bring(module, node)
    if not parts:
        report.warnings.append("The cartridge has no organisation, so nothing was arranged into modules.")
    return report.as_dict()
