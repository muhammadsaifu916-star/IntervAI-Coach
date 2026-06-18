from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('quizzes', '0002_quizanswer'),
    ]

    operations = [
        migrations.AddField(
            model_name='quizquestion',
            name='topic',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='quizquestion',
            name='subtopic',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='quizquestion',
            name='explanation',
            field=models.TextField(blank=True, default=''),
        ),
    ]
