"""AI assistance within decision D5 (items 6.11, 6.12). The model's HTTP API is never called: a fake
stands in for Ollama and records what the LMS sent it."""

import io
import json
import zipfile
from datetime import timedelta

import pytest
from django.core.files.base import ContentFile
from django.utils import timezone

from assist import providers
from assist.models import Exchange, SiteSwitch
from audit.models import AuditLog
from courses.models import ContentItem, Module

pytestmark = pytest.mark.django_db

PAGE_BODY = (
    "<h2>Soil texture</h2><p>Soil texture is the proportion of sand, silt and clay in a soil. Sandy soils "
    "drain quickly and hold few nutrients; clay soils hold water and nutrients but drain slowly. Loam is a "
    "balanced mixture and suits most crops grown at the school farm.</p>"
)


class FakeOllama:
    """Answers POST /api/generate like Ollama does, with the next prepared answer."""

    def __init__(self):
        self.answers: list = []
        self.sent: list[dict] = []
        self.down = False

    def __call__(self, request, timeout=None):
        if self.down:
            raise OSError("connection refused")
        assert request.full_url == "http://ollama.gsa.internal:11434/api/generate"
        self.sent.append(json.loads(request.data))
        answer = self.answers.pop(0) if self.answers else ""
        return io.BytesIO(json.dumps({"response": answer, "done": True}).encode())


@pytest.fixture
def ollama(monkeypatch):
    fake = FakeOllama()
    monkeypatch.setattr(providers.urllib.request, "urlopen", fake)
    return fake


@pytest.fixture
def ai_on(settings):
    settings.AI_ENABLED = True
    settings.AI_OLLAMA_URL = "http://ollama.gsa.internal:11434"
    settings.AI_MODEL = "llama3.1:8b"
    settings.AI_VISION_MODEL = "llava:7b"


@pytest.fixture
def module(site):
    return Module.objects.create(site=site, title="Week 1: Soils")


@pytest.fixture
def page(module):
    return ContentItem.objects.create(module=module, kind="page", title="Soil texture", body=PAGE_BODY)


def switch_on(site, **values):
    SiteSwitch.objects.update_or_create(site=site, defaults=values)


def office_file(module, folder="word", name="notes.docx") -> ContentItem:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("[Content_Types].xml", "<Types/>")
        xml = "<w:document><w:body><w:p><w:r><w:t>Compost adds organic matter &amp; feeds soil life."
        xml += " Turn the heap weekly so that it stays aerobic and warm.</w:t></w:r></w:p>"
        xml += "<w:p><w:r><w:t>A finished compost smells of earth and is dark and crumbly.</w:t></w:r></w:p>"
        package.writestr(f"{folder}/document.xml" if folder == "word" else "ppt/slides/slide1.xml", xml)
    return ContentItem.objects.create(
        module=module, kind="file", title="Compost notes", file=ContentFile(buffer.getvalue(), name=name)
    )


# ---------------------------------------------------------------------------------------------------------
# Off by default


def test_everything_is_off_by_default(site, page, lecturer, student, client_for, ollama):
    teacher = client_for(lecturer.user)
    status = teacher.get(f"/api/v1/sites/{site.id}/ai/").json()
    assert status["enabled"] is False and status["drafts"] is False and status["helper_available"] is False
    assert (
        teacher.patch(f"/api/v1/sites/{site.id}/ai/", {"drafts": True}, format="json").json()["code"]
        == "ai_off"
    )
    drafted = teacher.post(f"/api/v1/sites/{site.id}/ai/drafts/questions/", {"item": page.id}, format="json")
    assert drafted.json()["code"] == "ai_off"
    asked = client_for(student.user).post(f"/api/v1/sites/{site.id}/ai/ask/", {"question": "What is loam?"})
    assert asked.status_code == 403 and asked.json()["code"] == "ai_off"
    assert ollama.sent == [] and providers.provider() is None


def test_each_course_has_its_own_switches_kept_by_its_teaching_staff(
    ai_on, site, lecturer, student, client_for
):
    url = f"/api/v1/sites/{site.id}/ai/"
    assert client_for(lecturer.user).get(url).json()["drafts"] is False  # on for the LMS, off for the course
    assert client_for(student.user).patch(url, {"study_helper": True}, format="json").status_code == 403
    changed = client_for(lecturer.user).patch(url, {"drafts": True, "study_helper": True}, format="json")
    assert changed.json()["drafts"] is True and changed.json()["study_helper"] is True
    assert AuditLog.objects.filter(entity="assist.siteswitch", action="update").exists()


