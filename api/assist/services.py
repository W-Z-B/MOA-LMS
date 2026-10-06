"""What AI is asked, with what, and the rules around it (items 6.11, 6.12, decision D5).

Lecturer drafts: questions from the lecturer's own page or Word or PowerPoint file, rubric wording, and
alternative text for a picture. A draft is only ever shown back to the lecturer, who reviews and edits it
before saving it through the ordinary screens; saving it is marked as AI-drafted in the audit log.

The study helper: answers a student's question only from the course's own published material that the
student can see. The material is found with PostgreSQL full-text search (no extension needed); with nothing
found the helper says so without asking the model, and the model is told to say so too when the passages
found do not answer. Every answer lists its sources. It is switched off while the student has a quiz
attempt in progress or a quiz or assignment open to them on the site. The prompt carries the question and
the course's material only: nothing about the student.
"""

import html
import json
import re
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser

from django.conf import settings
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.utils import timezone

from assist.models import Exchange, SiteSwitch
from assist.providers import ProviderError, enabled, provider
from courses import release
from courses.access import person_of, site_role
from courses.models import ContentItem, CourseSite, Membership

LONGEST_SOURCE = 12_000  # characters of a lecturer's material sent for drafting
EXCERPT = 2_000  # characters of each passage the helper answers from
PASSAGES = 3
NOT_FOUND = "NOT_IN_MATERIAL"
NOTHING_FOUND = (
    "I could not find this in your course's material, so I cannot answer it. Ask your lecturer, or look "
    "through the course's modules."
)


class Refusal(Exception):
    def __init__(self, code: str, detail: str, status: int = 403):
        super().__init__(detail)
        self.code, self.detail, self.status = code, detail, status


def switch(site: CourseSite) -> SiteSwitch:
    return SiteSwitch.objects.filter(site=site).first() or SiteSwitch(site=site)


# ---------------------------------------------------------------------------------------------------------
# When the study helper is off


def assessment_open(person, site: CourseSite, now=None) -> str | None:
    """Why the study helper is off for this student now, or None when it may be used."""
    from assessments.models import Submission
    from assessments.rules import due_for
    from quizzes.models import Attempt
    from quizzes.services import effective, is_closed

    now = now or timezone.now()
    if Attempt.objects.filter(quiz__site=site, student=person, state=Attempt.State.IN_PROGRESS).exists():
        return "The study helper is off while you have a quiz attempt in progress on this course."
    for quiz in site.quizzes.filter(is_published=True, is_practice=False):
        if (quiz.opens_at and quiz.opens_at > now) or is_closed(quiz, person, now):
            continue
        allowed = effective(quiz, person).attempts_allowed
        if not allowed or quiz.attempts.filter(student=person).count() < allowed:
            return f"The study helper is off while the quiz “{quiz.title}” is open to you."
    if settings.AI_HELPER_OFF_DURING_ASSIGNMENTS:
        handed_in = Submission.objects.filter(assignment__site=site, student=person).values_list(
            "assignment_id", flat=True
        )
        for assignment in site.assignments.filter(is_published=True).exclude(id__in=list(handed_in)):
            if assignment.opens_at and assignment.opens_at > now:
                continue
            if due_for(assignment, person).at > now:
                return f"The study helper is off while the assignment “{assignment.title}” is open to you."
    return None


def status(user, site: CourseSite) -> dict:
    """What the screens show: whether AI is on, the site's switches, and whether the helper may be used."""
    on = enabled()
    chosen = switch(site)
    role = site_role(user, site)
    teaching = role in ("admin", Membership.SiteRole.LECTURER, Membership.SiteRole.ASSISTANT)
    reason = None
    if not on:
        reason = "AI help is not switched on for the GSA LMS."
    elif not chosen.study_helper:
        reason = "The study helper is not switched on for this course."
    elif role == Membership.SiteRole.STUDENT:
        reason = assessment_open(person_of(user), site)
    return {
        "enabled": on,
        "teaching": teaching,
        "drafts": on and chosen.drafts,
        "study_helper": on and chosen.study_helper,
        "helper_available": on and chosen.study_helper and reason is None and role is not None,
        "helper_reason": reason,
        "pictures": bool(on and settings.AI_VISION_MODEL),
    }


