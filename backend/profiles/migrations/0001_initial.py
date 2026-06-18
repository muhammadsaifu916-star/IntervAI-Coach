from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CandidateProfile',
            fields=[
                ('id',               models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('bio',              models.TextField(blank=True, default='')),
                ('location',         models.CharField(blank=True, default='', max_length=120)),
                ('skills',           models.JSONField(blank=True, default=list)),
                ('projects_summary', models.TextField(blank=True, default='')),
                ('website',          models.URLField(blank=True, default='')),
                ('linkedin',         models.URLField(blank=True, default='')),
                ('github',           models.URLField(blank=True, default='')),
                ('show_contact',     models.BooleanField(default=True)),
                ('show_full_name',   models.BooleanField(default=True)),
                ('published',        models.BooleanField(default=False)),
                ('published_at',     models.DateTimeField(blank=True, null=True)),
                ('created_at',       models.DateTimeField(auto_now_add=True)),
                ('updated_at',       models.DateTimeField(auto_now=True)),
                ('user',             models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='candidate_profile', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-published_at', '-created_at']},
        ),
    ]
