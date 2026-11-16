from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0010_delete_appointment'),
    ]

    operations = [
        migrations.AlterField(
            model_name='psychologueprofile',
            name='session_duration',
            field=models.IntegerField(
                choices=[
                    (45, '45 minutes'),
                    (50, '50 minutes'),
                    (60, '60 minutes'),
                    (75, '75 minutes'),
                ],
                default=45,
            ),
        ),
    ]
