from django.contrib import admin
from .models import InterviewSession, InterviewQuestion, InterviewAnswer


class InterviewQuestionInline(admin.TabularInline):
    model = InterviewQuestion
    extra = 0
    readonly_fields = ('order', 'question_type', 'category', 'question_text')


class InterviewAnswerInline(admin.TabularInline):
    model = InterviewAnswer
    extra = 0
    readonly_fields = ('question', 'transcript', 'answered_at')


@admin.register(InterviewSession)
class InterviewSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'job_role', 'attempt_number', 'score', 'passed', 'submitted_at')
    list_filter  = ('passed',)
    search_fields = ('user__username', 'user__email', 'job_role')
    inlines = [InterviewQuestionInline, InterviewAnswerInline]
