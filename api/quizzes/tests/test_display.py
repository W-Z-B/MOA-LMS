"""Question text reaches the page as cleaned HTML: imported HTML against the course pages' allow-list
(courses.richtext), typed text as paragraphs. The web app places it in the page as it is."""

import pytest

from quizzes.api import rich, shown_data

HOSTILE = (
    '<p onclick="steal()">Which <strong>soil</strong> holds water?</p>'
    "<script>alert(1)</script>"
    '<img src="x" onerror="alert(2)">'
    '<a href="javascript:alert(3)">more</a>'
    '<a href="https://moa.gov.gy/">Ministry</a>'
    "<iframe src='https://evil.example'></iframe>"
    '<span data-math="x^2">x</span>'
)


def test_imported_html_is_cleaned_against_the_allow_list():
    cleaned = rich(HOSTILE)
    for banned in ("<script", "alert(1)", "onerror", "onclick", "javascript:", "<iframe", 'src="x"'):
        assert banned not in cleaned
    assert "<strong>soil</strong>" in cleaned
    assert 'href="https://moa.gov.gy/"' in cleaned and 'rel="noopener noreferrer"' in cleaned
    assert 'data-math="x^2"' in cleaned


def test_images_need_an_address_on_the_lms_and_get_alternative_text():
    kept = rich('<p>Look:</p><img src="/api/v1/content/4/download/" width="40">')
    assert kept == '<p>Look:</p><img alt="" src="/api/v1/content/4/download/" width="40">'
    described = rich('<img src="/api/v1/content/4/download/" alt="A seedling">')
    assert described == '<img src="/api/v1/content/4/download/" alt="A seedling">'
    assert rich('<p>Moodle file</p><img src="@@PLUGINFILE@@/leaf.png" alt="Leaf">') == "<p>Moodle file</p>"


def test_typed_text_becomes_paragraphs_and_keeps_gaps():
    assert rich("A < B & C\n\nThe [[1]] is red.") == "<p>A &lt; B &amp; C</p><p>The [[1]] is red.</p>"
    assert rich("") == ""


def test_choice_items_and_prompts_are_cleaned_too():
    mc = shown_data(
        "multichoice",
        {
            "single": True,
            "choices": [
                {"id": "a", "text": "<p>Clay<script>x()</script></p>", "feedback": "<b onmouseover=x>Yes</b>"}
            ],
        },
    )
    assert mc["choices"][0]["text"] == "<p>Clay</p>"
    assert "onmouseover" not in mc["choices"][0]["feedback"]
    assert mc["single"] is True
    matching = shown_data(
        "matching",
        {
            "prompts": [{"id": "a", "text": "<em>Loam</em><img src=x onerror=y>"}],
            "pairs": [{"prompt": "<i>x</i>"}],
        },
    )
    assert matching["prompts"][0]["text"] == "<em>Loam</em>"  # an image whose address was dropped goes too
    assert matching["pairs"][0]["prompt"] == "x"
    ordering = shown_data("ordering", {"items": [{"id": "a", "text": "<script>1</script>Sow"}]})
    assert ordering["items"][0]["text"] == "Sow"
    assert shown_data("truefalse", {"correct": True}) == {"correct": True}


@pytest.mark.django_db
def test_attempts_and_bank_listings_carry_clean_html(make_question, make_quiz, lecturer, student, client_for):
    question = make_question(text=HOSTILE)
    quiz = make_quiz([question])
    learner = client_for(student.user)
    attempt = learner.post(f"/api/v1/quizzes/{quiz.id}/start/").json()
    text = attempt["questions"][0]["text"]
    assert "<script" not in text and "onerror" not in text and "<strong>soil</strong>" in text
    listed = client_for(lecturer.user).get(f"/api/v1/questions/{question.id}/").json()["latest"]
    assert listed["text"] == HOSTILE  # as written, for editing
    assert "<script" not in listed["text_html"] and "javascript:" not in listed["text_html"]
