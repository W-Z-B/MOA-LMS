"""Paper quizzes for a room without devices (item 3.24).

A paper is drawn once from a quiz: its questions are fixed when it is made (random slots draw then), and it
is printed in one or two versions, A and B, with the questions and the options in another order in B. Each
student's answers are keyed in from their answer sheet, on a grid or from a spreadsheet, and become an
attempt at the quiz: marked by the same rules as an online attempt and counted the same way.
"""

from django.db import models

from core.models import TimeStampedModel


class PaperQuiz(TimeStampedModel):
    quiz = models.ForeignKey("quizzes.Quiz", on_delete=models.CASCADE, related_name="papers")
    title = models.CharField(max_length=160)
    sat_on = models.DateField(help_text="The day the paper is sat; the attempts are dated then")

    class Meta:
        ordering = ["quiz", "-sat_on", "id"]
        verbose_name_plural = "paper quizzes"

    def __str__(self) -> str:
        return f"{self.quiz}: {self.title}"


class PaperVersion(models.Model):
    """One printed version. items: [{"version": QuestionVersion id, "max_mark": "2.00", "layout": {...}}] in
    the order printed; the layout fixes the order of the options, so a letter on a sheet means one option."""

    paper = models.ForeignKey(PaperQuiz, on_delete=models.CASCADE, related_name="versions")
    label = models.CharField(max_length=2)
    items = models.JSONField(default=list)

    class Meta:
        ordering = ["paper", "label"]
        constraints = [models.UniqueConstraint(fields=["paper", "label"], name="paper_version_label_once")]

    def __str__(self) -> str:
        return f"{self.paper} version {self.label}"


class PaperScript(TimeStampedModel):
    """One student's answer sheet as keyed in, and the attempt it made."""

    paper = models.ForeignKey(PaperQuiz, on_delete=models.CASCADE, related_name="scripts")
    version = models.ForeignKey(PaperVersion, on_delete=models.PROTECT, related_name="scripts")
    student = models.ForeignKey("people.PersonRef", on_delete=models.PROTECT, related_name="paper_scripts")
    attempt = models.OneToOneField("quizzes.Attempt", on_delete=models.CASCADE, related_name="paper_script")
    cells = models.JSONField(default=list, help_text="What was keyed for each question, in printed order")

    class Meta:
        ordering = ["paper", "student"]
        constraints = [models.UniqueConstraint(fields=["paper", "student"], name="paper_script_once")]

    def __str__(self) -> str:
        return f"{self.student} on {self.paper}"
