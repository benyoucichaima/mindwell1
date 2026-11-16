from datetime import time

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser, PsychologueProfile
from consultations.models import Creneau


class ManageAvailabilityRenderTests(TestCase):
    def test_recurring_block_renders(self):
        psych = CustomUser.objects.create_user(
            username='render-psych', password='x', user_type='psychologue'
        )
        patient = CustomUser.objects.create_user(
            username='render-patient', password='x', user_type='patient'
        )
        PsychologueProfile.objects.create(user=psych, is_verified=True)
        self.client.force_login(psych)

        response = self.client.get(reverse('consultations:manage_availability'))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('id="recurring-block"', html)
        self.assertIn('recurring_sessions.js', html)
        self.assertIn('name="patient_id"', html)
        self.assertIn('name="start_time"', html)
        self.assertIn('name="weekday"', html)

    def test_creneaux_grouped_in_accordion(self):
        psych = CustomUser.objects.create_user(
            username='accordion-psych', password='x', user_type='psychologue'
        )
        PsychologueProfile.objects.create(user=psych, is_verified=True)
        today = timezone.localdate()
        Creneau.objects.create(
            psychologue=psych,
            date=today,
            heure_debut=time(9, 0),
            heure_fin=time(9, 45),
            statut=Creneau.Statut.LIBRE,
        )
        self.client.force_login(psych)

        response = self.client.get(reverse('consultations:manage_availability'))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('id="creneaux-accordion"', html)
        self.assertIn('class="accordion-header"', html)
        self.assertIn('data-date="%s"' % today.isoformat(), html)
        self.assertIn('créneau', html)
        self.assertIn('id="btn-deplier-tout"', html)
        self.assertIn('id="btn-replier-tout"', html)