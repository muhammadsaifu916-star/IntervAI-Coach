from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('interviews', '0003_interview_session_metadata'),
    ]

    operations = [
        migrations.AddField(
            model_name='interviewquestion',
            name='generation_source',
            field=models.CharField(
                blank=True,
                default='curated',
                help_text='llm | curated | dataset | dynamic',
                max_length=20,
            ),
        ),
    ]
