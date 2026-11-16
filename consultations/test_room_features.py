from datetime import timedelta
from unittest.mock import patch

from asgiref.sync import async_to_sync
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser
from ai_service.models import SessionSummary
from consultations.models import Consultation, Message, PaymentRecord
from consultations.access import has_room_time_access
from consultations.routing import websocket_urlpatterns


class ConsultationRoomFeatureTests(TestCase):
    def setUp(self):
        self.patient = CustomUser.objects.create_user(
            username="room-feature-patient",
            password="test-password",
            user_type="patient",
        )
        self.psychologist = CustomUser.objects.create_user(
            username="room-feature-psychologist",
            password="test-password",
            user_type="psychologue",
        )
        current_start = timezone.localtime(timezone.now() - timedelta(minutes=5))
        self.consultation = Consultation.objects.create(
            patient=self.patient,
            psychologue=self.psychologist,
            date=current_start.date(),
            start_time=current_start.time().replace(second=0, microsecond=0),
            duration_minutes=90,
            session_type=Consultation.SessionType.VIDEO,
            status=Consultation.Status.CONFIRMED,
            payment_status=Consultation.PaymentStatus.PAID,
            price="3200.00",
        )
        PaymentRecord.objects.create(
            consultation=self.consultation,
            amount=self.consultation.price,
            method="CIB",
            status="success",
            transaction_ref="ROOM-FEATURE-PAYMENT",
        )

    def test_room_renders_realtime_chat_video_controls_and_psychologist_ai_panel(self):
        room_url = reverse(
            "consultations:consultation_chat",
            args=[self.consultation.pk],
        )
        self.client.force_login(self.patient)
        patient_response = self.client.get(room_url)
        self.assertEqual(patient_response.status_code, 200)
        self.assertContains(patient_response, "/ws/consultations/")
        self.assertContains(patient_response, "RTCPeerConnection")
        self.assertNotContains(patient_response, "Générer le résumé IA")

        self.client.force_login(self.psychologist)
        psychologist_response = self.client.get(room_url)
        self.assertEqual(psychologist_response.status_code, 200)
        self.assertContains(psychologist_response, "Générer le résumé IA")
        self.assertContains(psychologist_response, "Analyser les émotions du patient")

    def test_room_rejects_access_before_scheduled_start(self):
        future_start = timezone.localtime(timezone.now() + timedelta(hours=2))
        self.consultation.date = future_start.date()
        self.consultation.start_time = future_start.time().replace(second=0, microsecond=0)
        self.consultation.duration_minutes = 75
        self.consultation.status = Consultation.Status.CONFIRMED
        self.consultation.save()
        self.client.force_login(self.patient)

        response = self.client.get(
            reverse("consultations:consultation_chat", args=[self.consultation.pk]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("accounts:patient_dashboard"))
        self.assertIn(
            "لا يمكن الدخول إلى الجلسة قبل موعدها المحدد.",
            [str(message) for message in response.wsgi_request._messages],
        )

    def test_room_marks_expired_session_completed_and_denies_entry(self):
        past_start = timezone.localtime(timezone.now() - timedelta(hours=2))
        self.consultation.date = past_start.date()
        self.consultation.start_time = past_start.time().replace(second=0, microsecond=0)
        self.consultation.duration_minutes = 50
        self.consultation.status = Consultation.Status.CONFIRMED
        self.consultation.save()
        self.client.force_login(self.patient)

        response = self.client.get(
            reverse("consultations:consultation_chat", args=[self.consultation.pk]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("accounts:patient_dashboard"))
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, Consultation.Status.COMPLETED)
        self.assertIn(
            "انتهت مدة هذه الجلسة ولا يمكن الدخول إليها.",
            [str(message) for message in response.wsgi_request._messages],
        )

    def test_room_timer_uses_database_end_time_as_timezone_aware_iso(self):
        self.client.force_login(self.patient)
        self.assertTrue(
            has_room_time_access(self.consultation),
            (
                f"start={self.consultation.date} {self.consultation.start_time}, "
                f"end={self.consultation.end_time}, now={timezone.localtime()}"
            ),
        )

        response = self.client.get(
            reverse("consultations:consultation_chat", args=[self.consultation.pk]),
        )

        self.assertEqual(
            response.status_code,
            200,
            f"{response.get('Location')} {list(response.wsgi_request._messages)}",
        )
        self.assertContains(response, 'data-session-end="')
        self.assertContains(response, 'data-server-now="')
        self.assertContains(response, "window.setInterval(updateTimer, 1000)")

    def test_chat_history_is_real_identified_messages_for_both_participants(self):
        self.consultation.session_type = Consultation.SessionType.CHAT
        self.consultation.save(update_fields=["session_type"])
        patient_message = Message.objects.create(
            consultation=self.consultation,
            expediteur=self.patient,
            contenu="Patient-authored consultation message",
        )
        psychologist_message = Message.objects.create(
            consultation=self.consultation,
            expediteur=self.psychologist,
            contenu="Psychologist-authored consultation message",
        )
        SessionSummary.objects.create(
            consultation=self.consultation,
            emotions=["حزن", "سعادة"],
            themes=["sommeil"],
            risk_level="low",
        )
        room_url = reverse("consultations:consultation_chat", args=[self.consultation.pk])

        self.client.force_login(self.patient)
        patient_response = self.client.get(room_url)
        self.assertContains(patient_response, f'data-message-id="{patient_message.pk}"')
        self.assertContains(patient_response, f'data-message-id="{psychologist_message.pk}"')
        self.assertContains(patient_response, f'message-bubble mine"')
        self.assertContains(patient_response, f'message-bubble other"')
        self.assertContains(patient_response, "Patient-authored consultation message")
        self.assertContains(patient_response, "Psychologist-authored consultation message")
        self.assertNotContains(patient_response, "حزن")
        self.assertNotContains(patient_response, "سعادة")

        self.client.force_login(self.psychologist)
        psychologist_response = self.client.get(room_url)
        self.assertContains(psychologist_response, f'data-message-id="{patient_message.pk}"')
        self.assertContains(psychologist_response, f'data-message-id="{psychologist_message.pk}"')
        self.assertContains(psychologist_response, f'message-bubble mine"')
        self.assertContains(psychologist_response, f'message-bubble other"')
        self.assertContains(psychologist_response, "msg-sender")
        self.assertNotContains(psychologist_response, "حزن")
        self.assertNotContains(psychologist_response, "سعادة")

    @patch(
        "ai_service.services._ask",
        return_value={
            "summary": "La personne évoque du stress et des difficultés de sommeil.",
            "themes": ["stress", "sommeil"],
            "emotions": ["anxiété"],
            "risk_level": "low",
        },
    )
    def test_psychologist_can_generate_real_session_summary(self, ask):
        Message.objects.create(
            consultation=self.consultation,
            expediteur=self.patient,
            contenu="Je ressens du stress et je dors difficilement.",
            type_message=Message.TypeMessage.TEXTE,
        )
        self.client.force_login(self.psychologist)
        response = self.client.post(
            reverse(
                "consultations:request_ai_analysis",
                args=[self.consultation.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        self.assertEqual(response.json()["themes"], ["stress", "sommeil"])
        self.assertTrue(response.json()["requires_professional_review"])
        ask.assert_called_once()
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.ai_summary, response.json()["summary"])
        self.assertTrue(
            SessionSummary.objects.filter(consultation=self.consultation).exists()
        )

    def test_ai_summary_endpoint_rejects_patient_and_unassigned_psychologist(self):
        url = reverse(
            "consultations:request_ai_analysis",
            args=[self.consultation.pk],
        )
        self.client.force_login(self.patient)
        self.assertEqual(self.client.post(url).status_code, 403)

        other_psychologist = CustomUser.objects.create_user(
            username="room-feature-other-psychologist",
            password="test-password",
            user_type="psychologue",
        )
        self.client.force_login(other_psychologist)
        self.assertEqual(self.client.post(url).status_code, 403)

    def test_ai_summary_requires_a_paid_confirmed_consultation(self):
        self.consultation.status = Consultation.Status.CANCELLED
        self.consultation.save(update_fields=["status"])
        self.client.force_login(self.psychologist)

        response = self.client.post(
            reverse(
                "consultations:request_ai_analysis",
                args=[self.consultation.pk],
            )
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["status"], "error")

    def test_audio_transcription_consent_is_patient_controlled(self):
        consent_url = reverse(
            "consultations:update_audio_transcription_consent",
            args=[self.consultation.pk],
        )
        self.client.force_login(self.patient)
        patient_response = self.client.post(consent_url, {"consent": "true"})
        self.assertEqual(patient_response.status_code, 200)
        self.consultation.refresh_from_db()
        self.assertTrue(self.consultation.audio_transcription_consent)
        self.assertIsNotNone(self.consultation.audio_transcription_consent_at)

        self.client.force_login(self.psychologist)
        self.assertEqual(
            self.client.post(consent_url, {"consent": "false"}).status_code,
            403,
        )

    def test_doctor_only_ai_json_is_not_rendered_in_patient_room(self):
        self.consultation.doctor_only_ai_summary = {
            "private_marker": "doctor-only-clinical-summary",
        }
        self.consultation.save(update_fields=["doctor_only_ai_summary"])
        self.client.force_login(self.patient)

        response = self.client.get(
            reverse(
                "consultations:consultation_chat",
                args=[self.consultation.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "doctor-only-clinical-summary")

        self.client.force_login(self.psychologist)
        doctor_response = self.client.get(
            reverse(
                "consultations:consultation_chat",
                args=[self.consultation.pk],
            )
        )
        self.assertContains(doctor_response, "doctor-only-clinical-summary")


class ConsultationRoomConsumerTests(TransactionTestCase):
    def setUp(self):
        self.patient = CustomUser.objects.create_user(
            username="realtime-patient",
            password="test-password",
            user_type="patient",
        )
        self.psychologist = CustomUser.objects.create_user(
            username="realtime-psychologist",
            password="test-password",
            user_type="psychologue",
        )
        current_start = timezone.localtime(timezone.now() - timedelta(minutes=5))
        self.consultation = Consultation.objects.create(
            patient=self.patient,
            psychologue=self.psychologist,
            date=current_start.date(),
            start_time=current_start.time().replace(second=0, microsecond=0),
            duration_minutes=90,
            status=Consultation.Status.CONFIRMED,
            payment_status=Consultation.PaymentStatus.PAID,
            price="3200.00",
        )
        PaymentRecord.objects.create(
            consultation=self.consultation,
            amount=self.consultation.price,
            method="CIB",
            status="success",
            transaction_ref="REALTIME-ROOM-PAYMENT",
        )

    def test_websocket_chat_persists_and_broadcasts_message(self):
        async def interact():
            path = f"/ws/consultations/{self.consultation.pk}/"
            patient_communicator = WebsocketCommunicator(
                URLRouter(websocket_urlpatterns),
                path,
            )
            patient_communicator.scope["user"] = self.patient
            patient_connected, _ = await patient_communicator.connect()
            self.assertTrue(patient_connected)
            self.assertEqual(
                (await patient_communicator.receive_json_from())["kind"],
                "ready",
            )

            psychologist_communicator = WebsocketCommunicator(
                URLRouter(websocket_urlpatterns),
                path,
            )
            psychologist_communicator.scope["user"] = self.psychologist
            psychologist_connected, _ = await psychologist_communicator.connect()
            self.assertTrue(psychologist_connected)
            self.assertEqual(
                (await psychologist_communicator.receive_json_from())["kind"],
                "ready",
            )

            await patient_communicator.send_json_to({
                "kind": "chat",
                "content": "Message en temps réel",
            })
            patient_received = await patient_communicator.receive_json_from()
            psychologist_received = await psychologist_communicator.receive_json_from()
            self.assertEqual(patient_received["type"], "chat_message_received")
            self.assertEqual(psychologist_received["type"], "chat_message_received")
            self.assertEqual(patient_received["kind"], "chat")
            self.assertEqual(psychologist_received["kind"], "chat")
            self.assertEqual(psychologist_received["content"], "Message en temps réel")
            self.assertEqual(patient_received["id"], psychologist_received["id"])
            self.assertEqual(patient_received["sender_id"], self.patient.pk)
            self.assertEqual(psychologist_received["sender_id"], self.patient.pk)
            self.assertEqual(patient_received["sender_name"], "realtime-patient")
            self.assertEqual(psychologist_received["sender_name"], "realtime-patient")

            await psychologist_communicator.send_json_to({
                "kind": "chat",
                "content": "Réponse du psychologue",
            })
            patient_reply = await patient_communicator.receive_json_from()
            psychologist_reply = await psychologist_communicator.receive_json_from()
            self.assertEqual(patient_reply["type"], "chat_message_received")
            self.assertEqual(psychologist_reply["type"], "chat_message_received")
            self.assertEqual(patient_reply["content"], "Réponse du psychologue")
            self.assertEqual(patient_reply["sender_id"], self.psychologist.pk)
            self.assertEqual(psychologist_reply["sender_id"], self.psychologist.pk)
            self.assertNotEqual(patient_reply["id"], patient_received["id"])

            await patient_communicator.send_json_to({
                "kind": "signal",
                "signal_type": "offer",
                "signal": {"type": "offer", "sdp": "test-sdp"},
            })
            relayed_signal = await psychologist_communicator.receive_json_from()
            self.assertEqual(relayed_signal["type"], "webrtc_signal_received")
            self.assertEqual(relayed_signal["kind"], "signal")
            self.assertEqual(relayed_signal["signal_type"], "offer")
            self.assertEqual(relayed_signal["payload"]["type"], "offer")
            await patient_communicator.disconnect()
            await psychologist_communicator.disconnect()

        async_to_sync(interact)()
        self.assertTrue(
            Message.objects.filter(
                consultation=self.consultation,
                expediteur=self.patient,
                contenu="Message en temps réel",
            ).exists()
        )
        self.assertEqual(
            Message.objects.filter(
                consultation=self.consultation,
                contenu="Message en temps réel",
            ).count(),
            1,
        )
        self.assertTrue(
            Message.objects.filter(
                consultation=self.consultation,
                expediteur=self.psychologist,
                contenu="Réponse du psychologue",
            ).exists()
        )

    def test_websocket_rejects_unpaid_consultation(self):
        self.consultation.payment_status = Consultation.PaymentStatus.UNPAID
        self.consultation.save(update_fields=["payment_status"])

        async def connect():
            communicator = WebsocketCommunicator(
                URLRouter(websocket_urlpatterns),
                f"/ws/consultations/{self.consultation.pk}/",
            )
            communicator.scope["user"] = self.patient
            connected, close_code = await communicator.connect()
            return connected, close_code

        connected, close_code = async_to_sync(connect)()
        self.assertFalse(connected)
        self.assertEqual(close_code, 4403)
