from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('consultations', '0010_recurringsession_patient_note_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='consultation',
            name='is_replacement',
            field=models.BooleanField(
                default=False, help_text='Séance de rattrapage gratuite'
            ),
        ),
        migrations.AddField(
            model_name='consultation',
            name='replaced_consultation',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='replacements',
                to='consultations.consultation',
                help_text='La séance annulée remplacée',
            ),
        ),
        migrations.AddField(
            model_name='consultation',
            name='replacement_declined_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text='Date à laquelle le patient a refusé la séance de rattrapage',
            ),
        ),
    ]