# ---------------------------------------------------------------------------------------------------------
# Text of the lecturer's material


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in {"p", "br", "li", "h1", "h2", "h3", "h4", "tr", "div"}:
            self.parts.append("\n")


def html_text(body: str) -> str:
    parser = _Text()
    parser.feed(body or "")
    return re.sub(r"\n\s*\n+", "\n\n", html.unescape("".join(parser.parts))).strip()


def _office_text(item: ContentItem) -> str:
    """The words of a Word or PowerPoint file, from the XML inside it."""
    with item.file.open("rb") as stored, zipfile.ZipFile(stored) as package:
        names = sorted(
            n
            for n in package.namelist()
            if n == "word/document.xml" or re.fullmatch(r"ppt/slides/slide\d+\.xml", n)
        )
        text = []
        for name in names[:200]:
            xml = package.read(name)[:2_000_000].decode("utf-8", "ignore")
            xml = re.sub(r"</w:p>|</a:p>", "\n", xml)
            text.append(html.unescape(re.sub(r"<[^>]+>", "", xml)))
    return "\n".join(text).strip()


def material_text(item: ContentItem) -> str:
    if item.kind == ContentItem.Kind.PAGE:
        return html_text(item.body)
    if item.kind == ContentItem.Kind.FILE and item.file:
        from core.uploads import sniff

        with item.file.open("rb") as stored:
            kind = sniff(stored)
        if kind in ("docx", "pptx"):
            return _office_text(item)
    raise Refusal("not_readable", "Only pages, and Word or PowerPoint files, can be read for drafting.", 400)


# ---------------------------------------------------------------------------------------------------------
# Lecturer drafts


def _model(vision: bool = False):
    try:
        chosen = provider(vision=vision)
    except ProviderError as error:
        raise Refusal("ai_unavailable", str(error), 503) from error
    if chosen is None:
        if vision and enabled():
            raise Refusal(
                "no_picture_model", "No AI model that reads pictures is set up for the GSA LMS.", 503
            )
        raise Refusal("ai_off", "AI help is not switched on for the GSA LMS.")
    return chosen


def _ask(chosen, prompt: str, **kwargs) -> str:
    try:
        return chosen.generate(prompt, **kwargs)
    except ProviderError as error:
        raise Refusal("ai_unavailable", "The AI model could not be reached. Try again later.", 503) from error


def _json(text: str):
    """The JSON in a model's answer, or a refusal: models sometimes wrap it in prose."""
    match = re.search(r"[\[{].*[\]}]", text, re.S)
    try:
        return json.loads(match.group(0) if match else text)
    except (json.JSONDecodeError, AttributeError) as error:
        raise Refusal("ai_unreadable", "The AI model's answer could not be read. Try again.", 502) from error


def check_drafts_on(site: CourseSite) -> None:
    if not enabled():
        raise Refusal("ai_off", "AI help is not switched on for the GSA LMS.")
    if not switch(site).drafts:
        raise Refusal("drafts_off", "AI drafts are not switched on for this course.")


QUESTION_SYSTEM = (
    "You help a lecturer at the Guyana School of Agriculture write quiz questions. Use only the material "
    "given. Write in plain British English. Answer with JSON only."
)


