from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


def seed_packages(apps, schema_editor):
    Package = apps.get_model('payments', 'Package')
    Package.objects.update_or_create(
        slug='basic',
        defaults={
            'name': 'Basic Package', 'price': 3000, 'profile_limit': 3,
            'validity_days': 7, 'sort_order': 1, 'recommended': False,
            'features': [
                'Unlock up to 3 candidate profiles',
                'Valid for 7 days',
                'Full contact information & AI assessment scores',
                'Detailed interview reports',
                
                'Unlocked profiles stay accessible forever',
            ],
        },
    )
    Package.objects.update_or_create(
        slug='professional',
        defaults={
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
    )
    Package.objects.update_or_create(
        slug='enterprise',
        defaults={
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
    )


def unseed_packages(apps, schema_editor):
    apps.get_model('payments', 'Package').objects.all().delete()


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Package',
            fields=[
                ('id',            models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug',          models.CharField(choices=[('basic','Basic'),('professional','Professional'),('enterprise','Enterprise')], max_length=20, unique=True)),
                ('name',          models.CharField(max_length=100)),
                ('price',         models.DecimalField(decimal_places=2, max_digits=8)),
                ('profile_limit', models.PositiveIntegerField(help_text='0 = unlimited')),
                ('validity_days', models.PositiveIntegerField()),
                ('features',      models.JSONField(default=list, help_text='List of feature strings')),
                ('recommended',   models.BooleanField(default=False)),
                ('sort_order',    models.PositiveIntegerField(default=0)),
            ],
            options={'ordering': ['sort_order']},
        ),
        migrations.CreateModel(
            name='Purchase',
            fields=[
                ('id',             models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('package_name',   models.CharField(max_length=100)),
                ('price_paid',     models.DecimalField(decimal_places=2, max_digits=8)),
                ('profile_limit',  models.PositiveIntegerField()),
                ('validity_days',  models.PositiveIntegerField()),
                ('purchased_at',   models.DateTimeField(auto_now_add=True)),
                ('expires_at',     models.DateTimeField()),
                ('payment_method', models.CharField(default='card', max_length=20)),
                ('transaction_id', models.CharField(blank=True, default='', max_length=64)),
                ('employer',       models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='purchases', to=settings.AUTH_USER_MODEL)),
                ('package',        models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='purchases', to='payments.package')),
            ],
            options={'ordering': ['-purchased_at']},
        ),
        migrations.CreateModel(
            name='ProfileUnlock',
            fields=[
                ('id',          models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('unlocked_at', models.DateTimeField(auto_now_add=True)),
                ('candidate',   models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='unlocked_by_employers', to=settings.AUTH_USER_MODEL)),
                ('employer',    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='profile_unlocks', to=settings.AUTH_USER_MODEL)),
                ('purchase',    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='unlocks', to='payments.purchase')),
            ],
            options={'ordering': ['-unlocked_at']},
        ),
        migrations.AddConstraint(
            model_name='profileunlock',
            constraint=models.UniqueConstraint(fields=['employer', 'candidate'], name='unique_employer_candidate_unlock'),
        ),
        migrations.RunPython(seed_packages, reverse_code=unseed_packages),
    ]
