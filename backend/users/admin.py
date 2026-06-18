from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User
from django.contrib.auth.models import Group
from django.contrib.admin.sites import NotRegistered

class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Additional Info', {'fields': ('role', 'phone')}),
        ('Email Verification', {'fields': ('email_verified',)}),
        ('Retry Cooldowns', {'fields': ('quiz_cooldown_until', 'interview_cooldown_until')}),
    )

    list_display = (
        'username',
        'email',
        'first_name',
        'last_name',
        'role',
        'phone',
        'email_verified',
        'is_active',
        'is_staff',
    )
    list_filter = UserAdmin.list_filter + (
        'email_verified',
        'quiz_cooldown_until',
        'interview_cooldown_until',
    )
    actions = ['clear_cooldowns']

    @admin.action(description='Clear quiz & interview cooldowns')
    def clear_cooldowns(self, request, queryset):
        updated = queryset.update(quiz_cooldown_until=None, interview_cooldown_until=None)
        self.message_user(request, f'Cleared cooldowns for {updated} user(s).')

admin.site.register(User, CustomUserAdmin)

try:
    admin.site.unregister(Group)
except NotRegistered:
    pass