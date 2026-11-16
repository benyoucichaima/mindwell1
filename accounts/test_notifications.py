from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase
from django.contrib.auth.models import AnonymousUser

from .models import CustomUser
from .notifications import notify_user
from .routing import websocket_urlpatterns


class NotificationConsumerTests(TransactionTestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="notification-user",
            password="test-password",
            user_type="psychologue",
        )

    def test_authenticated_user_receives_personal_group_notification(self):
        async def interact():
            communicator = WebsocketCommunicator(
                URLRouter(websocket_urlpatterns),
                "/ws/notifications/",
            )
            communicator.scope["user"] = self.user
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            payload = {
                "type": "session_requested",
                "consultation_id": "consultation-123",
            }
            await get_channel_layer().group_send(
                f"user_{self.user.pk}",
                {"type": "notification.event", "payload": payload},
            )
            self.assertEqual(await communicator.receive_json_from(), payload)
            await communicator.disconnect()

        async_to_sync(interact)()

    def test_unauthenticated_user_is_rejected(self):
        async def connect():
            communicator = WebsocketCommunicator(
                URLRouter(websocket_urlpatterns),
                "/ws/notifications/",
            )
            communicator.scope["user"] = AnonymousUser()
            connected, close_code = await communicator.connect()
            return connected, close_code

        connected, close_code = async_to_sync(connect)()
        self.assertFalse(connected)
        self.assertEqual(close_code, 4401)

    def test_notify_user_persists_and_publishes_to_the_users_group(self):
        async def interact():
            communicator = WebsocketCommunicator(
                URLRouter(websocket_urlpatterns),
                "/ws/notifications/",
            )
            communicator.scope["user"] = self.user
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            await database_sync_to_async(notify_user)(
                self.user.pk,
                "session_requested",
                "Nouvelle demande de consultation.",
                {"consultation_id": "consultation-123"},
            )
            event = await communicator.receive_json_from()
            self.assertEqual(event["type"], "session_requested")
            self.assertEqual(event["consultation_id"], "consultation-123")
            await communicator.disconnect()

        async_to_sync(interact)()