def test_only_http_addresses_are_called(settings, ai_on):
    settings.AI_OLLAMA_URL = "file:///etc/passwd"
    with pytest.raises(providers.ProviderError):
        providers.provider()


# ---------------------------------------------------------------------------------------------------------
# Lecturer drafts


QUESTIONS = {
    "questions": [
        {
            "name": "Loam",
            "text": "Which soil suits most crops at the school farm?",
            "choices": [
                {"text": "Loam", "correct": True, "feedback": "A balanced mixture."},
                {"text": "Pure sand", "correct": False},
                {"text": "Heavy clay", "correct": False},
                {"text": "Gravel", "correct": False},
            ],
            "general_feedback": "Loam balances drainage and nutrients.",
        },
        {"name": "Broken", "text": "No choices at all", "choices": []},
    ]
}


def test_questions_are_drafted_from_the_lecturers_own_page_and_marked_when_saved(
    ai_on, site, page, lecturer, client_for, ollama
):
    from quizzes.models import QuestionBank

    switch_on(site, drafts=True)
    ollama.answers = ["Here you are:\n" + json.dumps(QUESTIONS)]
    client = client_for(lecturer.user)
    drafted = client.post(f"/api/v1/sites/{site.id}/ai/drafts/questions/", {"item": page.id, "count": 3})
    assert drafted.status_code == 201, drafted.content
    questions = drafted.json()["output"]["questions"]
    assert (
        len(questions) == 1 and questions[0]["data"]["choices"][0]["fraction"] == 1
    )  # the broken one left out
    sent = ollama.sent[0]
    assert sent["model"] == "llama3.1:8b" and "Loam is a balanced mixture" in sent["prompt"]
    assert "<p>" not in sent["prompt"] and sent["format"] == "json"
    draft_id = drafted.json()["draft"]
    assert AuditLog.objects.filter(action="ai_drafted", entity="assist.exchange", entity_id=draft_id).exists()
    bank = QuestionBank.objects.create(name="Soils", site=site)
    edited = {**questions[0], "bank": bank.id, "text": questions[0]["text"] + " (edited)"}
    saved = client.post("/api/v1/questions/", edited, format="json")
    assert saved.status_code == 201, saved.content
    marked = client.post(
        f"/api/v1/ai/drafts/{draft_id}/saved/", {"record": "question", "id": saved.json()["id"]}
    )
    assert marked.status_code == 204
    entry = AuditLog.objects.get(action="ai_draft_saved")
    assert entry.entity == "quizzes.question" and entry.after == {"draft": draft_id, "kind": "questions"}


def test_draft_refusals(ai_on, site, page, module, lecturer, student, client_for, ollama):
    url = f"/api/v1/sites/{site.id}/ai/drafts/questions/"
    client = client_for(lecturer.user)
    assert client.post(url, {"item": page.id}).json()["code"] == "drafts_off"
    switch_on(site, drafts=True)
    assert client_for(student.user).post(url, {"item": page.id}).status_code == 403
    ollama.answers = ["I cannot help with that."]
    assert client.post(url, {"item": page.id}).status_code == 502
    ollama.answers = [json.dumps({"questions": [{"text": "x", "choices": []}]})]
    assert client.post(url, {"item": page.id}).json()["code"] == "ai_unreadable"
    ollama.down = True
    assert client.post(url, {"item": page.id}).status_code == 503
    short = ContentItem.objects.create(module=module, kind="page", title="Short", body="<p>Too short.</p>")
    assert client.post(url, {"item": short.id}).json()["code"] == "too_short"
    pdf = ContentItem.objects.create(
        module=module, kind="file", title="Scan", file=ContentFile(b"%PDF-1.7 scan", name="scan.pdf")
    )
    assert client.post(url, {"item": pdf.id}).json()["code"] == "not_readable"
    assert client.post(url, {"item": 999999}).status_code == 404


def test_word_and_powerpoint_files_can_be_read_for_drafting(
    ai_on, site, module, lecturer, client_for, ollama
):
    switch_on(site, drafts=True)
    client = client_for(lecturer.user)
    for folder, name in (("word", "notes.docx"), ("ppt", "slides.pptx")):
        item = office_file(module, folder, name)
        ollama.answers = [json.dumps(QUESTIONS)]
        answer = client.post(f"/api/v1/sites/{site.id}/ai/drafts/questions/", {"item": item.id, "count": 1})
        assert answer.status_code == 201, answer.content
        assert "Compost adds organic matter & feeds soil life." in ollama.sent[-1]["prompt"]


