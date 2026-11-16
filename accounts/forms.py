from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.utils.translation import gettext_lazy as _
from .models import CustomUser, PatientProfile, PsychologueProfile
from consultations.models import DoctorRating

User = get_user_model()


class DoctorRatingForm(forms.ModelForm):
    class Meta:
        model = DoctorRating
        fields = ["rating", "comment"]
        widgets = {
            "rating": forms.RadioSelect(
                choices=[(value, f"{value} ★") for value in range(1, 6)],
                attrs={"class": "rating-choice"},
            ),
            "comment": forms.Textarea(
                attrs={
                    "rows": 3,
                    "maxlength": 2000,
                    "placeholder": "تعليق اختياري",
                }
            ),
        }

    def clean_comment(self):
        comment = self.cleaned_data["comment"]
        if len(comment) > 2000:
            raise forms.ValidationError("يجب ألا يتجاوز التعليق 2000 حرف.")
        return comment


class PatientRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={
        'class': 'form-control',
        'placeholder': 'ex: marie.dupont@email.com'
    }))
    first_name = forms.CharField(required=True, widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': 'Prénom'
    }))
    last_name = forms.CharField(required=True, widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': 'Nom'
    }))
    phone = forms.CharField(required=True, widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': '06 12 34 56 78'
    }))

    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'email', 'phone', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Mot de passe'
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Confirmer le mot de passe'
        })

    def save(self, commit=True):
        user = super().save(commit=False)
        user.user_type = 'patient'
        user.username = user.email
        if commit:
            user.save()
            PatientProfile.objects.create(user=user)
        return user


class PsychologueRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={
        'class': 'form-control',
        'placeholder': 'Email professionnel'
    }))
    first_name = forms.CharField(required=True, widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': 'Prénom'
    }))
    last_name = forms.CharField(required=True, widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': 'Nom'
    }))
    phone = forms.CharField(required=True, widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': 'Téléphone'
    }))
    license_number = forms.CharField(required=True, widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': 'Numéro de licence'
    }))
    diploma = forms.CharField(required=True, widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': 'Diplôme'
    }))
    experience_years = forms.IntegerField(required=True, widget=forms.NumberInput(attrs={
        'class': 'form-control',
        'placeholder': 'Années d\'expérience'
    }))

    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'email', 'phone', 'license_number', 'diploma', 'experience_years', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Mot de passe'
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Confirmer le mot de passe'
        })

    def save(self, commit=True):
        user = super().save(commit=False)
        user.user_type = 'psychologue'
        user.is_active = False 
        user.username = user.email
        if commit:
            user.save()
            PsychologueProfile.objects.create(
                user=user,
                license_number=self.cleaned_data['license_number'],
                diploma=self.cleaned_data['diploma'],
                experience_years=self.cleaned_data['experience_years']
            )
        return user


class LoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': 'Email ou téléphone'
    }))
    password = forms.CharField(widget=forms.PasswordInput(attrs={
        'class': 'form-control',
        'placeholder': 'Mot de passe'
    }))


class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone', 'avatar']


class PatientProfileForm(forms.ModelForm):
    class Meta:
        model = PatientProfile
        fields = ['medical_history']


class PsychologueProfileForm(forms.ModelForm):
    class Meta:
        model = PsychologueProfile
        fields = ['specialty', 'biography', 'languages', 'hourly_rate']


class DeleteAccountForm(forms.Form):
    password = forms.CharField(
        label=_("Mot de passe actuel"),
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    confirm = forms.BooleanField(
        label=_("Je comprends que cette action est définitive."),
        error_messages={"required": _("Vous devez confirmer la suppression du compte.")},
    )

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise forms.ValidationError(_("Le mot de passe est incorrect."))
        return password