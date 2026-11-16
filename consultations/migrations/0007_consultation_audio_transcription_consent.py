from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("consultations", "0006_consultation_doctor_only_ai_summary"),
    ]

    operations = [
        migrations.AddField(
            model_name="consultation",
            name="audio_transcription_consent",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="consultation",
            name="audio_transcription_consent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