def test_rubric_wording_is_drafted_for_each_criterion(ai_on, site, lecturer, client_for, ollama):
    switch_on(site, drafts=True)
    ollama.answers = [
        json.dumps(
            {
                "criteria": [
                    {
                        "title": "Sampling method",
                        "description": "How the samples were taken",
                        "levels": ["Excellent", "Good", "Weak"],
                    }
                ]
            }
        )
    ]
    answer = client_for(lecturer.user).post(
        f"/api/v1/sites/{site.id}/ai/drafts/rubric/",
        {
            "title": "Soil report",
            "task": "Sample a plot and report",
            "criteria": ["Sampling method", "Analysis"],
            "levels": 3,
        },
        format="json",
    )
    assert answer.status_code == 201, answer.content
    criteria = answer.json()["output"]["criteria"]
    assert criteria[0]["levels"] == [
        {"points": "2", "description": "Excellent"},
        {"points": "1", "description": "Good"},
        {"points": "0", "description": "Weak"},
    ]
    assert criteria[1]["title"] == "Analysis" and len(criteria[1]["levels"]) == 3  # left for the lecturer


def test_alternative_text_is_suggested_by_a_model_that_reads_pictures(
    ai_on, settings, site, module, lecturer, client_for, ollama
):
    switch_on(site, drafts=True)
    picture = ContentItem.objects.create(
        module=module,
        kind="file",
        title="Seedlings",
        file=ContentFile(b"\x89PNG\r\n\x1a\nrest", name="s.png"),
    )
    ollama.answers = ['"Maize seedlings ten days after sowing, in rows on dark soil."']
    url = f"/api/v1/sites/{site.id}/ai/drafts/alt-text/"
    answer = client_for(lecturer.user).post(url, {"item": picture.id})
    assert answer.status_code == 201, answer.content
    assert (
        answer.json()["output"]["alt_text"] == "Maize seedlings ten days after sowing, in rows on dark soil."
    )
    assert ollama.sent[0]["model"] == "llava:7b" and ollama.sent[0]["images"]
    client_for(lecturer.user).post(
        f"/api/v1/ai/drafts/{answer.json()['draft']}/saved/", {"record": "content", "id": picture.id}
    )
    assert AuditLog.objects.filter(action="ai_draft_saved", entity="courses.contentitem").exists()
    notes = office_file(module)
    assert client_for(lecturer.user).post(url, {"item": notes.id}).json()["code"] == "not_a_picture"
    settings.AI_VISION_MODEL = ""
    assert client_for(lecturer.user).post(url, {"item": picture.id}).json()["code"] == "no_picture_model"


def test_a_draft_is_marked_saved_only_by_its_owner_and_only_for_its_course(
    ai_on, site, page, lecturer, make_person, client_for, ollama
):
    switch_on(site, drafts=True)
    ollama.answers = [json.dumps(QUESTIONS)]
    draft = (
        client_for(lecturer.user)
        .post(f"/api/v1/sites/{site.id}/ai/drafts/questions/", {"item": page.id})
        .json()
    )
    other = make_person("staff", "E0002", "Other", "Lecturer", "lecturer")
    url = f"/api/v1/ai/drafts/{draft['draft']}/saved/"
    assert client_for(other.user).post(url, {"record": "content", "id": page.id}).status_code == 404
    assert client_for(lecturer.user).post(url, {"record": "rubric", "id": 999999}).status_code == 404


# ---------------------------------------------------------------------------------------------------------
# The study helper


def test_the_helper_answers_from_the_course_material_and_shows_its_sources(
    ai_on, site, page, student, client_for, ollama
):
    switch_on(site, study_helper=True)
    ollama.answers = ["Loam is a balanced mixture of sand, silt and clay [1]."]
    client = client_for(student.user)
    assert client.get(f"/api/v1/sites/{site.id}/ai/").json()["helper_available"] is True
    answer = client.post(f"/api/v1/sites/{site.id}/ai/ask/", {"question": "Which soil suits most crops?"})
    assert answer.status_code == 200, answer.content
    body = answer.json()
    assert body["answered"] is True and body["sources"][0]["item"] == page.id
    assert body["sources"][0]["link"] == f"/sites/{site.id}/pages/{page.id}"
    prompt = ollama.sent[0]["prompt"] + ollama.sent[0]["system"]
    assert "Which soil suits most crops?" in prompt and "Loam is a balanced mixture" in prompt
    for personal in (student.first_name, student.last_name, student.external_id, student.email):
        assert personal not in prompt
    kept = Exchange.objects.get(kind="helper")
    assert kept.answered and kept.output is None and kept.sources == [page.id]
    assert not AuditLog.objects.filter(entity="assist.exchange").exists()  # never in the audit log


