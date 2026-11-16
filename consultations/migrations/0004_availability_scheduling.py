import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('consultations', '0003_paymentrecord'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='creneau',
            name='is_generated',
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name='creneau',
            name='is_bookable',
            field=models.BooleanField(db_index=True, default=True),
        ),
        migrations.CreateModel(
            name='WeeklyAvailabilityRule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('weekday', models.PositiveSmallIntegerField(choices=[(0, 'Lundi'), (1, 'Mardi'), (2, 'Mercredi'), (3, 'Jeudi'), (4, 'Vendredi'), (5, 'Samedi'), (6, 'Dimanche')])),
                ('start_time', models.TimeField()),
                ('end_time', models.TimeField()),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('psychologue', models.ForeignKey(limit_choices_to={'user_type': 'psychologue'}, on_delete=django.db.models.deletion.CASCADE, related_name='weekly_availability_rules', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['weekday', 'start_time'],
            },
        ),
        migrations.AddConstraint(
            model_name='weeklyavailabilityrule',
            constraint=models.UniqueConstraint(fields=('psychologue', 'weekday', 'start_time'), name='week_avail_start_unique'),
        ),
        migrations.AddConstraint(
            model_name='weeklyavailabilityrule',
            constraint=models.CheckConstraint(check=models.Q(('start_time__lt', models.F('end_time'))), name='week_avail_interval_ok'),
        ),
        migrations.CreateModel(
            name='AvailabilityException',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('kind', models.CharField(choices=[('closed', 'Fermeture'), ('replacement', 'Remplacement des horaires'), ('additional', 'Période supplémentaire')], max_length=20)),
                ('start_time', models.TimeField(blank=True, null=True)),
                ('end_time', models.TimeField(blank=True, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('psychologue', models.ForeignKey(limit_choices_to={'user_type': 'psychologue'}, on_delete=django.db.models.deletion.CASCADE, related_name='availability_exceptions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['date', 'kind', 'start_time'],
                'indexes': [
                    models.Index(fields=['psychologue', 'date', 'is_active'], name='consultatio_psychol_8d706c_idx'),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name='availabilityexception',
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ('end_time__isnull', True),
                        ('kind', 'closed'),
                        ('start_time__isnull', True),
                    ),
                    models.Q(
                        ('end_time__isnull', False),
                        ('kind__in', ['replacement', 'additional']),
                        ('start_time__isnull', False),
                        ('start_time__lt', models.F('end_time')),
                    ),
                    _connector='OR',
                ),
                name='avail_exception_interval_ok',
            ),
        ),
        migrations.AddConstraint(
            model_name='availabilityexception',
            constraint=models.UniqueConstraint(
                condition=models.Q(('is_active', True), ('kind', 'closed')),
                fields=('psychologue', 'date'),
                name='avail_active_closure_unique',
            ),
        ),
    ]
