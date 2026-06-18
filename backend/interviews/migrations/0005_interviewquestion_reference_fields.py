from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('interviews', '0004_interviewquestion_generation_source'),
    ]

    operations = [
        migrations.AddField(
            model_name='interviewquestion',
            name='reference_keywords',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='interviewquestion',
            name='reference_points',
            field=models.TextField(blank=True, default=''),
        ),
    ]
