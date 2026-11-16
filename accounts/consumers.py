import asyncio
import json

from django.db.models import Q
from django.utils import timezone
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Conversation, Message
from ai_service.services import analyse_and_save


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4401)
            return

        self.user_group_name = f"user_{user.pk}"
        await self.channel_layer.group_add(self.user_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "user_group_name"):
            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name,
            )

    async def notification_event(self, event):
        await self.send(text_data=json.dumps(event["payload"]))


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        self.conv_id = self.scope["url_route"]["kwargs"]["conversation_id"]
        if not self.user.is_authenticated or not await self.is_member():
            await self.close()
            return
        self.room = f"chat_{self.conv_id}"
        self.doctor_room = f"doctor_{self.conv_id}"
        await self.channel_layer.group_add(self.room, self.channel_name)
        if self.user.user_type == "psychologue":          # الطبيب فقط
            await self.channel_layer.group_add(self.doctor_room, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "room"):
            await self.channel_layer.group_discard(self.room, self.channel_name)
            await self.channel_layer.group_discard(self.doctor_room, self.channel_name)

    async def receive(self, text_data):
        content = (json.loads(text_data).get("content") or "").strip()
        if not content:
            return
        msg_id = await self.save_message(content)
        await self.channel_layer.group_send(self.room, {
            "type": "chat.message", "id": msg_id, "sender_id": self.user.id,
            "content": content, "time": timezone.now().isoformat(),
        })
        if self.user.user_type == "patient":               # تحليل رسائل المريض فقط
            asyncio.create_task(self.run_ai(msg_id, content))

    async def run_ai(self, msg_id, text):
        try:
            result = await database_sync_to_async(analyse_and_save)(msg_id, text)
        except Exception as e:
            print("AI error:", e)                          # لا تعطلي المحادثة إذا فشل الـ AI
            return
        await self.channel_layer.group_send(self.doctor_room, {"type": "ai.update", **result})

    # ---- handlers ----
    async def chat_message(self, event):
        await self.send(text_data=json.dumps({"kind": "chat", **{k: v for k, v in event.items() if k != "type"}}))

    async def ai_update(self, event):                      # يصل للطبيب فقط
        await self.send(text_data=json.dumps({"kind": "ai", **{k: v for k, v in event.items() if k != "type"}}))

    # ---- db ----
    @database_sync_to_async
    def is_member(self):
        return Conversation.objects.filter(Q(patient=self.user) | Q(psychologue=self.user), id=self.conv_id).exists()

    @database_sync_to_async
    def save_message(self, content):
        conv = Conversation.objects.get(id=self.conv_id)
        msg = Message.objects.create(conversation=conv, sender=self.user, content=content)
        conv.updated_at = timezone.now()
        conv.save(update_fields=["updated_at"])
        return msg.pk


class CallConsumer(AsyncWebsocketConsumer):
    """مستهلك مؤقت للمكالمات لتجنب أخطاء الاستيراد"""
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        await self.accept()

    async def disconnect(self, close_code):
        pass

    async def receive(self, text_data):
        pass