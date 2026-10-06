"""Student orientation (item 7.16): "Getting started with the GSA LMS", a short self-paced course taken in
the first week.

It is an ordinary course site with a catalogue entry, so it uses the same pages, quiz, logbook and
completion rules as every other course (item 5.03): it is complete when every page has been read. Staff join
it from the staff-development catalogue; students are enrolled on it at their first sign-in when
ORIENTATION_AUTO_ENROL is on (the default), and only once: someone a course administrator takes off it is not
put back.

ensure_course() makes the course and is safe to run again: it adds only what is missing and never changes
what a course administrator has edited since. The management command seed_orientation calls it.
"""

from dataclasses import dataclass, field

from django.conf import settings
from django.db import transaction

from audit.services import record, snapshot
from courses.models import ContentItem, CourseSite, Membership, Module
from courses.richtext import clean
from people.models import PersonRef
from staffdev.models import CatalogueEntry

TITLE = "Getting started with the GSA LMS"
DESCRIPTION = (
    "A short course on using the GSA LMS: finding your courses, handing in work, quizzes, the logbook, "
    "working on a phone with poor signal, and asking for help. It takes about an hour."
)

# (module title, [(page title, page body as HTML)])
MODULES: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "1. Finding your way",
        [
            (
                "Welcome to the GSA LMS",
                "<p>The GSA LMS is where your courses live: the material your lecturers put up, the work you "
                "hand in, your quizzes, your marks and feedback, and messages from your lecturers.</p>"
                "<p>This short course shows you how to use it. Read each page, try the practice quiz and the "
                "practice logbook entry, and you are done. It takes about an hour, and you can stop and come "
                "back at any time.</p>"
                "<p>When you have read a page, choose <strong>Mark complete</strong> at the bottom of it. "
                "The course is complete when every page is marked.</p>",
            ),
            (
                "Home, To do and search",
                "<ol><li><strong>Home</strong> shows the work due this week, feedback you have been given "
                "and how far you are in each course.</li>"
                "<li><strong>To do</strong> lists everything waiting for you, the oldest first. Work past "
                "its due date is marked overdue.</li>"
                "<li><strong>Search</strong> finds a course, a page, an assignment or a quiz by a word in "
                "its title. On a computer press Ctrl and K together; on a phone use the Search tab at the "
                "bottom.</li>"
                "<li>The <strong>bell</strong> at the top shows your notifications: new marks, messages and "
                "reminders before work is due.</li></ol>",
            ),
        ],
    ),
    (
        "2. Your courses",
        [
            (
                "Finding your course material",
                "<ol><li>Open <strong>My courses</strong> from Home.</li>"
                "<li>Choose a course. Its <strong>Content</strong> tab lists the weeks or topics, each with "
                "its pages, files and links.</li>"
                "<li>Open a page to read it, or a file to download it. Some material appears only from a set "
                "date, or after you have finished an earlier item; the course says when.</li></ol>",
            ),
            (
                "Handing in work",
                "<ol><li>Open the course and its <strong>Assignments</strong> tab.</li>"
                "<li>Choose the assignment and read what it asks for, when it is due and what kind of file "
                "it takes.</li>"
                "<li>Type your answer or attach your file, tick the statement that the work is your own, and "
                "hand it in.</li>"
                "<li>You get a receipt with the time it was received. Until it is marked you can hand in "
                "again, and the newest copy is the one marked.</li></ol>"
                "<p>If you cannot hand in on time for a good reason, ask your lecturer for an extension "
                "before the due date. Work handed in late may lose marks, as the assignment says.</p>",
            ),
            (
                "Quizzes",
                "<ol><li>Open the course and its <strong>Quizzes</strong> tab, and choose the quiz.</li>"
                "<li>Read how long you have and how many attempts you are allowed, then start.</li>"
                "<li>Each answer is saved as you give it. If the signal drops, carry on: your answers are "
                "kept on the phone and sent when the signal returns.</li>"
                "<li>Choose <strong>Submit</strong> when you have finished. A timed quiz is submitted for "
                "you when the time runs out.</li></ol>",
            ),
        ],
    ),
    (
        "3. Phones, the field and practice",
        [
            (
                "Using the LMS on a phone with poor signal",
                "<ol><li>Open the LMS in your phone's browser and add it to your home screen: it then opens "
                "like an app.</li>"
                "<li>Without signal, typed work, quiz answers, messages and logbook entries wait on the "
                "phone and are sent when the signal returns. The top of the screen says how many are "
                "waiting.</li>"
                "<li>A file needs signal to send. Save it on the phone and hand it in when you are back in "
                "range.</li>"
                "<li>On a shared phone, always sign out when you finish. What you left waiting is sent only "
                "when you sign in again, never under someone else's name.</li></ol>",
            ),
            (
                "Practice: write a logbook entry",
                "<p>Your practical work on the farm, in the laboratory or in the processing unit is recorded "
                "in each course's logbook, and your supervisor signs it off.</p>"
                "<ol><li>Open this course's <strong>Logbook</strong> tab.</li>"
                '<li>Add an entry: today\'s date, where you were (for example "Plot 7"), what you did (for '
                'example "Read the orientation course") and how long it took.</li>'
                "<li>Save it. It shows as waiting for sign-off. In your real courses your supervisor signs "
                "it or hands it back for correction.</li></ol>"
                "<p>This entry is only for practice; nobody marks it.</p>",
            ),
            (
                "Practice quiz",
                "<p>The <strong>Quizzes</strong> tab of this course has a short practice quiz about finding "
                "your way in the LMS. It does not count towards anything, and you may take it as many times "
                "as you like.</p>",
            ),
        ],
    ),
    (
        "4. Getting help",
        [
            (
                "Help, your data and who to ask",
                "<ol><li><strong>Help</strong> (from search, or the Help link at the top of most pages) "
                "explains each task step by step.</li>"
                "<li>If you are stuck, choose <strong>Ask for help</strong> on any help page. Your question "
                "goes to the course administrators with the page you were on, and the answer comes back to "
                "you as a notification.</li>"
                "<li>For a question about a course's work, write to your lecturer from "
                "<strong>Messages</strong>.</li>"
                "<li><strong>My data</strong> shows what the LMS holds about you, and lets you ask for a "
                "correction.</li></ol>",
            ),
        ],
    ),
]

