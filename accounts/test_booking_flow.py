from datetime import time, timedelta
import re

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Call, Conversation, CustomUser, Notification, PsychologueProfile
from consultations.models import (
    Consultation,
    Creneau,
    Document,
    PaymentRecord,
    WeeklyAvailabilityRule,
)


class PatientBookingFlowTests(TestCase):
    def setUp(self):
        self.patient = CustomUser.objects.create_user(
            username='patient-booking',
            password='test-password',
            user_type='patient',
        )
        self.psychologue = CustomUser.objects.create_user(
            username='psychologue-booking',
            password='test-password',
            user_type='psychologue',
            is_active=True,
        )
        PsychologueProfile.objects.create(
            user=self.psychologue,
            is_verified=True,
            hourly_rate='3200.00',
            session_duration=45,
        )
        self.slot = Creneau.objects.create(
            psychologue=self.psychologue,
            date=timezone.localdate() + timedelta(days=2),
            heure_debut='10:00',
            heure_fin='11:00',
            statut=Creneau.Statut.LIBRE,
        )
        WeeklyAvailabilityRule.objects.create(
            psychologue=self.psychologue,
            weekday=self.slot.date.weekday(),
            start_time=time(9),
            end_time=time(12),
        )
        self.client.force_login(self.patient)
        self.booking_url = reverse(
            'accounts:book_consultation',
            args=[self.psychologue.pk],
        )

    def test_search_page_links_to_booking_and_booking_page_renders(self):
        search_response = self.client.get(reverse('accounts:trouver_psychologue'))
        booking_response = self.client.get(self.booking_url)

        self.assertEqual(search_response.status_code, 200)
        self.assertContains(
            search_response,
            reverse('accounts:book_consultation', args=[self.psychologue.pk]),
        )
        self.assertEqual(booking_response.status_code, 200)
        self.assertTemplateUsed(booking_response, 'patient/book_consultation.html')

    def test_availability_endpoint_returns_real_free_slot(self):
        url = reverse(
            'consultations:get_available_slots',
            kwargs={
                'psychologue_id': self.psychologue.pk,
                'date_str': self.slot.date.isoformat(),
            },
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()['slots'],
            [{
                'id': self.slot.pk,
                'heure_debut': '10:00',
                'heure_fin': '11:00',
            }],
        )

    def test_availability_endpoint_hides_past_slots(self):
        past_datetime = timezone.localtime(timezone.now() - timedelta(hours=2))
        past_slot = Creneau.objects.create(
            psychologue=self.psychologue,
            date=past_datetime.date(),
            heure_debut=past_datetime.time().replace(second=0, microsecond=0),
            heure_fin=(past_datetime + timedelta(minutes=45)).time().replace(
                second=0,
                microsecond=0,
            ),
            statut=Creneau.Statut.LIBRE,
        )
        url = reverse(
            'consultations:get_available_slots',
            kwargs={
                'psychologue_id': self.psychologue.pk,
                'date_str': past_slot.date.isoformat(),
            },
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['slots'], [])

    def test_booking_creates_consultation_and_reserves_selected_slot(self):
        response = self.client.post(
            self.booking_url,
            {
                'creneau_id': self.slot.pk,
                'consultation_type': Consultation.SessionType.VIDEO,
                'notes': 'Initial appointment',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('accounts:patient_dashboard'))
        consultation = Consultation.objects.get(patient=self.patient)
        self.slot.refresh_from_db()
        self.assertEqual(consultation.creneau, self.slot)
        self.assertEqual(consultation.psychologue, self.psychologue)
        self.assertEqual(consultation.date, self.slot.date)
        self.assertEqual(consultation.start_time, self.slot.heure_debut)
        self.assertEqual(consultation.end_time, self.slot.heure_fin)
        self.assertEqual(consultation.duration_minutes, 60)
        self.assertEqual(str(consultation.price), '3200.00')
        self.assertEqual(consultation.status, Consultation.Status.PENDING)
        self.assertTrue(
            Notification.objects.filter(
                user=self.psychologue,
                message='Nouvelle demande de consultation.',
            ).exists()
        )
        self.slot.refresh_from_db()
        self.assertEqual(self.slot.statut, Creneau.Statut.RESERVE)

    def test_rejection_notifies_the_patient(self):
        consultation = self.create_consultation(Consultation.Status.PENDING)
        self.client.force_login(self.psychologue)

        response = self.client.post(
            reverse('accounts:reject_appointment', args=[consultation.id]),
        )

        self.assertRedirects(response, reverse('accounts:rendez_vous'))
        consultation.refresh_from_db()
        self.assertEqual(consultation.status, Consultation.Status.CANCELLED)
        self.assertTrue(
            Notification.objects.filter(
                user=self.patient,
                message='Votre demande de consultation a été refusée.',
            ).exists()
        )

    def create_consultation(self, status, payment_status=Consultation.PaymentStatus.UNPAID):
        return Consultation.objects.create(
            patient=self.patient,
            psychologue=self.psychologue,
            date=self.slot.date,
            start_time=time(10, 0),
            end_time=time(11, 0),
            duration_minutes=60,
            session_type=Consultation.SessionType.VIDEO,
            price='3200.00',
            status=status,
            payment_status=payment_status,
        )

    def build_test_card_data(self, method='CIB', card_number='1111111111111111'):
        expiry = timezone.localdate().replace(day=1)
        if expiry.month == 12:
            expiry = expiry.replace(year=expiry.year + 1, month=1)
        else:
            expiry = expiry.replace(month=expiry.month + 1)
        return {
            'payment_method': method,
            'cardholder_name': 'TEST USER',
            'test_card_number': card_number,
            'expiry_month': f'{expiry.month:02d}',
            'expiry_year': f'{expiry.year:04d}',
            'cvv': '123',
        }

    def mark_consultation_paid(self, consultation):
        consultation.payment_status = Consultation.PaymentStatus.PAID
        consultation.payment_date = timezone.now()
        consultation.save(update_fields=['payment_status', 'payment_date'])
        return PaymentRecord.objects.create(
            consultation=consultation,
            amount=consultation.price,
            method='CIB',
            transaction_ref=f'SIM-TEST-{consultation.pk.hex[:8]}',
            status='success',
        )

    def test_dashboard_offers_payment_only_for_confirmed_unpaid_consultations(self):
        payable = self.create_consultation(Consultation.Status.CONFIRMED)
        self.create_consultation(Consultation.Status.PENDING)
        self.create_consultation(
            Consultation.Status.CONFIRMED,
            Consultation.PaymentStatus.PAID,
        )

        response = self.client.get(reverse('accounts:patient_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{reverse("home")}" class="sidebar-logo"')
        self.assertContains(response, 'Accueil de la plateforme')
        self.assertContains(
            response,
            reverse('accounts:payment_page', args=[payable.id]),
        )
        self.assertEqual(response.content.decode().count('Payer'), 1)

    def test_patient_dashboard_completes_expired_sessions_and_orders_history(self):
        expired = self.create_consultation(Consultation.Status.CONFIRMED)
        expired.date = timezone.localdate() - timedelta(days=1)
        expired.save()

        first_upcoming = self.create_consultation(Consultation.Status.PENDING)
        first_upcoming.date = timezone.localdate() + timedelta(days=2)
        first_upcoming.start_time = time(9)
        first_upcoming.save()
        second_upcoming = self.create_consultation(Consultation.Status.PENDING)
        second_upcoming.date = timezone.localdate() + timedelta(days=2)
        second_upcoming.start_time = time(12)
        second_upcoming.save()

        response = self.client.get(reverse('accounts:patient_dashboard'))

        self.assertEqual(response.status_code, 200)
        expired.refresh_from_db()
        self.assertEqual(expired.status, Consultation.Status.COMPLETED)
        self.assertEqual(
            [item.pk for item in response.context['upcoming_sessions']],
            [first_upcoming.pk, second_upcoming.pk],
        )
        self.assertEqual(response.context['completed_sessions'][0].pk, expired.pk)
        self.assertContains(response, 'past-appointment')

    def test_psychologist_can_emergency_cancel_future_session_and_notify_patient(self):
        consultation = self.create_consultation(Consultation.Status.PENDING)
        future = timezone.localtime(timezone.now() + timedelta(days=2))
        consultation.date = future.date()
        consultation.start_time = time(10)
        consultation.duration_minutes = 60
        consultation.save()
        creneau = self.slot
        creneau.statut = Creneau.Statut.RESERVE
        creneau.save(update_fields=['statut'], skip_overlap_validation=True)
        consultation.creneau = creneau
        consultation.save(update_fields=['creneau'])
        self.client.force_login(self.psychologue)

        response = self.client.post(
            reverse(
                'accounts:emergency_cancel_appointment',
                args=[consultation.pk],
            )
        )

        self.assertRedirects(response, reverse('accounts:psychologue_dashboard'))
        consultation.refresh_from_db()
        creneau.refresh_from_db()
        self.assertEqual(consultation.status, Consultation.Status.CANCELLED)
        self.assertEqual(creneau.statut, Creneau.Statut.LIBRE)
        self.assertTrue(
            Notification.objects.filter(
                user=self.patient,
                message='تم إلغاء موعدك من طرف الأخصائي. سيتم التواصل معك لتحديد موعد بديل.',
            ).exists()
        )

    def test_psychologist_dashboard_loads_real_time_notifications(self):
        self.client.force_login(self.psychologue)

        response = self.client.get(reverse('accounts:psychologue_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "js/realtime-notifications.js")
        self.assertContains(response, 'data-user-type="psychologue"')

    def test_patient_can_cancel_before_start_even_within_24_hours(self):
        consultation = self.create_consultation(Consultation.Status.CONFIRMED)
        session_start = timezone.localtime(timezone.now() + timedelta(hours=2))
        consultation.date = session_start.date()
        consultation.start_time = session_start.time().replace(second=0, microsecond=0)
        consultation.save()
        payment = self.mark_consultation_paid(consultation)
        cancel_url = reverse('accounts:cancel_appointment', args=[consultation.id])

        dashboard_response = self.client.get(reverse('accounts:patient_dashboard'))
        appointments_response = self.client.get(reverse('accounts:rendez_vous'))

        self.assertContains(dashboard_response, cancel_url)
        self.assertContains(appointments_response, cancel_url)
        self.assertNotContains(
            dashboard_response,
            reverse('accounts:payment_page', args=[consultation.id]),
        )

        response = self.client.post(cancel_url)

        self.assertRedirects(response, reverse('accounts:rendez_vous'))
        consultation.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(consultation.status, Consultation.Status.CANCELLED)
        self.assertEqual(consultation.payment_status, Consultation.PaymentStatus.PAID)
        self.assertEqual(payment.status, 'success')

    def test_patient_cannot_cancel_after_start_or_when_consultation_is_in_progress(self):
        consultation = self.create_consultation(Consultation.Status.CONFIRMED)
        session_start = timezone.localtime(timezone.now() - timedelta(minutes=1))
        consultation.date = session_start.date()
        consultation.start_time = session_start.time().replace(second=0, microsecond=0)
        consultation.save()
        cancel_url = reverse('accounts:cancel_appointment', args=[consultation.id])

        self.client.post(cancel_url)

        consultation.refresh_from_db()
        self.assertEqual(consultation.status, Consultation.Status.CONFIRMED)

        consultation.status = Consultation.Status.IN_PROGRESS
        consultation.date = self.slot.date
        consultation.start_time = time(10)
        consultation.save()
        self.client.post(cancel_url)

        consultation.refresh_from_db()
        self.assertEqual(consultation.status, Consultation.Status.IN_PROGRESS)

    def test_administrator_cannot_confirm_patient_appointment(self):
        consultation = self.create_consultation(Consultation.Status.PENDING)
        administrator = CustomUser.objects.create_user(
            username='appointment-admin',
            password='test-password',
            user_type='admin',
            is_staff=True,
        )
        self.client.force_login(administrator)

        response = self.client.post(
            reverse('accounts:confirm_appointment', args=[consultation.id]),
        )

        self.assertEqual(response.status_code, 404)
        consultation.refresh_from_db()
        self.assertEqual(consultation.status, Consultation.Status.PENDING)

    def test_patient_login_redirects_to_patient_dashboard(self):
        self.client.logout()

        response = self.client.post(
            reverse('accounts:login'),
            {'email': self.patient.username, 'password': 'test-password'},
        )

        self.assertRedirects(response, reverse('accounts:patient_dashboard'))

    def test_psychologist_login_redirects_to_psychologist_dashboard(self):
        self.client.logout()

        response = self.client.post(
            reverse('accounts:login'),
            {'email': self.psychologue.username, 'password': 'test-password'},
        )

        self.assertRedirects(response, reverse('accounts:psychologue_dashboard'))

    def test_admin_login_redirects_to_admin_panel(self):
        self.client.logout()
        administrator = CustomUser.objects.create_user(
            username='admin-login-test',
            password='test-password',
            user_type='admin',
            is_staff=True,
            is_superuser=True,
        )

        response = self.client.post(
            reverse('accounts:login'),
            {'email': administrator.username, 'password': 'test-password'},
        )

        self.assertRedirects(response, reverse('dashboard'))

    def test_login_preserves_safe_next_and_rejects_external_next(self):
        self.client.logout()
        dashboard_url = reverse('accounts:patient_dashboard')
        login_page = self.client.get(
            f"{reverse('accounts:login')}?next={dashboard_url}"
        )
        self.assertContains(
            login_page,
            f'name="next" value="{dashboard_url}"',
        )

        safe_response = self.client.post(
            reverse('accounts:login'),
            {
                'email': self.patient.username,
                'password': 'test-password',
                'next': dashboard_url,
            },
        )
        self.assertRedirects(safe_response, dashboard_url)

        self.client.logout()
        unsafe_response = self.client.post(
            reverse('accounts:login'),
            {
                'email': self.patient.username,
                'password': 'test-password',
                'next': 'https://attacker.example/redirect',
            },
        )
        self.assertRedirects(unsafe_response, dashboard_url)

    def test_home_displays_authenticated_username_as_rendered_text(self):
        self.patient.first_name = 'SyntheticPatient'
        self.patient.save(update_fields=['first_name'])
        self.client.force_login(self.patient)

        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'SyntheticPatient')
        self.assertNotContains(response, '{{ user.first_name')

    def test_patient_registration_redirects_to_platform_home(self):
        self.client.logout()

        response = self.client.post(
            reverse('accounts:register_patient'),
            {
                'first_name': 'Salima',
                'last_name': 'Test',
                'email': 'salima.test@example.invalid',
                'phone': '0550000000',
                'password': 'synthetic-test-password',
                'password_confirm': 'synthetic-test-password',
            },
        )

        self.assertRedirects(response, reverse('home'))

    def test_payment_flow_records_one_transaction_and_confirms_success_page(self):
        consultation = self.create_consultation(Consultation.Status.CONFIRMED)
        payment_page = self.client.get(
            reverse('accounts:payment_page', args=[consultation.id])
        )

        self.assertEqual(payment_page.status_code, 200)
        self.assertTemplateUsed(payment_page, 'accounts/payment.html')
        self.assertContains(payment_page, 'csrfmiddlewaretoken')
        self.assertContains(
            payment_page,
            f'action="{reverse("accounts:process_payment", args=[consultation.id])}"',
        )
        self.assertContains(payment_page, 'name="payment_method"')
        self.assertContains(payment_page, 'name="card_number"')
        self.assertContains(payment_page, 'name="expiry"')
        self.assertContains(payment_page, '1111 1111 1111 1112')
        self.assertContains(payment_page, '2222 2222 2222 2223')
        self.assertContains(payment_page, '3200,00 DZD')

        response = self.client.post(
            reverse('accounts:process_payment', args=[consultation.id]),
            self.build_test_card_data(),
        )

        self.assertRedirects(
            response,
            reverse('accounts:payment_success', args=[consultation.id]),
        )
        consultation.refresh_from_db()
        payment = PaymentRecord.objects.get(consultation=consultation)
        self.assertEqual(consultation.payment_status, Consultation.PaymentStatus.PAID)
        self.assertIsNotNone(consultation.payment_date)
        self.assertEqual(payment.amount, consultation.price)
        self.assertEqual(payment.method, 'CIB')
        self.assertEqual(payment.status, 'success')
        self.assertTrue(payment.transaction_ref.startswith('SIM-'))

        success_page = self.client.get(response['Location'])
        self.assertEqual(success_page.status_code, 200)
        self.assertTemplateUsed(success_page, 'accounts/payment_success.html')
        self.assertContains(success_page, payment.transaction_ref)

        repeat_response = self.client.post(
            reverse('accounts:process_payment', args=[consultation.id]),
            self.build_test_card_data(),
        )
        self.assertRedirects(
            repeat_response,
            reverse('accounts:patient_dashboard'),
        )
        self.assertEqual(PaymentRecord.objects.filter(consultation=consultation).count(), 1)

    def test_failed_simulated_payment_stays_unpaid_and_can_be_retried(self):
        consultation = self.create_consultation(Consultation.Status.CONFIRMED)
        failed_response = self.client.post(
            reverse('accounts:process_payment', args=[consultation.id]),
            self.build_test_card_data(card_number='1111111111111112'),
        )

        self.assertRedirects(
            failed_response,
            reverse('accounts:payment_page', args=[consultation.id]),
        )
        consultation.refresh_from_db()
        payment = PaymentRecord.objects.get(consultation=consultation)
        self.assertEqual(consultation.payment_status, Consultation.PaymentStatus.UNPAID)
        self.assertIsNone(consultation.payment_date)
        self.assertEqual(payment.status, 'failed')
        self.assertContains(
            self.client.get(failed_response['Location']),
            'échec simulé',
        )

        retry_response = self.client.post(
            reverse('accounts:process_payment', args=[consultation.id]),
            self.build_test_card_data(method='EDAHABIA', card_number='2222222222222222'),
        )

        self.assertRedirects(
            retry_response,
            reverse('accounts:payment_success', args=[consultation.id]),
        )
        consultation.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(consultation.payment_status, Consultation.PaymentStatus.PAID)
        self.assertEqual(payment.status, 'success')
        self.assertEqual(payment.method, 'EDAHABIA')
        self.assertEqual(PaymentRecord.objects.filter(consultation=consultation).count(), 1)

    def test_payment_accepts_requested_synthetic_card_and_never_saves_card_data(self):
        consultation = self.create_consultation(Consultation.Status.CONFIRMED)
        payment_data = {
            'payment_method': 'CIB',
            'cardholder_name': 'MERIME MARIAA',
            'card_number': '6280123456789010',
            'expiry': '12/28',
            'cvv': '123',
        }
        response = self.client.post(
            reverse('accounts:process_payment', args=[consultation.id]),
            payment_data,
        )

        self.assertRedirects(
            response,
            reverse('accounts:payment_success', args=[consultation.id]),
        )
        consultation.refresh_from_db()
        payment = PaymentRecord.objects.get(consultation=consultation)
        self.assertEqual(consultation.payment_status, Consultation.PaymentStatus.PAID)
        self.assertIsNotNone(consultation.payment_date)
        self.assertEqual(payment.status, 'success')
        for sensitive_value in payment_data.values():
            if sensitive_value != payment_data['payment_method']:
                self.assertNotIn(sensitive_value, str(payment.__dict__))

    def test_payment_form_submits_with_csrf_checks_enabled(self):
        consultation = self.create_consultation(Consultation.Status.CONFIRMED)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.patient)

        page = csrf_client.get(
            reverse('accounts:payment_page', args=[consultation.id])
        )
        self.assertEqual(page.status_code, 200)
        self.assertIn('no-store', page['Cache-Control'])
        token_match = re.search(
            r'name="csrfmiddlewaretoken" value="([^"]+)"',
            page.content.decode(),
        )
        self.assertIsNotNone(token_match)

        response = csrf_client.post(
            reverse('accounts:process_payment', args=[consultation.id]),
            {
                **self.build_test_card_data(),
                'csrfmiddlewaretoken': token_match.group(1),
            },
        )

        self.assertRedirects(
            response,
            reverse('accounts:payment_success', args=[consultation.id]),
        )

    def test_payment_validation_errors_are_displayed_on_the_payment_page(self):
        consultation = self.create_consultation(Consultation.Status.CONFIRMED)
        payment_data = self.build_test_card_data()
        payment_data.pop('cvv')

        response = self.client.post(
            reverse('accounts:process_payment', args=[consultation.id]),
            payment_data,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response['Location'],
            reverse('accounts:payment_page', args=[consultation.id]),
        )
        payment_page = self.client.get(response['Location'])
        self.assertContains(payment_page, 'Vérifiez les informations de test')

    def test_payment_rejects_another_patients_consultation(self):
        consultation = self.create_consultation(Consultation.Status.CONFIRMED)
        other_patient = CustomUser.objects.create_user(
            username='other-payment-patient',
            password='test-password',
            user_type='patient',
        )
        self.client.force_login(other_patient)

        response = self.client.post(
            reverse('accounts:process_payment', args=[consultation.id]),
            self.build_test_card_data(),
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(PaymentRecord.objects.exists())
        consultation.refresh_from_db()
        self.assertEqual(consultation.payment_status, Consultation.PaymentStatus.UNPAID)

    def test_psychologist_cannot_pay_a_consultation(self):
        consultation = self.create_consultation(Consultation.Status.CONFIRMED)
        self.client.force_login(self.psychologue)

        response = self.client.post(
            reverse('accounts:process_payment', args=[consultation.id]),
            self.build_test_card_data(),
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(PaymentRecord.objects.exists())
        consultation.refresh_from_db()
        self.assertEqual(consultation.payment_status, Consultation.PaymentStatus.UNPAID)

    def test_payment_rejects_unconfirmed_already_paid_and_invalid_methods(self):
        pending = self.create_consultation(Consultation.Status.PENDING)
        unpaid_url = reverse('accounts:payment_page', args=[pending.id])
        self.assertRedirects(
            self.client.get(unpaid_url),
            reverse('accounts:patient_dashboard'),
        )
        self.assertRedirects(
            self.client.post(
                reverse('accounts:process_payment', args=[pending.id]),
                {'payment_method': 'CIB'},
            ),
            reverse('accounts:patient_dashboard'),
        )
        self.assertFalse(PaymentRecord.objects.exists())

        confirmed = self.create_consultation(Consultation.Status.CONFIRMED)
        payment_url = reverse('accounts:payment_page', args=[confirmed.id])
        self.assertRedirects(
            self.client.post(
                reverse('accounts:process_payment', args=[confirmed.id]),
                {'payment_method': 'INVALID'},
            ),
            payment_url,
        )
        confirmed.payment_status = Consultation.PaymentStatus.PAID
        confirmed.save(update_fields=['payment_status'])
        self.assertRedirects(
            self.client.get(payment_url),
            reverse('accounts:patient_dashboard'),
        )
        self.assertFalse(PaymentRecord.objects.exists())

    def test_patient_cannot_open_psychologue_only_dashboard(self):
        response = self.client.get(reverse('accounts:psychologue_dashboard'))

        self.assertRedirects(response, reverse('home'))

    def test_psychologue_cannot_open_patient_only_booking_pages(self):
        self.client.force_login(self.psychologue)

        self.assertRedirects(
            self.client.get(reverse('accounts:trouver_psychologue')),
            reverse('home'),
        )
        self.assertRedirects(
            self.client.get(
                reverse('accounts:book_consultation', args=[self.psychologue.id])
            ),
            reverse('home'),
        )

    def test_booking_rejects_slot_that_is_no_longer_free(self):
        self.slot.statut = Creneau.Statut.RESERVE
        self.slot.save(update_fields=['statut'])

        response = self.client.post(
            self.booking_url,
            {'creneau_id': self.slot.pk},
        )

        self.assertRedirects(response, self.booking_url)
        self.assertFalse(Consultation.objects.exists())

    def test_second_booking_attempt_cannot_claim_the_same_slot(self):
        booking_data = {
            'creneau_id': self.slot.pk,
            'consultation_type': Consultation.SessionType.VIDEO,
        }

        first_response = self.client.post(self.booking_url, booking_data)
        second_response = self.client.post(self.booking_url, booking_data)

        self.assertEqual(first_response.status_code, 302)
        self.assertRedirects(second_response, self.booking_url)
        self.assertEqual(Consultation.objects.filter(creneau=self.slot).count(), 1)
        self.slot.refresh_from_db()
        self.assertEqual(self.slot.statut, Creneau.Statut.RESERVE)

    def test_booking_rejects_slot_belonging_to_another_psychologue(self):
        other_psychologue = CustomUser.objects.create_user(
            username='other-psychologue',
            password='test-password',
            user_type='psychologue',
            is_active=True,
        )
        PsychologueProfile.objects.create(user=other_psychologue, is_verified=True)
        other_slot = Creneau.objects.create(
            psychologue=other_psychologue,
            date=self.slot.date,
            heure_debut='12:00',
            heure_fin='13:00',
            statut=Creneau.Statut.LIBRE,
        )

        response = self.client.post(
            self.booking_url,
            {'creneau_id': other_slot.pk},
        )

        self.assertRedirects(response, self.booking_url)
        self.assertFalse(Consultation.objects.exists())
        other_slot.refresh_from_db()
        self.assertEqual(other_slot.statut, Creneau.Statut.LIBRE)

    def test_booking_rejects_past_slot(self):
        past_datetime = timezone.localtime(timezone.now() - timedelta(hours=2))
        past_slot = Creneau.objects.create(
            psychologue=self.psychologue,
            date=past_datetime.date(),
            heure_debut=past_datetime.time().replace(second=0, microsecond=0),
            heure_fin=(past_datetime + timedelta(minutes=45)).time().replace(
                second=0,
                microsecond=0,
            ),
            statut=Creneau.Statut.LIBRE,
        )

        response = self.client.post(
            self.booking_url,
            {'creneau_id': past_slot.pk},
        )

        self.assertRedirects(response, self.booking_url)
        self.assertFalse(Consultation.objects.exists())

    def test_booking_rejects_invalid_or_missing_slot_id(self):
        for creneau_id in ('not-an-id', ''):
            with self.subTest(creneau_id=creneau_id):
                response = self.client.post(
                    self.booking_url,
                    {'creneau_id': creneau_id},
                )

                self.assertRedirects(response, self.booking_url)
                self.assertFalse(Consultation.objects.exists())

    def test_root_patient_dashboard_delegates_to_account_dashboard(self):
        response = self.client.get(reverse('patient_dashboard'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('accounts:patient_dashboard'))

    def test_consultation_chat_template_renders_with_csrf(self):
        consultation = self.create_consultation(Consultation.Status.CONFIRMED)
        self.mark_consultation_paid(consultation)

        response = self.client.get(
            reverse('consultations:consultation_chat', args=[consultation.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'consultations/chat_room.html')
        self.assertContains(response, 'csrfmiddlewaretoken')

    def test_consultation_room_requires_payment_and_active_appointment(self):
        consultation = self.create_consultation(Consultation.Status.CONFIRMED)
        room_url = reverse('consultations:consultation_chat', args=[consultation.id])

        self.assertEqual(self.client.get(room_url).status_code, 403)

        self.mark_consultation_paid(consultation)
        consultation.status = Consultation.Status.CANCELLED
        consultation.save(update_fields=['status'])
        self.assertEqual(self.client.get(room_url).status_code, 403)

    def test_only_patient_and_assigned_psychologist_can_open_paid_consultation_room(self):
        consultation = self.create_consultation(Consultation.Status.CONFIRMED)
        self.mark_consultation_paid(consultation)
        room_url = reverse('consultations:consultation_chat', args=[consultation.id])

        self.assertEqual(self.client.get(room_url).status_code, 200)

        self.client.force_login(self.psychologue)
        self.assertEqual(self.client.get(room_url).status_code, 200)

        another_patient = CustomUser.objects.create_user(
            username='unauthorized-room-patient',
            password='test-password',
            user_type='patient',
        )
        self.client.force_login(another_patient)
        self.assertEqual(self.client.get(room_url).status_code, 404)

        another_psychologue = CustomUser.objects.create_user(
            username='unauthorized-room-psychologue',
            password='test-password',
            user_type='psychologue',
        )
        self.client.force_login(another_psychologue)
        self.assertEqual(self.client.get(room_url).status_code, 404)

    def test_payment_status_and_room_link_are_visible_on_appointment_list(self):
        consultation = self.create_consultation(Consultation.Status.CONFIRMED)
        room_url = reverse('consultations:consultation_chat', args=[consultation.id])

        unpaid_response = self.client.get(reverse('accounts:rendez_vous'))
        self.assertContains(unpaid_response, 'Paiement : Non payé')
        self.assertContains(unpaid_response, reverse('accounts:payment_page', args=[consultation.id]))
        self.assertNotContains(unpaid_response, room_url)

        self.mark_consultation_paid(consultation)
        paid_response = self.client.get(reverse('accounts:rendez_vous'))
        self.assertContains(paid_response, 'Paiement : Payé')
        self.assertContains(paid_response, room_url)

    def test_psychologue_availability_and_document_pages_render(self):
        self.client.force_login(self.psychologue)

        availability_response = self.client.get(
            reverse('consultations:manage_availability')
        )
        documents_response = self.client.get(
            reverse('consultations:upload_document')
        )

        self.assertEqual(availability_response.status_code, 200)
        self.assertTemplateUsed(
            availability_response,
            'consultations/manage_availability.html',
        )
        self.assertContains(availability_response, 'csrfmiddlewaretoken')
        self.assertEqual(documents_response.status_code, 200)
        self.assertTemplateUsed(
            documents_response,
            'consultations/upload_document.html',
        )
        self.assertContains(documents_response, 'csrfmiddlewaretoken')

    def test_unverified_psychologue_cannot_publish_availability_or_receive_booking(self):
        self.psychologue.psychologue_profile.is_verified = False
        self.psychologue.psychologue_profile.save(update_fields=['is_verified'])

        self.client.force_login(self.psychologue)
        availability_response = self.client.post(
            reverse('consultations:manage_availability'),
            {
                'date': (timezone.localdate() + timedelta(days=3)).isoformat(),
                'heure_debut': '12:00',
                'heure_fin': '13:00',
            },
        )
        self.assertRedirects(
            availability_response,
            reverse('consultations:upload_document'),
        )
        self.assertFalse(Creneau.objects.filter(heure_debut=time(12, 0)).exists())

        self.client.force_login(self.patient)
        booking_response = self.client.post(
            self.booking_url,
            {'creneau_id': self.slot.pk},
        )
        self.assertRedirects(
            booking_response,
            reverse('accounts:trouver_psychologue'),
        )
        self.assertFalse(Consultation.objects.exists())

        slots_response = self.client.get(
            reverse(
                'consultations:get_available_slots',
                kwargs={
                    'psychologue_id': self.psychologue.pk,
                    'date_str': self.slot.date.isoformat(),
                },
            )
        )
        self.assertEqual(slots_response.json()['slots'], [])

    def test_psychologist_registration_stays_unverified_and_document_page_remains_available(self):
        self.client.logout()
        response = self.client.post(
            reverse('accounts:register_psychologue'),
            {
                'first_name': 'Nadia',
                'last_name': 'Test',
                'email': 'nadia.test@example.invalid',
                'phone': '0550000000',
                'password': 'synthetic-test-password',
                'password_confirm': 'synthetic-test-password',
                'specialites': 'clinique',
                'experience': '2',
                'license_number': 'SYNTHETIC-LICENSE',
                'city': 'Alger',
            },
        )

        self.assertRedirects(
            response,
            reverse('accounts:psychologue_dashboard'),
        )
        user = CustomUser.objects.get(email='nadia.test@example.invalid')
        self.assertTrue(user.is_active)
        self.assertFalse(user.psychologue_profile.is_verified)
        self.assertEqual(user.psychologue_profile.registration_number, 'SYNTHETIC-LICENSE')
        self.assertEqual(user.psychologue_profile.city, 'Alger')
        self.assertEqual(user.city, 'Alger')
        self.assertEqual(
            self.client.get(reverse('consultations:upload_document')).status_code,
            200,
        )

    def test_unverified_psychologist_cannot_confirm_an_existing_request(self):
        consultation = self.create_consultation(Consultation.Status.PENDING)
        self.psychologue.psychologue_profile.is_verified = False
        self.psychologue.psychologue_profile.save(update_fields=['is_verified'])
        self.client.force_login(self.psychologue)

        response = self.client.post(
            reverse('accounts:confirm_appointment', args=[consultation.id]),
        )

        self.assertRedirects(response, reverse('accounts:rendez_vous'))
        consultation.refresh_from_db()
        self.assertEqual(consultation.status, Consultation.Status.PENDING)

    def test_verified_psychologist_can_confirm_request_and_notify_patient(self):
        consultation = self.create_consultation(Consultation.Status.PENDING)
        self.client.force_login(self.psychologue)

        response = self.client.post(
            reverse('accounts:confirm_appointment', args=[consultation.id]),
        )

        self.assertRedirects(response, reverse('accounts:rendez_vous'))
        consultation.refresh_from_db()
        self.assertEqual(consultation.status, Consultation.Status.CONFIRMED)
        self.assertTrue(
            Notification.objects.filter(
                user=self.patient,
                message='Votre demande de consultation a été acceptée.',
            ).exists()
        )

    def test_document_approval_and_rejection_update_profile_verification(self):
        admin_user = CustomUser.objects.create_user(
            username='verification-admin',
            password='test-password',
            user_type='admin',
            is_staff=True,
            is_superuser=True,
        )
        self.psychologue.psychologue_profile.is_verified = False
        self.psychologue.psychologue_profile.save(update_fields=['is_verified'])
        document = Document.objects.create(
            psychologue=self.psychologue,
            type_document=Document.TypeDocument.DIPLOME,
            fichier='synthetic-diploma.pdf',
        )

        document.valider(admin_user)
        self.psychologue.psychologue_profile.refresh_from_db()
        document.refresh_from_db()
        self.assertEqual(document.statut, Document.Statut.VALIDE)
        self.assertEqual(document.admin_validateur, admin_user)
        self.assertTrue(self.psychologue.psychologue_profile.is_verified)
        self.assertIsNotNone(self.psychologue.psychologue_profile.verification_date)

        document.rejeter(admin_user, 'Document requires correction.')
        self.psychologue.psychologue_profile.refresh_from_db()
        document.refresh_from_db()
        self.assertEqual(document.statut, Document.Statut.REJETE)
        self.assertFalse(self.psychologue.psychologue_profile.is_verified)
        self.assertIsNone(self.psychologue.psychologue_profile.verification_date)

    def test_document_admin_can_approve_and_reject_documents(self):
        admin_user = CustomUser.objects.create_user(
            username='document-admin',
            password='test-password',
            user_type='admin',
            is_staff=True,
            is_superuser=True,
        )
        self.psychologue.psychologue_profile.is_verified = False
        self.psychologue.psychologue_profile.save(update_fields=['is_verified'])
        document = Document.objects.create(
            psychologue=self.psychologue,
            type_document=Document.TypeDocument.DIPLOME,
            fichier='synthetic-diploma.pdf',
        )
        self.client.force_login(admin_user)
        admin_url = reverse('admin:consultations_document_changelist')

        approve_response = self.client.post(
            admin_url,
            {
                'action': 'approve_selected_documents',
                '_selected_action': [str(document.pk)],
            },
        )
        self.assertEqual(approve_response.status_code, 302)
        document.refresh_from_db()
        self.psychologue.psychologue_profile.refresh_from_db()
        self.assertEqual(document.statut, Document.Statut.VALIDE)
        self.assertEqual(document.admin_validateur, admin_user)
        self.assertTrue(self.psychologue.psychologue_profile.is_verified)

        reject_response = self.client.post(
            admin_url,
            {
                'action': 'reject_selected_documents',
                '_selected_action': [str(document.pk)],
            },
        )
        self.assertEqual(reject_response.status_code, 302)
        document.refresh_from_db()
        self.psychologue.psychologue_profile.refresh_from_db()
        self.assertEqual(document.statut, Document.Statut.REJETE)
        self.assertEqual(document.motif_rejet, 'Rejected by administrator.')
        self.assertFalse(self.psychologue.psychologue_profile.is_verified)

    def test_call_room_validates_type_and_does_not_mark_call_ongoing(self):
        self.client.force_login(self.psychologue)
        call_url = reverse('accounts:start_call', args=[self.patient.pk])

        response = self.client.get(call_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'call/room.html')
        call = Call.objects.get(patient=self.patient, psychologue=self.psychologue)
        self.assertEqual(call.status, 'scheduled')

        invalid_response = self.client.get(call_url, {'type': 'invalid'})
        self.assertEqual(invalid_response.status_code, 302)
        self.assertEqual(Call.objects.count(), 1)

    def test_patient_and_psychologue_share_the_same_messages_interface(self):
        conversation = Conversation.objects.create(
            patient=self.patient,
            psychologue=self.psychologue,
        )
        messages_url = reverse('accounts:messages_list')

        for user, role_label in (
            (self.patient, 'Espace patient'),
            (self.psychologue, 'Espace psychologue'),
        ):
            with self.subTest(user_type=user.user_type):
                self.client.force_login(user)
                dashboard_name = (
                    'accounts:patient_dashboard'
                    if user.user_type == 'patient'
                    else 'accounts:psychologue_dashboard'
                )
                dashboard_response = self.client.get(reverse(dashboard_name))
                self.assertEqual(dashboard_response.status_code, 200)
                self.assertContains(
                    dashboard_response,
                    f'href="{messages_url}"',
                )

                response = self.client.get(messages_url)

                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, 'accounts/messages_list.html')
                self.assertContains(response, role_label)
                self.assertContains(response, f'href="{messages_url}"')

        self.client.force_login(self.patient)
        chat_response = self.client.get(
            reverse('accounts:chat_room', args=[conversation.pk])
        )
        self.assertEqual(chat_response.status_code, 200)
        self.assertContains(chat_response, 'id="message-list"')
        self.assertContains(chat_response, 'id="msg-input"')
        self.assertContains(chat_response, 'socket.addEventListener("message"')
        self.assertNotContains(chat_response, 'JSON.parse(e.data)')

        self.assertEqual(self.client.get('/accounts/chat/list/').status_code, 404)
