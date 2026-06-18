from django.contrib import admin
from .models import CandidateProfile


@admin.register(CandidateProfile)
class CandidateProfileAdmin(admin.ModelAdmin):
    list_display  = ('user', 'published', 'published_at', 'updated_at')
    list_filter   = ('published',)
    search_fields = ('user__username', 'user__email', 'bio', 'location')
    readonly_fields = ('published_at', 'created_at', 'updated_at')
