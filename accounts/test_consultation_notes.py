from datetime import time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import (
    ConsultationNote,
    CustomUser,
    Notification,
    PsychologueProfile,
)
from accounts import notes_service
from consultations.models import Consultation


class ConsultationNotesTests(TestCase):
    def setUp(self):
        self.psych = CustomUser.objects.create_user(
            username='note-psych', password='x', user_type='psychologue'
        )
        self.other_psych = CustomUser.objects.create_user(
            username='note-other-psych', password='x', user_type='psychologue'
        )
        # Verified profiles so @verification_required lets the psychologist in.
        PsychologueProfile.objects.create(user=self.psych, is_verified=True)
        PsychologueProfile.objects.create(user=self.other_psych, is_verified=True)
        self.patient = CustomUser.objects.create_user(
            username='note-patient', password='x', user_type='patient'
        )
        self.other_patient = CustomUser.objects.create_user(
            username='note-other-patient', password='x', user_type='patient'
        )
        self.consultation = Consultation.objects.create(
            patient=self.patient,
            psychologue=self.psych,
            date=timezone.localdate(),
            start_time=time(9),
            end_time=time(10),
            price=3000,
        )

    def test_patient_note_sends_notification_and_is_visible(self):
        note = notes_service.create_patient_note(
            psychologue=self.psych,
            patient=self.patient,
            content='Bonjour, voici votre note.',
        )
        self.assertIsNotNone(note.sent_at)
        self.assertTrue(note.is_visible_to_patient)

        # Notification created with title + url pointing to the note page.
        notif = Notification.objects.get(user=self.patient)
        self.assertEqual(notif.title, 'Nouvelle note de votre psychologue')
        self.assertEqual(
            notif.url,
            reverse('accounts:patient_note_detail', args=[note.pk]),
        )

        # Patient can read it.
        self.client.force_login(self.patient)
        resp = self.client.get(
            reverse('accounts:patient_note_detail', args=[note.pk])
        )
        self.assertEqual(resp.status_code, 200)

    def test_professional_note_never_visible_to_patient(self):
        note = notes_service.create_professional_note(
            psychologue=self.psych,
            patient=self.patient,
            content='Observation privée confidentielle.',
        )
        self.assertFalse(note.is_visible_to_patient)
        self.assertIsNone(note.sent_at)
        # No notification for private notes.
        self.assertFalse(Notification.objects.filter(user=self.patient).exists())

        # Patient cannot read it directly.
        self.client.force_login(self.patient)
        resp = self.client.get(
            reverse('accounts:patient_note_detail', args=[note.pk])
        )
        self.assertEqual(resp.status_code, 404)

        # Not returned by the patient-visible queryset.
        self.assertNotIn(
            note, list(notes_service.patient_visible_notes(self.patient))
        )

    def test_psychologist_cannot_note_non_patient(self):
        from django.core.exceptions import PermissionDenied

        with self.assertRaises(PermissionDenied):
            notes_service.create_professional_note(
                psychologue=self.psych,
                patient=self.other_patient,
                content='Je ne suis pas ce praticien.',
            )

    def test_empty_content_rejected(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            notes_service.create_patient_note(
                psychologue=self.psych, patient=self.patient, content='   '
            )

    def test_patient_cannot_read_other_patients_note(self):
        note = notes_service.create_patient_note(
            psychologue=self.psych,
            patient=self.patient,
            content='Note privée du patient A.',
        )
        self.client.force_login(self.other_patient)
        resp = self.client.get(
            reverse('accounts:patient_note_detail', args=[note.pk])
        )
        self.assertEqual(resp.status_code, 404)

    def test_patient_cannot_access_psychologist_notes_page(self):
        self.client.force_login(self.patient)
        resp = self.client.get(reverse('accounts:psychologue_notes'))
        self.assertEqual(resp.status_code, 403)

    def test_psychologue_notes_page_lists_both_kinds(self):
        notes_service.create_patient_note(
            psychologue=self.psych, patient=self.patient, content='Note patient.'
        )
        notes_service.create_professional_note(
            psychologue=self.psych, patient=self.patient, content='Note privée.'
        )
        self.client.force_login(self.psych)
        resp = self.client.get(
            reverse('accounts:psychologue_notes'),
            {'patient': self.patient.pk},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['notes']), 2)
        self.assertEqual(
            {n.note_type for n in resp.context['notes']},
            {'patient', 'professional'},
        )

    def test_psychologist_sees_only_own_notes(self):
        Consultation.objects.create(
            patient=self.patient,
            psychologue=self.other_psych,
            date=timezone.localdate(),
            start_time=time(11),
            end_time=time(12),
            price=3000,
        )
        notes_service.create_professional_note(
            psychologue=self.other_psych,
            patient=self.patient,
            content='Note d’un autre praticien.',
        )
        notes = notes_service.notes_for_psychologue(self.psych)
        self.assertEqual(list(notes), [])

    # --- Point 1: @verification_required -------------------------------
    def test_unverified_psychologist_cannot_open_notes_page(self):
        unverified = CustomUser.objects.create_user(
            username='unverified-psych', password='x', user_type='psychologue'
        )
        PsychologueProfile.objects.create(user=unverified, is_verified=False)
        self.client.force_login(unverified)
        resp = self.client.get(reverse('accounts:psychologue_notes'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('pending', resp.url)

    def test_unverified_psychologist_cannot_create_note(self):
        unverified = CustomUser.objects.create_user(
            username='unverified-psych2', password='x', user_type='psychologue'
        )
        PsychologueProfile.objects.create(user=unverified, is_verified=False)
        Consultation.objects.create(
            patient=self.patient, psychologue=unverified,
            date=timezone.localdate(), start_time=time(9), end_time=time(10),
            price=3000,
        )
        self.client.force_login(unverified)
        resp = self.client.post(
            reverse('accounts:psychologue_notes'),
            {
                'patient': self.patient.pk,
                'note_type': 'professional',
                'content': 'Doit être bloqué.',
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(
            ConsultationNote.objects.filter(content='Doit être bloqué.').exists()
        )

    # --- Point 2: consultation selector strictly filtered --------------
    def test_consultation_selector_only_own_patient(self):
        Consultation.objects.create(
            patient=self.patient, psychologue=self.other_psych,
            date=timezone.localdate(), start_time=time(14), end_time=time(15),
            price=3000,
        )
        self.client.force_login(self.psych)
        resp = self.client.get(
            reverse('accounts:psychologue_notes'), {'patient': self.patient.pk}
        )
        self.assertEqual(resp.status_code, 200)
        selector_ids = [c.pk for c in resp.context['consultations']]
        self.assertIn(self.consultation.pk, selector_ids)
        # The other psychologist's consultation must not be offered.
        other = Consultation.objects.get(
            patient=self.patient, psychologue=self.other_psych
        )
        self.assertNotIn(other.pk, selector_ids)

    # --- Point 3: consistency patient / psychologue / consultation -----
    def test_note_rejects_foreign_consultation(self):
        from django.core.exceptions import ValidationError

        other = Consultation.objects.create(
            patient=self.patient, psychologue=self.other_psych,
            date=timezone.localdate(), start_time=time(14), end_time=time(15),
            price=3000,
        )
        with self.assertRaises(ValidationError):
            notes_service.create_professional_note(
                psychologue=self.psych,
                patient=self.patient,
                content='Liaison invalide.',
                consultation_id=other.pk,
            )
        self.assertFalse(
            ConsultationNote.objects.filter(content='Liaison invalide.').exists()
        )

    def test_note_links_valid_consultation(self):
        note = notes_service.create_professional_note(
            psychologue=self.psych,
            patient=self.patient,
            content='Note liée.',
            consultation_id=self.consultation.pk,
        )
        self.assertEqual(note.consultation_id, self.consultation.pk)

    # --- Point 4: cancelled / no_show behaviour ------------------------
    def test_cancelled_only_allows_professional_note(self):
        Consultation.objects.filter(pk=self.consultation.pk).update(
            status=Consultation.Status.CANCELLED
        )
        # Professional documentation still allowed.
        note = notes_service.create_professional_note(
            psychologue=self.psych, patient=self.patient, content='Doc pro.'
        )
        self.assertEqual(note.note_type, ConsultationNote.NoteType.PROFESSIONAL)
        # Patient note refused.
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            notes_service.create_patient_note(
                psychologue=self.psych, patient=self.patient, content='Note patient.'
            )

    def test_no_show_only_allows_professional_note(self):
        Consultation.objects.filter(pk=self.consultation.pk).update(
            status=Consultation.Status.NO_SHOW
        )
        notes_service.create_professional_note(
            psychologue=self.psych, patient=self.patient, content='No-show doc.'
        )
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            notes_service.create_patient_note(
                psychologue=self.psych, patient=self.patient, content='Note patient.'
            )

    # --- Replacement (rattrapage) sessions -----------------------------
    def test_replacement_note_visible_to_psychologue_and_badged(self):
        replacement = Consultation.objects.create(
            patient=self.patient,
            psychologue=self.psych,
            date=timezone.localdate(),
            start_time=time(15),
            end_time=time(16),
            price=0,
            is_replacement=True,
            replaced_consultation=self.consultation,
        )
        note = notes_service.create_patient_note(
            psychologue=self.psych,
            patient=self.patient,
            content='Note de rattrapage.',
            consultation_id=replacement.pk,
        )
        # The service query already includes notes linked to a replacement.
        self.assertIn(
            note, notes_service.notes_for_psychologue(self.psych, self.patient)
        )
        # The notes page lists it and renders the replacement badge.
        self.client.force_login(self.psych)
        resp = self.client.get(
            reverse('accounts:psychologue_notes'),
            {'patient': self.patient.pk},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(note, list(resp.context['notes']))
        self.assertContains(resp, 'Séance de rattrapage')

    def test_patient_note_allowed_for_cancelled_replacement_only(self):
        # No active encounter remains: the original is cancelled and the only
        # other consultation is a cancelled replacement session.
        Consultation.objects.filter(pk=self.consultation.pk).update(
            status=Consultation.Status.CANCELLED
        )
        Consultation.objects.create(
            patient=self.patient,
            psychologue=self.psych,
            date=timezone.localdate(),
            start_time=time(15),
            end_time=time(16),
            price=0,
            is_replacement=True,
            status=Consultation.Status.CANCELLED,
        )
        note = notes_service.create_patient_note(
            psychologue=self.psych,
            patient=self.patient,
            content='Note sur rattrapage annulé.',
        )
        self.assertEqual(note.note_type, ConsultationNote.NoteType.PATIENT)

    # --- Point 5: secure retraction ------------------------------------
    def test_author_can_retract_and_history_is_kept(self):
        note = notes_service.create_patient_note(
            psychologue=self.psych, patient=self.patient, content='Note à rétracter.'
        )
        updated, error = notes_service.retract_note(
            note.pk, self.psych, reason='Envoyée au mauvais patient.'
        )
        self.assertIsNone(error)
        note.refresh_from_db()
        self.assertIsNotNone(note.retracted_at)
        self.assertEqual(note.retraction_reason, 'Envoyée au mauvais patient.')
        # History kept: row still exists, notification still exists (updated).
        self.assertTrue(ConsultationNote.objects.filter(pk=note.pk).exists())
        self.assertTrue(Notification.objects.filter(user=self.patient).exists())
        # Content hidden from the patient.
        self.assertIsNone(notes_service.get_patient_note(note.pk, self.patient))
        self.client.force_login(self.patient)
        resp = self.client.get(
            reverse('accounts:patient_note_detail', args=[note.pk])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn('Note à rétracter.', resp.content.decode())

    def test_retraction_refused_for_non_author(self):
        note = notes_service.create_patient_note(
            psychologue=self.psych, patient=self.patient, content='Note.'
        )
        from django.core.exceptions import PermissionDenied

        with self.assertRaises(PermissionDenied):
            notes_service.retract_note(note.pk, self.other_psych)
        note.refresh_from_db()
        self.assertIsNone(note.retracted_at)

    def test_retraction_view_refuses_non_author(self):
        note = notes_service.create_patient_note(
            psychologue=self.psych, patient=self.patient, content='Note.'
        )
        self.client.force_login(self.other_psych)
        resp = self.client.post(
            reverse('accounts:retract_consultation_note', args=[note.pk])
        )
        self.assertEqual(resp.status_code, 404)
        note.refresh_from_db()
        self.assertIsNone(note.retracted_at)

    def test_patient_cannot_retract(self):
        note = notes_service.create_patient_note(
            psychologue=self.psych, patient=self.patient, content='Note.'
        )
        self.client.force_login(self.patient)
        resp = self.client.post(
            reverse('accounts:retract_consultation_note', args=[note.pk])
        )
        self.assertEqual(resp.status_code, 403)
        note.refresh_from_db()
        self.assertIsNone(note.retracted_at)

    def test_double_retraction_rejected(self):
        note = notes_service.create_patient_note(
            psychologue=self.psych, patient=self.patient, content='Note.'
        )
        notes_service.retract_note(note.pk, self.psych, reason='first')
        _, error = notes_service.retract_note(note.pk, self.psych, reason='again')
        self.assertIsNotNone(error)

    def test_notes_page_renders_retracted_history(self):
        note = notes_service.create_patient_note(
            psychologue=self.psych, patient=self.patient, content='Note.'
        )
        notes_service.retract_note(note.pk, self.psych, reason='Erreur de patient.')
        self.client.force_login(self.psych)
        resp = self.client.get(
            reverse('accounts:psychologue_notes'), {'patient': self.patient.pk}
        )
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('rétractée', html)
        self.assertIn('Erreur de patient.', html)