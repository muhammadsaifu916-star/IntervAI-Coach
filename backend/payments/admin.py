from datetime import timedelta
from django.contrib import admin
from django.utils import timezone
from .models import Purchase, ProfileUnlock

class ProfileUnlockInline(admin.TabularInline):
    model = ProfileUnlock
    extra = 0
    readonly_fields = ('candidate', 'unlocked_at', 'employer')


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = (
        'employer',
        'package_name',
        'price_paid',
        'purchased_at',
        'expires_at',
        'status_label',
    )
    list_filter = ('package_name',)
    search_fields = ('employer__username', 'employer__email', 'transaction_id')
    inlines = [ProfileUnlockInline]

    fields = (
        'employer',
        'package',
        'payment_method',
        'package_name',
        'price_paid',
        'profile_limit',
        'validity_days',
        'purchased_at',
        'expires_at',
        'transaction_id',
        'status_label',
    )

    readonly_fields = (
        'package_name',
        'price_paid',
        'profile_limit',
        'validity_days',
        'purchased_at',
        'expires_at',
        'transaction_id',
        'status_label',
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'employer':
            kwargs['queryset'] = db_field.remote_field.model.objects.filter(
                role='employer'
            ).order_by('username', 'email')

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_changeform_initial_data(self, request):
        data = super().get_changeform_initial_data(request)
        data['payment_method'] = 'Bank Transfer'
        return data

    def save_model(self, request, obj, form, change):
        if obj.package:
            obj.package_name = obj.package.name
            obj.price_paid = obj.package.price
            obj.profile_limit = obj.package.profile_limit
            obj.validity_days = obj.package.validity_days

        if not obj.expires_at:
            obj.expires_at = timezone.now() + timedelta(days=obj.validity_days)

        if not obj.payment_method:
            obj.payment_method = 'bank_transfer'

        super().save_model(request, obj, form, change)

@admin.register(ProfileUnlock)
class ProfileUnlockAdmin(admin.ModelAdmin):
    list_display  = ('employer', 'candidate', 'unlocked_at', 'purchase')
    search_fields = ('employer__username', 'candidate__username')
