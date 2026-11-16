from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ai_service", "0002_stressassessmentresult_supportconversation_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="sessionsummary",
            name="sentiment",
            field=models.CharField(blank=True, max_length=20),
        ),
    ]