def draft_questions(user, site: CourseSite, item: ContentItem, count: int) -> Exchange:
    """Multiple-choice questions drafted from the lecturer's own material, each checked against the rules
    for a question so that it can be saved as it is or after editing."""
    from quizzes.schemas import MULTICHOICE, QuestionDataError, validate_question

    check_drafts_on(site)
    text = material_text(item)[:LONGEST_SOURCE]
    if len(text) < 80:
        raise Refusal("too_short", "There is too little text in this item to draft questions from.", 400)
    prompt = (
        f"Write {count} multiple-choice questions that test understanding of the material below. Each has "
        "four choices and exactly one correct choice. Answer as JSON: "
        '{"questions": [{"name": "short name", "text": "the question", "choices": [{"text": "...", '
        '"correct": true or false, "feedback": "why"}], "general_feedback": "..."}]}\n\n'
        f"MATERIAL:\n{text}"
    )
    answer = _json(_ask(_model(), prompt, system=QUESTION_SYSTEM, json_output=True))
    rows = answer.get("questions", []) if isinstance(answer, dict) else answer
    drafts = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        choices = [
            {
                "text": str(c.get("text", ""))[:1000],
                "fraction": 1 if c.get("correct") is True else 0,
                "feedback": str(c.get("feedback", ""))[:1000],
            }
            for c in row.get("choices", [])
            if isinstance(c, dict) and str(c.get("text", "")).strip()
        ]
        data = {"single": True, "shuffle": True, "choices": choices}
        question_text = str(row.get("text", "")).strip()[:4000]
        try:
            data = validate_question(MULTICHOICE, question_text, data)
        except QuestionDataError:
            continue  # a draft that would not save is left out rather than shown
        drafts.append(
            {
                "name": (str(row.get("name") or question_text)[:200]).strip(),
                "qtype": MULTICHOICE,
                "text": question_text,
                "data": data,
                "general_feedback": str(row.get("general_feedback", ""))[:2000],
            }
        )
        if len(drafts) >= count:
            break
    if not drafts:
        raise Refusal("ai_unreadable", "The AI model's answer gave no usable questions. Try again.", 502)
    return Exchange.objects.create(
        site=site, user=user, kind=Exchange.Kind.QUESTIONS, source=item, output={"questions": drafts}
    )


RUBRIC_SYSTEM = (
    "You help a lecturer at the Guyana School of Agriculture word a marking rubric. Describe what work at "
    "each level shows, in plain British English, one or two sentences each. Answer with JSON only."
)


def draft_rubric(user, site: CourseSite, title: str, task: str, criteria: list[str], levels: int) -> Exchange:
    check_drafts_on(site)
    named = "\n".join(f"- {c}" for c in criteria)
    prompt = (
        f"Rubric: {title}\nThe work: {task}\nCriteria:\n{named}\n\nFor each criterion write {levels} level "
        "descriptions, from the best work to the weakest. Answer as JSON: "
        '{"criteria": [{"title": "criterion as given", "description": "what the criterion looks at", '
        '"levels": ["best level description", "...", "weakest level description"]}]}'
    )
    answer = _json(_ask(_model(), prompt, system=RUBRIC_SYSTEM, json_output=True))
    rows = answer.get("criteria", []) if isinstance(answer, dict) else []
    by_title = {str(r.get("title", "")).strip().lower(): r for r in rows if isinstance(r, dict)}
    drafted = []
    for position, name in enumerate(criteria):
        row = by_title.get(name.strip().lower()) or (rows[position] if position < len(rows) else {})
        said = [str(x)[:1000] for x in (row.get("levels") or []) if str(x).strip()][:levels] if row else []
        said += [""] * (levels - len(said))
        drafted.append(
            {
                "title": name,
                "description": str((row or {}).get("description", ""))[:1000],
                "levels": [
                    {"points": str(levels - i - 1), "description": text} for i, text in enumerate(said)
                ],
            }
        )
    output = {"title": title, "kind": "scored", "criteria": drafted}
    return Exchange.objects.create(site=site, user=user, kind=Exchange.Kind.RUBRIC, output=output)


ALT_SYSTEM = (
    "You write alternative text for pictures in course material at an agricultural college, for people "
    "who cannot see them. Say what the picture shows that matters for learning, in one plain British "
    "English sentence of at most 25 words. Do not start with 'Image of' or 'Picture of'."
)