def test_the_helper_refuses_when_the_material_has_nothing(
    ai_on, site, page, module, student, client_for, ollama
):
    switch_on(site, study_helper=True)
    client = client_for(student.user)
    nothing = client.post(f"/api/v1/sites/{site.id}/ai/ask/", {"question": "Who won the cricket?"}).json()
    assert nothing["answered"] is False and nothing["sources"] == [] and ollama.sent == []
    ollama.answers = ["NOT_IN_MATERIAL"]
    unanswered = client.post(
        f"/api/v1/sites/{site.id}/ai/ask/", {"question": "How much clay is in Guyana?"}
    ).json()
    assert unanswered["answered"] is False and len(ollama.sent) == 1
    hidden = ContentItem.objects.create(
        module=module, kind="page", title="Draft notes", body="<p>Cricket scores</p>", is_published=False
    )
    assert (
        client.post(f"/api/v1/sites/{site.id}/ai/ask/", {"question": "cricket"}).json()["answered"] is False
    )
    assert hidden.id not in Exchange.objects.latest("at").sources
    assert client.post(f"/api/v1/sites/{site.id}/ai/ask/", {"question": "?!"}).json()["answered"] is False


def test_the_helper_is_off_until_the_course_switches_it_on(ai_on, site, page, student, client_for):
    answer = client_for(student.user).post(f"/api/v1/sites/{site.id}/ai/ask/", {"question": "loam"})
    assert answer.json()["code"] == "helper_off"


def test_the_helper_is_off_while_a_quiz_is_open_or_in_progress(
    ai_on, site, page, student, client_for, ollama
):
    from quizzes.models import Attempt, Quiz

    switch_on(site, study_helper=True)
    client = client_for(student.user)
    quiz = Quiz.objects.create(site=site, title="Soils test", is_published=True, attempts_allowed=1)
    status = client.get(f"/api/v1/sites/{site.id}/ai/").json()
    assert status["helper_available"] is False and "Soils test" in status["helper_reason"]
    refused = client.post(f"/api/v1/sites/{site.id}/ai/ask/", {"question": "loam"})
    assert refused.status_code == 403 and refused.json()["code"] == "assessment_open"
    Attempt.objects.create(quiz=quiz, student=student, started_at=timezone.now())
    assert "in progress" in client.get(f"/api/v1/sites/{site.id}/ai/").json()["helper_reason"]
    Attempt.objects.update(state="finished", submitted_at=timezone.now())  # no attempts left
    assert client.get(f"/api/v1/sites/{site.id}/ai/").json()["helper_available"] is True
    Quiz.objects.create(
        site=site, title="Later", is_published=True, opens_at=timezone.now() + timedelta(days=3)
    )
    Quiz.objects.create(site=site, title="Practice", is_published=True, is_practice=True)
    assert client.get(f"/api/v1/sites/{site.id}/ai/").json()["helper_available"] is True
    assert ollama.sent == []


def test_the_helper_is_off_while_an_assignment_is_open_to_the_student(
    ai_on, settings, site, page, assignment, student, client_for
):
    from assessments.models import Submission

    switch_on(site, study_helper=True)
    client = client_for(student.user)
    assert "Soil sampling report" in client.get(f"/api/v1/sites/{site.id}/ai/").json()["helper_reason"]
    Submission.objects.create(assignment=assignment, student=student, submitted_at=timezone.now())
    assert client.get(f"/api/v1/sites/{site.id}/ai/").json()["helper_available"] is True
    Submission.objects.all().delete()
    settings.AI_HELPER_OFF_DURING_ASSIGNMENTS = False
    assert client.get(f"/api/v1/sites/{site.id}/ai/").json()["helper_available"] is True


def test_teaching_staff_may_try_the_helper_during_assessments(
    ai_on, site, page, assignment, lecturer, client_for, ollama
):
    switch_on(site, study_helper=True)
    ollama.answers = ["Loam [1]."]
    answer = client_for(lecturer.user).post(f"/api/v1/sites/{site.id}/ai/ask/", {"question": "loam"})
    assert answer.json()["answered"] is True


def test_exchanges_go_with_the_activity_logs(ai_on, site):
    from privacy.retention import purge

    old = Exchange.objects.create(site=site, kind="helper")
    Exchange.objects.filter(pk=old.pk).update(at=timezone.now() - timedelta(days=400))
    recent = Exchange.objects.create(site=site, kind="helper")
    assert purge()["ai-exchanges"] == 1
    assert list(Exchange.objects.values_list("id", flat=True)) == [recent.id]
