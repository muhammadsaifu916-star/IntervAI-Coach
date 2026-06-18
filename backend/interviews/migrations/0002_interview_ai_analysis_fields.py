from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('interviews', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='interviewsession',
            name='communication_score',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='interviewsession',
            name='grammar_score',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='interviewsession',
            name='confidence_score',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='interviewsession',
            name='filler_ratio',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='interviewsession',
            name='analysis_data',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='interviewsession',
            name='improvement_plan',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='interviewsession',
            name='progress_report',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='interviewanswer',
            name='score',
            field=models.FloatField(blank=True, null=True),
        ),
    ]