def suggest_alt_text(user, site: CourseSite, item: ContentItem) -> Exchange:
    from core.uploads import sniff

    check_drafts_on(site)
    if item.kind != ContentItem.Kind.FILE or not item.file:
        raise Refusal("not_a_picture", "Choose a picture put up on this course.", 400)
    with item.file.open("rb") as stored:
        if sniff(stored) not in ("jpeg", "png", "webp"):
            raise Refusal("not_a_picture", "Only JPG, PNG and WebP pictures can be described.", 400)
        stored.seek(0)
        picture = stored.read(10_000_000)
    said = _ask(_model(vision=True), "Describe this picture.", system=ALT_SYSTEM, images=[picture])
    said = re.sub(r"\s+", " ", said).strip().strip('"')[:250]
    if not said:
        raise Refusal("ai_unreadable", "The AI model gave no description. Try again.", 502)
    return Exchange.objects.create(
        site=site, user=user, kind=Exchange.Kind.ALT_TEXT, source=item, output={"alt_text": said}
    )


# ---------------------------------------------------------------------------------------------------------
# The study helper


@dataclass
class HelperAnswer:
    answered: bool
    answer: str
    sources: list[dict] = field(default_factory=list)


HELPER_SYSTEM = (
    "You are a study helper for students at the Guyana School of Agriculture. Answer the question using "
    "only the numbered passages from the course's own material. Say which passages you used, like [1]. If "
    f"the passages do not answer the question, reply with exactly {NOT_FOUND} and nothing else. Never "
    "answer from anything else you know. Use plain British English."
)


def _query(question: str) -> SearchQuery | None:
    """Any of the question's words, as a full-text query; the parser drops common words."""
    words = [w for w in re.findall(r"[A-Za-z0-9]+", question)[:30] if len(w) > 1]
    if not words:
        return None
    return SearchQuery(" | ".join(words), search_type="raw", config="english")


def passages(request, site: CourseSite, question: str) -> list[ContentItem]:
    """The published pages of the course the person can see that best match the question."""
    query = _query(question)
    if query is None:
        return []
    items = ContentItem.objects.filter(
        module__site=site, kind=ContentItem.Kind.PAGE, is_published=True, under_review=False
    )
    hidden = release.hidden_items(request, items)
    if hidden:
        items = items.exclude(id__in=hidden)
    vector = SearchVector("title", weight="A", config="english") + SearchVector(
        "body", weight="B", config="english"
    )
    return list(
        items.annotate(search=vector, rank=SearchRank(vector, query))
        .filter(search=query)
        .select_related("module")
        .order_by("-rank", "id")[:PASSAGES]
    )


def ask(request, site: CourseSite, question: str) -> HelperAnswer:
    """Answer a question from the course's own material, or say it is not there."""
    user = request.user
    info = status(user, site)
    if not info["enabled"]:
        raise Refusal("ai_off", "AI help is not switched on for the GSA LMS.")
    if not info["study_helper"]:
        raise Refusal("helper_off", "The study helper is not switched on for this course.")
    if site_role(user, site) == Membership.SiteRole.STUDENT and info["helper_reason"]:
        raise Refusal("assessment_open", info["helper_reason"])
    found = passages(request, site, question)
    sources = [
        {"item": i.id, "title": i.title, "module": i.module.title, "link": f"/sites/{site.id}/pages/{i.id}"}
        for i in found
    ]
    exchange = Exchange(site=site, user=user, kind=Exchange.Kind.HELPER, sources=[i.id for i in found])
    if not found:
        exchange.save()
        return HelperAnswer(False, NOTHING_FOUND)
    numbered = "\n\n".join(
        f"[{n}] {i.title}\n{html_text(i.body)[:EXCERPT]}" for n, i in enumerate(found, start=1)
    )
    said = _ask(_model(), f"PASSAGES:\n{numbered}\n\nQUESTION: {question}", system=HELPER_SYSTEM)
    if NOT_FOUND in said or not said.strip():
        exchange.save()
        return HelperAnswer(False, NOTHING_FOUND)
    exchange.answered = True
    exchange.save()
    return HelperAnswer(True, said, sources)
