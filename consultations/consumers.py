import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone

from .access import (
    complete_if_expired,
    has_paid_confirmed_room_access,
    has_room_time_access,
)
from .models import Consultation, Message


class ConsultationRoomConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        self.consultation_id = self.scope["url_route"]["kwargs"]["consultation_id"]
        consultation = await self.get_accessible_consultation()
        if consultation is None:
            await self.close(code=4403)
            return

        self.room_group_name = f"consultation_{self.consultation_id}"
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        await self.send_json({
            "kind": "ready",
            "user_id": self.user.pk,
            "user_type": self.user.user_type,
        })

    async def disconnect(self, _close_code):
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name,
            )

    async def receive(self, text_data=None, bytes_data=None):
        if bytes_data is not None or not text_data or len(text_data) > 65536:
            await self.send_json({"kind": "error", "message": "Message invalide."})
            return
        if await self.get_accessible_consultation() is None:
            await self.close(code=4403)
            return

        try:
            payload = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send_json({"kind": "error", "message": "Message invalide."})
            return

        if not isinstance(payload, dict):
            await self.send_json({"kind": "error", "message": "Message invalide."})
            return

        message_type = payload.get("type")
        legacy_kind = payload.get("kind")

        if message_type == "chat_message" or legacy_kind == "chat":
            content = payload.get("content")
            if not isinstance(content, str) or not content.strip():
                await self.send_json({"kind": "error", "message": "Le message est vide."})
                return
            content = content.strip()
            if len(content) > 5000:
                await self.send_json({
                    "kind": "error",
                    "message": "Le message dépasse la longueur autorisée.",
                })
                return

            message = await self.save_message(content)
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "room.chat_message",
                    "id": message["id"],
                    "sender_id": self.user.pk,
                    "sender_name": self.user.get_full_name() or self.user.username,
                    "content": content,
                    "timestamp": message["timestamp"],
                },
            )
            return

        if message_type == "webrtc_signal" or legacy_kind == "signal":
            signal = payload.get("payload", payload.get("signal"))
            signal_type = payload.get("signal_type")
            if signal_type is None and isinstance(signal, dict):
                signal_type = signal.get("type")
                if signal_type == "candidate":
                    signal_type = "candidate"
            if signal_type not in {"ready", "offer", "answer", "candidate"} or not isinstance(signal, dict):
                await self.send_json({"kind": "error", "message": "Signal d’appel invalide."})
                return
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "room.webrtc_signal",
                    "sender_channel": self.channel_name,
                    "signal_type": signal_type,
                    "payload": signal,
                },
            )
            return

        await self.send_json({"kind": "error", "message": "Type de message inconnu."})

    async def room_chat_message(self, event):
        await self.send_json({
            "type": "chat_message_received",
            "kind": "chat",
            "id": event["id"],
            "sender_id": event["sender_id"],
            "sender_name": event["sender_name"],
            "content": event["content"],
            "timestamp": event["timestamp"],
        })

    async def room_webrtc_signal(self, event):
        if event["sender_channel"] == self.channel_name:
            return
        await self.send_json({
            "type": "webrtc_signal_received",
            "kind": "signal",
            "signal_type": event["signal_type"],
            "payload": event["payload"],
            "signal": event["payload"],
        })

    async def send_json(self, payload):
        await self.send(text_data=json.dumps(payload))

    @database_sync_to_async
    def get_accessible_consultation(self):
        if not self.user.is_authenticated or self.user.user_type not in {"patient", "psychologue"}:
            return None

        participant_field = (
            "patient_id" if self.user.user_type == "patient" else "psychologue_id"
        )
        try:
            consultation = (
                Consultation.objects
                .select_related("payment_record")
                .get(pk=self.consultation_id, **{participant_field: self.user.pk})
            )
        except Consultation.DoesNotExist:
            return None

        complete_if_expired(consultation)
        if not has_paid_confirmed_room_access(consultation):
            return None
        if not has_room_time_access(consultation):
            return None
        return consultation

    @database_sync_to_async
    def save_message(self, content):
        message = Message.objects.create(
            consultation_id=self.consultation_id,
            expediteur_id=self.user.pk,
            contenu=content,
            type_message=Message.TypeMessage.TEXTE,
        )
        return {
            "id": message.pk,
            "timestamp": timezone.localtime(message.date_envoi).isoformat(),
        }
