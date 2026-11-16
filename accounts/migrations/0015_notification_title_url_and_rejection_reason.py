from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0014_reset_legacy_psychologist_ratings"),
    ]

    operations = [
        migrations.AddField(
            model_name="notification",
            name="title",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="notification",
            name="url",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="psychologueprofile",
            name="rejection_reason",
            field=models.TextField(blank=True),
        ),
    ]
