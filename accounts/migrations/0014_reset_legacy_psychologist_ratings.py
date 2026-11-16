from django.db import migrations


def reset_legacy_ratings(apps, schema_editor):
    profile_model = apps.get_model("accounts", "PsychologueProfile")
    profile_model.objects.all().update(average_rating=None, review_count=0)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0013_alter_psychologueprofile_average_rating"),
    ]

    operations = [
        migrations.RunPython(
            reset_legacy_ratings,
            migrations.RunPython.noop,
        ),
    ]
