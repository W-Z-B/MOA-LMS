"""Load test (item 7.08): a whole class sits one quiz at once while others use the LMS as usual.

Locust (MIT) is a development tool: it never ships and runs from its own image (docs/performance.md says
how). The data comes from `manage.py seed_load --fictional --students 90`: the first QUIZ_TAKERS accounts
sit the quiz, the rest browse, and the lecturer watches the attempts come in.

    LOAD_USER_PASSWORD   the password seed_load gave the fictional accounts
    LOAD_TOTP_SECRET     the lecturer's authenticator secret seed_load enrolled (base32)
    QUIZ_TAKERS          how many of the class sit the quiz (default 60)
    THINK_MIN, THINK_MAX seconds a person pauses between actions (default 3 and 10)

Every request is named by what it is, not its address, so the results group by page.
"""

import base64
import hashlib
import hmac
import itertools
import os
import random
import struct
import time

from locust import HttpUser, between, task
from locust.exception import StopUser

PASSWORD = os.environ.get("LOAD_USER_PASSWORD", "")
QUIZ_TAKERS = int(os.environ.get("QUIZ_TAKERS", "60"))
THINK = between(float(os.environ.get("THINK_MIN", "3")), float(os.environ.get("THINK_MAX", "10")))
_takers = itertools.count(1)
_browsers = itertools.count(QUIZ_TAKERS + 1)


def totp(secret: str) -> str:
    """The current authenticator code for a base32 secret (RFC 6238), as the lecturer's app would show."""
    key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", int(time.time()) // 30), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    return f"{(struct.unpack('>I', digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1_000_000:06d}"


class Person(HttpUser):
    abstract = True
    wait_time = THINK
    username = ""

    def on_start(self):
        self.client.verify = False  # the test stack's own certificate
        self.client.headers.update({"Origin": self.host, "Referer": f"{self.host}/"})
        self.signed_out()
        answer = self.post(
            "/api/v1/auth/login/", {"username": self.username, "password": PASSWORD}, "sign in"
        )
        if answer.status_code != 200:
            raise StopUser(f"{self.username} could not sign in: {answer.status_code}")
        self.client.get("/api/v1/auth/me/", name="me")
        self.client.get("/api/v1/home/", name="home")
        sites = self.client.get("/api/v1/sites/", name="my courses").json()["results"]
        self.site = next(s["id"] for s in sites if s["code"].startswith("LOAD101"))
        self.pages = []

    def signed_out(self):
        """The web app's first call: refused before signing in, which is what it should be."""
        with self.client.get("/api/v1/auth/me/", name="me (signed out)", catch_response=True) as answer:
            if answer.status_code == 403:
                answer.success()

    def post(self, path, body, name, method="post"):
        token = self.client.cookies.get("csrftoken", "")
        return getattr(self.client, method)(path, json=body, name=name, headers={"X-CSRFToken": token})

    def browse(self):
        """A student between classes: Home, the course, a page or two, announcements, the calendar."""
        self.client.get("/api/v1/home/", name="home")
        self.client.get("/api/v1/to-do/", name="to do")
        contents = self.client.get(f"/api/v1/sites/{self.site}/contents/", name="course contents").json()
        if not self.pages:
            modules = contents.get("modules", []) if isinstance(contents, dict) else []
            self.pages = [item["id"] for module in modules for item in module.get("items", [])]
        for item in random.sample(self.pages, min(2, len(self.pages))):
            self.client.get(f"/api/v1/content/{item}/", name="a page")
        self.client.get(f"/api/v1/announcements/?site={self.site}", name="announcements")
        self.client.get("/api/v1/notifications/", name="notifications")
        self.client.get("/api/v1/calendar/", name="calendar")


class QuizTaker(Person):
    """One of the class sitting the quiz: start, answer each question with a pause, turn the page, hand in;
    then carry on as usual."""

    weight = 2

    def on_start(self):
        self.username = f"load.student{next(_takers):02d}"
        super().on_start()
        quizzes = self.client.get(f"/api/v1/quizzes/?site={self.site}", name="quizzes").json()
        quizzes = quizzes.get("results", quizzes)
        self.quiz = next(q["id"] for q in quizzes if q["title"].startswith("Class test"))
        self.sat = False

    @task
    def sit_the_quiz(self):
        if self.sat:
            self.browse()
            return
        attempt = self.post(f"/api/v1/quizzes/{self.quiz}/start/", None, "quiz: start").json()
        aid = attempt["id"]
        questions = attempt.get("questions", [])
        page = attempt.get("current_page", 1)
        while True:
            for question in [q for q in questions if q.get("page", page) == page]:
                self._think()
                choice = random.choice(["a", "a", "b", "c", "d"])  # noqa: S311 - a test's pretend answer
                self.post(
                    f"/api/v1/quiz-attempts/{aid}/answers/{question['position']}/",
                    {"response": {"choice": choice}},
                    "quiz: save an answer",
                    method="put",
                )
            if page >= attempt.get("last_page", 1):
                break
            attempt = self.post(f"/api/v1/quiz-attempts/{aid}/next-page/", None, "quiz: next page").json()
            page = attempt.get("current_page", page + 1)
            questions = attempt.get("questions", questions)
        self.post(f"/api/v1/quiz-attempts/{aid}/submit/", None, "quiz: hand in")
        self.client.get(f"/api/v1/quiz-attempts/{aid}/", name="quiz: review")
        self.sat = True

    def _think(self):
        self.wait()


class Browser(Person):
    """A student of the course not sitting the quiz just now."""

    weight = 1

    def on_start(self):
        self.username = f"load.student{next(_browsers):02d}"
        super().on_start()

    @task
    def browse_the_course(self):
        self.browse()


class Lecturer(Person):
    """The lecturer, watching the attempts arrive."""

    fixed_count = 1

    def on_start(self):
        self.username = "load.lecturer"
        self.client.verify = False
        self.client.headers.update({"Origin": self.host, "Referer": f"{self.host}/"})
        self.signed_out()
        self.post("/api/v1/auth/login/", {"username": self.username, "password": PASSWORD}, "sign in")
        self.post(
            "/api/v1/auth/mfa/verify/",
            {"code": totp(os.environ.get("LOAD_TOTP_SECRET", ""))},
            "authenticator",
        )
        sites = self.client.get("/api/v1/sites/", name="my courses").json()["results"]
        self.site = next(s["id"] for s in sites if s["code"].startswith("LOAD101"))
        quizzes = self.client.get(f"/api/v1/quizzes/?site={self.site}", name="quizzes").json()
        self.quiz = next(
            q["id"] for q in quizzes.get("results", quizzes) if q["title"].startswith("Class test")
        )

    @task
    def watch(self):
        self.client.get(f"/api/v1/quizzes/{self.quiz}/attempts/", name="lecturer: attempts")
        self.client.get(f"/api/v1/sites/{self.site}/gradebook/", name="lecturer: gradebook")