BANK = "Orientation practice questions"
QUIZ = "Practice quiz: finding your way"
# (name, type, text, data)
QUESTIONS = [
    (
        "Where work is listed",
        "multichoice",
        "<p>Where do you see everything waiting for you, oldest first?</p>",
        {
            "single": True,
            "choices": [
                {"text": "To do", "fraction": 1, "feedback": "Yes. To do lists everything waiting for you."},
                {"text": "My account", "fraction": 0, "feedback": "My account is for your password."},
                {"text": "My data", "fraction": 0, "feedback": "My data shows what the LMS holds about you."},
            ],
        },
    ),
    (
        "Answers without signal",
        "truefalse",
        "<p>If the signal drops during a quiz, the answers you have given are lost.</p>",
        {
            "correct": False,
            "feedback_true": "Not so: answers wait on the phone and are sent when the signal returns.",
            "feedback_false": "Right: answers wait on the phone and are sent when the signal returns.",
        },
    ),
    (
        "Handing in again",
        "truefalse",
        "<p>Until your work is marked, you may hand it in again, and the newest copy is marked.</p>",
        {
            "correct": True,
            "feedback_true": "Right.",
            "feedback_false": "In fact you may: the newest copy is the one marked.",
        },
    ),
    (
        "Asking for help",
        "multichoice",
        "<p>You are stuck on a screen. What is the quickest way to get help?</p>",
        {
            "single": True,
            "choices": [
                {
                    "text": "Choose Ask for help on a help page",
                    "fraction": 1,
                    "feedback": "Yes. It goes to the course administrators with the page you were on.",
                },
                {"text": "Sign out and in again", "fraction": 0, "feedback": "That rarely helps."},
                {"text": "Wait until the next class", "fraction": 0, "feedback": "You need not wait."},
            ],
        },
    ),
]


