from django import forms
from django.utils import timezone
from datetime import datetime

from accounts.models import PsychologueProfile

from .models import AvailabilityException, WeeklyAvailabilityRule


class WeeklyAvailabilityRuleForm(forms.ModelForm):
    session_duration = forms.TypedChoiceField(
        choices=PsychologueProfile.SESSION_DURATION_CHOICES,
        coerce=int,
        label='Durée des séances',
    )

    class Meta:
        model = WeeklyAvailabilityRule
        fields = ('weekday', 'start_time', 'end_time', 'is_active')
        labels = {
            'weekday': 'Jour',
            'start_time': 'Début',
            'end_time': 'Fin',
            'is_active': 'Actif',
        }
        widgets = {
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
        }

    def __init__(self, *args, profile, **kwargs):
        self.profile = profile
        super().__init__(*args, **kwargs)
        self.fields['session_duration'].initial = profile.session_duration

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        if start_time and end_time and end_time <= start_time:
            self.add_error('end_time', 'L’heure de fin doit suivre l’heure de début.')
        return cleaned_data


class AvailabilityExceptionForm(forms.ModelForm):
    class Meta:
        model = AvailabilityException
        fields = ('date', 'kind', 'start_time', 'end_time')
        labels = {
            'date': 'Date',
            'kind': 'Type d’exception',
            'start_time': 'Début',
            'end_time': 'Fin',
        }
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        kind = cleaned_data.get('kind')
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        date = cleaned_data.get('date')
        if kind == AvailabilityException.Kind.CLOSED:
            cleaned_data['start_time'] = None
            cleaned_data['end_time'] = None
        elif not start_time or not end_time:
            raise forms.ValidationError('Les horaires de début et de fin sont requis.')
        elif end_time <= start_time:
            self.add_error('end_time', 'L’heure de fin doit suivre l’heure de début.')
        # Pour aujourd’hui, une heure de début déjà passée est refusée.
        if (
            date
            and start_time
            and date == timezone.localdate()
            and timezone.make_aware(
                datetime.combine(date, start_time), timezone.get_current_timezone()
            ) <= timezone.now()
        ):
            self.add_error(
                'start_time',
                "Pour aujourd'hui, l'heure de début doit être dans le futur.",
            )
        return cleaned_data
