"""Moodle course backups (.mbz), for moving content only (item 6.08).

What comes in, as drafts with their licence "not yet known":
- each section becomes a module (its summary, when it has one, a first page "About this section");
- pages and labels become pages, URLs become links, and files (the "resource" activity) become file items
  when they are kinds a course may hold;
- the backup's question bank comes in through the Moodle XML importer (quizzes.formats.parse_moodle_xml):
  each question of a type the LMS has is written as Moodle XML and imported into a question bank of the
  course, by its Moodle category. The quizzes themselves are not rebuilt.
What does not: people, enrolments, groups, submissions, grades, logs, forums and their posts, assignments,
folders, books, lessons and other activities; each is listed in the report with the reason.
"""

import posixpath
import xml.etree.ElementTree as ET  # noqa: S405 - only builds Moodle XML; parsing goes through common.xml

from interchange.common import (
    Builder,
    ImportRefused,
    Report,
    ZipSource,
    child,
    children,
    tar_members,
    text,
    xml,
)
from quizzes.formats import parse_moodle_xml

TYPES = {
    "multichoice": "multichoice",
    "truefalse": "truefalse",
    "shortanswer": "shortanswer",
    "numerical": "numerical",
    "essay": "essay",
    "match": "matching",
}
SKIP_REASONS = {
    "forum": "Forums and their posts are not imported; start discussions in the course's forums.",
    "assign": "Assignments are not imported; set them again in the Assignments tab.",
    "quiz": "Quizzes are not rebuilt; their questions are in the course's question bank.",
    "folder": "Folders are not imported; put their files up one by one.",
}


def _wanted_xml(name: str, size: int) -> bool:
    return name.endswith(".xml") and (
        name in ("moodle_backup.xml", "files.xml", "questions.xml")
        or name.startswith(("sections/", "activities/"))
    )


class _Backup:
    """The backup's XML, read once; files read on request (a second pass for a tar backup)."""

    def __init__(self, upload):
        upload.seek(0)
        head = upload.read(4)
        upload.seek(0)
        self.upload = upload
        self.zip = None
        if head.startswith(b"\x1f\x8b"):
            self.xml = dict(tar_members(upload, _wanted_xml))
        elif head == b"PK\x03\x04":
            self.zip = ZipSource(upload)
            self.xml = {name: self.zip.read(name) for name in self.zip.entries if _wanted_xml(name, 0)}
        else:
            raise ImportRefused("This is not a Moodle backup (.mbz).")
        if "moodle_backup.xml" not in self.xml:
            raise ImportRefused("This is not a Moodle course backup: it has no moodle_backup.xml.")

    def doc(self, name: str, what: str):
        data = self.xml.get(name)
        return xml(data, what) if data is not None else None

    def files(self, wanted: set[str]) -> dict[str, bytes]:
        if not wanted:
            return {}
        if self.zip is not None:
            return {name: self.zip.read(name) for name in wanted if self.zip.has(name)}
        return dict(tar_members(self.upload, lambda name, size: name in wanted))


def _latest_questions(category):
    """The questions of a category: in a Moodle 4 backup, only the newest version of each."""
    entries = list(category.iter("question_bank_entry"))
    groups = (
        [list(entry.iter("question")) for entry in entries]
        if entries
        else [[q] for q in category.iter("question")]
    )
    for group in groups:
        usable = [q for q in group if text(q, "qtype") and text(q, "parent") in ("", "0")]
        if usable:
            yield usable[-1]


def _questions_xml(root) -> tuple[str, list[dict]]:
    """The backup's questions as a Moodle XML file, and those of types the LMS does not have."""
    quiz = ET.Element("quiz")
    skipped = []

    def text_el(parent, tag, value, fmt="html"):
        element = ET.SubElement(parent, tag, {"format": fmt} if fmt else {})
        ET.SubElement(element, "text").text = value or ""

    for category in root.iter("question_category"):
        name = text(category, "name") or "Imported"
        heading = ET.SubElement(quiz, "question", {"type": "category"})
        text_el(heading, "category", f"$course$/top/{name}", fmt=None)
        for question in _latest_questions(category):
            qtype = text(question, "qtype")
            title = text(question, "name") or "Imported question"
            mapped = TYPES.get(qtype)
            if mapped is None:
                skipped.append(
                    {"title": title, "reason": f"The Moodle question type “{qtype}” is not imported."}
                )
                continue
            element = ET.SubElement(quiz, "question", {"type": "matching" if qtype == "match" else qtype})
            text_el(element, "name", title, fmt=None)
            text_el(element, "questiontext", text(question, "questiontext"))
            text_el(element, "generalfeedback", text(question, "generalfeedback"))
            ET.SubElement(element, "defaultgrade").text = text(question, "defaultmark") or "1"
            tolerances = {
                text(record, "answer"): text(record, "tolerance")
                for record in question.iter("numerical_record")
            }
            for answer in question.iter("answer"):
                if child(answer, "answertext") is None:
                    continue
                try:
                    fraction = float(text(answer, "fraction") or 0) * 100
                except ValueError:
                    fraction = 0
                words = text(answer, "answertext")
                if qtype == "truefalse":
                    words = words.lower()
                node = ET.SubElement(element, "answer", {"fraction": f"{fraction:g}"})
                ET.SubElement(node, "text").text = words
                text_el(node, "feedback", text(answer, "feedback"))
                if qtype == "numerical":
                    ET.SubElement(node, "tolerance").text = tolerances.get(answer.get("id"), "0") or "0"
            for option in ("single", "shuffleanswers", "usecase"):
                for found in question.iter(option):
                    ET.SubElement(element, option).text = (found.text or "").strip()
                    break
            for match in question.iter("match"):
                sub = ET.SubElement(element, "subquestion", {"format": "html"})
                ET.SubElement(sub, "text").text = text(match, "questiontext")
                ET.SubElement(ET.SubElement(sub, "answer"), "text").text = text(match, "answertext")
    return ET.tostring(quiz, encoding="unicode"), skipped


