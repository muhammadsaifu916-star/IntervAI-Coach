from django.db import migrations


# Canonical package definitions (PKR pricing). Kept in sync with the seed in
# 0001_initial so that both fresh and already-migrated databases converge on
# the same values. Profile limits / validity were already correct; this updates
# pricing, currency, and feature copy.
PACKAGES = {
    'basic': {
        'name': 'Basic Package', 'price': 3000, 'profile_limit': 3,
        'validity_days': 7, 'sort_order': 1, 'recommended': False,
        'features': [
            'Unlock up to 3 candidate profiles',
            'Full contact information & AI assessment scores',
            'Detailed interview reports',
            'Valid for 7 days',
            'Unlocked profiles stay accessible forever',
        ],
    },
    'professional': {
        'name': 'Professional Package', 'price': 9500, 'profile_limit': 10,
        'validity_days': 30, 'sort_order': 2, 'recommended': True,
        'features': [
            'Unlock up to 10 candidate profiles',
            'Full contact information & AI assessment scores',
            'Detailed interview reports',
            'Valid for 30 days',
            'Unlocked profiles stay accessible forever',
            'Priority support',
        ],
    },
    'enterprise': {
        'name': 'Enterprise Package', 'price': 25000, 'profile_limit': 0,
        'validity_days': 90, 'sort_order': 3, 'recommended': False,
        'features': [
            'Unlock unlimited candidate profiles',
            'Full contact information & AI assessment scores',
            'Detailed interview reports',
            'Advanced search filters',
            'Valid for 90 days',
            'Unlocked profiles stay accessible forever',
            'Dedicated account manager',
            'Custom integration support',
        ],
    },
}


def update_pricing(apps, schema_editor):
    Package = apps.get_model('payments', 'Package')
    for slug, defaults in PACKAGES.items():
        Package.objects.update_or_create(slug=slug, defaults=defaults)


def noop(apps, schema_editor):
    # Pricing is data-only; nothing to undo on reverse.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0002_remove_profileunlock_unique_employer_candidate_unlock_and_more'),
    ]

    operations = [
        migrations.RunPython(update_pricing, reverse_code=noop),
    ]
