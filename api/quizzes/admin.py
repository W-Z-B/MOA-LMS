from django.contrib import admin

from quizzes.models import (
    Attempt,
    AttemptAnswer,
    Question,
    QuestionBank,
    QuestionCategory,
    QuestionVersion,
    Quiz,
    QuizOverride,
    QuizSlot,
)


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ("title", "site", "closes_at", "weight", "is_practice", "is_published")
    list_filter = ("is_published", "is_practice")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("name", "bank", "qtype", "is_archived")
    list_filter = ("qtype", "is_archived")


for model in (
    QuestionBank,
    QuestionCategory,
    QuestionVersion,
    QuizSlot,
    QuizOverride,
    Attempt,
    AttemptAnswer,
):
    admin.site.register(model)