def import_backup(site, upload, request) -> dict:
    from quizzes.models import QuestionBank
    from quizzes.services import import_questions

    backup = _Backup(upload)
    report = Report()
    build = Builder(site, request, report)
    info = backup.doc("moodle_backup.xml", "moodle_backup.xml")
    contents = child(child(info, "information"), "contents")
    if contents is None:
        raise ImportRefused("The backup does not list its contents; make a course backup in Moodle.")
    activities = children(child(contents, "activities"), "activity")
    by_section: dict[str, list] = {}
    for activity in activities:
        by_section.setdefault(text(activity, "sectionid"), []).append(activity)

    # Files: which stored file each resource activity names (files.xml through the activity's inforef.xml).
    files_doc = backup.doc("files.xml", "files.xml")
    stored = {}
    for record in children(files_doc, "file") if files_doc is not None else []:
        if text(record, "filename") not in ("", ".") and text(record, "component") == "mod_resource":
            stored[record.get("id")] = (text(record, "contenthash"), text(record, "filename"))
    wanted: dict[str, list] = {}
    for activity in activities:
        if text(activity, "modulename") != "resource":
            continue
        inforef = backup.doc(f"{text(activity, 'directory')}/inforef.xml", "inforef.xml")
        refs = [text(ref, "id") for ref in inforef.iter("file")] if inforef is not None else []
        found = [stored[r] for r in refs if r in stored]
        wanted[text(activity, "moduleid")] = found
    blobs = backup.files({f"files/{h[:2]}/{h}" for files in wanted.values() for h, _ in files if len(h) > 2})

    for section in children(child(contents, "sections"), "section"):
        section_doc = backup.doc(f"{text(section, 'directory')}/section.xml", "section.xml")
        name = text(section_doc, "name") if section_doc is not None else ""
        number = text(section_doc, "number") if section_doc is not None else ""
        title = name or (f"Section {number}" if number else text(section, "title") or "Section")
        members = by_section.get(text(section, "sectionid"), [])
        summary = text(section_doc, "summary") if section_doc is not None else ""
        if not members and not summary:
            continue
        module = build.module(title)
        if summary:
            build.page(module, "About this section", summary)
        sequence = (text(section_doc, "sequence") if section_doc is not None else "").split(",")
        order = {moduleid: place for place, moduleid in enumerate(sequence)}
        members.sort(key=lambda a: order.get(text(a, "moduleid"), len(order)))
        for activity in members:
            kind, title = text(activity, "modulename"), text(activity, "title") or "Untitled"
            directory = text(activity, "directory")
            doc = backup.doc(f"{directory}/{kind}.xml", f"{kind}.xml")
            body = child(doc, kind) if doc is not None else None
            if kind == "page" and body is not None:
                build.page(module, text(body, "name") or title, text(body, "content"))
            elif kind == "label" and body is not None:
                build.page(module, text(body, "name") or title, text(body, "intro"))
            elif kind == "url" and body is not None:
                build.link(module, text(body, "name") or title, text(body, "externalurl"))
            elif kind == "resource":
                files = wanted.get(text(activity, "moduleid"), [])
                if not files:
                    report.skip(title, "Its file is not in the backup (made without files?).")
                for contenthash, filename in files:
                    data = blobs.get(f"files/{contenthash[:2]}/{contenthash}")
                    if data is None:
                        report.skip(title, "Its file is not in the backup (made without files?).")
                        continue
                    label = title if len(files) == 1 else f"{title}: {filename}"
                    build.file(module, label, posixpath.basename(filename), data)
            else:
                report.skip(title, SKIP_REASONS.get(kind, f"Moodle “{kind}” activities are not imported."))

    questions = backup.doc("questions.xml", "questions.xml")
    if questions is not None:
        moodle_xml, skipped = _questions_xml(questions)
        report.skipped.extend(skipped)
        parsed = parse_moodle_xml(moodle_xml)
        if parsed.questions:
            bank = QuestionBank.objects.create(
                site=site,
                name=f"Imported from Moodle for {site.code}"[:160],
                created_by=request.user,
                updated_by=request.user,
            )
            done = import_questions(bank, parsed, request=request)
            report.questions += len(done["imported"])
            report.skipped.extend({"title": s["name"], "reason": s["reason"]} for s in done["skipped"])
            report.warnings.extend(done["warnings"])
        else:
            report.skipped.extend({"title": s["name"], "reason": s["reason"]} for s in parsed.skipped)
    report.warnings.append("Other people's work, enrolments, marks and logs are never imported.")
    return report.as_dict()
