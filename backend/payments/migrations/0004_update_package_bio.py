from django.db import migrations
from decimal import Decimal


PACKAGES = {
    'basic': {
        'name': 'Basic Package',
        'price': Decimal('3000.00'),
        'profile_limit': 3,
        'validity_days': 7,
        'sort_order': 1,
        'recommended': False,
        'features': [
            'Unlock up to 3 candidate profiles',
            'Valid for 7 days',
            'Full contact information & AI assessment scores',
            'Unlocked profiles stay accessible forever',
        ],
    },
    'professional': {
        'name': 'Professional Package',
        'price': Decimal('9500.00'),
        'profile_limit': 10,
        'validity_days': 30,
        'sort_order': 2,
        'recommended': True,
        'features': [
            'Unlock up to 10 candidate profiles',
            'Valid for 30 days',
            'Full contact information & AI assessment scores',
            'Unlocked profiles stay accessible forever',
        ],
    },
    'enterprise': {
        'name': 'Enterprise Package',
        'price': Decimal('25000.00'),
        'profile_limit': 0,
        'validity_days': 90,
        'sort_order': 3,
        'recommended': False,
        'features': [
            'Unlock unlimited candidate profiles',
            'Valid for 90 days',
            'Full contact information & AI assessment scores',
            'Unlocked profiles stay accessible forever',
        ],
    },
}


def update_package_bio(apps, schema_editor):
    Package = apps.get_model('payments', 'Package')

    for slug, data in PACKAGES.items():
        Package.objects.update_or_create(
            slug=slug,
            defaults=data,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0003_update_package_pricing'),
    ]

    operations = [
        migrations.RunPython(update_package_bio),
    ]