@dataclass
class Made:
    site: CourseSite
    added: list[str] = field(default_factory=list)


def site() -> CourseSite | None:
    return CourseSite.objects.filter(code=settings.ORIENTATION_SITE_CODE).first()


@transaction.atomic
def ensure_course() -> Made:
    """Make the orientation course, or add what is missing from it. Changes nothing that exists."""
    course, created = CourseSite.objects.get_or_create(
        code=settings.ORIENTATION_SITE_CODE,
        defaults={
            "title": TITLE,
            "description": DESCRIPTION,
            "kind": CourseSite.Kind.STAFF_DEVELOPMENT,
            "source": CourseSite.Source.LOCAL,
            "is_published": True,
        },
    )
    made = Made(course)
    if created:
        record(None, "create", course, after=snapshot(course), reason="seed_orientation")
        made.added.append("the course")
    _, created = CatalogueEntry.objects.get_or_create(
        site=course,
        defaults={
            "summary": DESCRIPTION,
            "audience": "Every new student, and any member of staff new to the LMS",
            "length_hours": 1,
            "self_enrol": CatalogueEntry.Enrol.OPEN,
            "rule_all_items": True,
            "issue_certificate": False,
        },
    )
    if created:
        made.added.append("its catalogue entry and completion rule")
    for position, (module_title, pages) in enumerate(MODULES, 1):
        module, created = Module.objects.get_or_create(
            site=course, title=module_title, defaults={"position": position}
        )
        if created:
            made.added.append(f"module {module_title}")
        for item_position, (title, body) in enumerate(pages, 1):
            _, created = ContentItem.objects.get_or_create(
                module=module,
                title=title,
                defaults={"kind": ContentItem.Kind.PAGE, "body": clean(body), "position": item_position},
            )
            if created:
                made.added.append(f"page {title}")
    if _ensure_quiz(course):
        made.added.append("the practice quiz")
    return made


def _ensure_quiz(course: CourseSite) -> bool:
    from quizzes import schemas
    from quizzes.models import Question, QuestionBank, QuestionVersion, Quiz, QuizSlot

    if Quiz.objects.filter(site=course, title=QUIZ).exists():
        return False
    bank, _ = QuestionBank.objects.get_or_create(site=course, name=BANK)
    quiz = Quiz.objects.create(
        site=course,
        title=QUIZ,
        description="<p>Four questions on finding your way in the LMS. "
        "It does not count towards anything.</p>",
        attempts_allowed=0,
        is_practice=True,
        review_correct=Quiz.Review.IMMEDIATELY,
    )
    for position, (name, qtype, text, data) in enumerate(QUESTIONS, 1):
        question = Question.objects.filter(bank=bank, name=name).first()
        if question is None:
            question = Question.objects.create(bank=bank, qtype=qtype, name=name)
            QuestionVersion.objects.create(
                question=question, text=text, data=schemas.validate_question(qtype, text, data)
            )
        QuizSlot.objects.create(quiz=quiz, position=position, question=question)
    quiz.is_published = True
    quiz.save(update_fields=["is_published"])
    record(None, "create", quiz, after=snapshot(quiz), reason="seed_orientation")
    return True


def enrol_new_student(person: PersonRef | None, *, request=None) -> Membership | None:
    """Put a student on the orientation course at their first sign-in. Nothing when the setting is off, the
    course has not been made, the person is not a student, or they have ever been on it (a course
    administrator may have taken them off)."""
    if not settings.ORIENTATION_AUTO_ENROL or person is None or person.kind != PersonRef.Kind.STUDENT:
        return None
    course = site()
    if course is None or not course.is_published:
        return None
    membership, created = Membership.objects.get_or_create(
        site=course, person=person, defaults={"role": Membership.SiteRole.STUDENT}
    )
    if not created:
        return None
    record(
        request,
        "enrolled",
        membership,
        after=snapshot(membership),
        reason="Enrolled on the orientation course at first sign-in",
    )
    return membership
