# Records the model change of User.email_verified default (True -> False).
# This only changes the field default applied to NEW rows going forward; it does
# not alter existing rows. It exists so Django stops warning about an unmigrated
# model change and so the schema state matches models.py.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0004_user_email_verified_emailverificationotp'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='email_verified',
            field=models.BooleanField(default=False),
        ),
    ]
