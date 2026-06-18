from django.contrib import admin
from .models import QuizSession, QuizQuestion


class QuizQuestionInline(admin.TabularInline):
    model = QuizQuestion
    extra = 0
    fields = (
        "order",
        "question_text",
        "question_type",
        "options",
        "correct_answer",
        "difficulty",
    )
    readonly_fields = (
        "order",
        "question_text",
        "question_type",
        "options",
        "correct_answer",
        "difficulty",
    )
    can_delete = False


@admin.register(QuizSession)
class QuizSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "job_role",
        "attempt_number",
        "score",
        "passed",
        "started_at",
        "submitted_at",
        "cooldown_until",
    )
    list_filter = (
        "passed",
        "job_role",
        "started_at",
        "submitted_at",
    )
    search_fields = (
        "user__email",
        "job_role",
    )
    ordering = ("-started_at",)
    inlines = [QuizQuestionInline]