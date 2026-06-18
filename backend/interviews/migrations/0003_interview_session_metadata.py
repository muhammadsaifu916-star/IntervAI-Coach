from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('interviews', '0002_interview_ai_analysis_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='interviewsession',
            name='years_experience',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='interviewsession',
            name='experience_band',
            field=models.CharField(blank=True, default='', max_length=40),
        ),
        migrations.AddField(
            model_name='interviewsession',
            name='monitoring_data',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='interviewsession',
            name='answer_timings',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
