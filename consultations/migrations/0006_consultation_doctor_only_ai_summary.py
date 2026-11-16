from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("consultations", "0005_doctorrating"),
    ]

    operations = [
        migrations.AddField(
            model_name="consultation",
            name="doctor_only_ai_summary",
            field=models.JSONField(blank=True, null=True),
        ),
    ]
