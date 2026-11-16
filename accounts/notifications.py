import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.utils import timezone

from .models import Notification


logger = logging.getLogger(__name__)


def _publish_notification(user_id, payload):
    channel_layer = get_channel_layer()
    if channel_layer is None:
        logger.error("Cannot publish notification: no Channels layer is configured.")
        return

    try:
        async_to_sync(channel_layer.group_send)(
            f"user_{user_id}",
            {"type": "notification.event", "payload": payload},
        )
    except Exception:
        logger.exception("Could not publish notification to user group %s.", user_id)


def notify_user(user_id, event_type, message, payload=None, title='', url=''):
    """Persist a notification and publish its non-sensitive event after commit.

    ``title`` and ``url`` are optional; when ``url`` is set, clients can link
    the notification directly to the related page (e.g. a note).
    """
    notification = Notification.objects.create(
        user_id=user_id, message=message, title=title, url=url
    )
    event_payload = {
        "type": event_type,
        "notification_id": notification.pk,
        "message": message,
        "created_at": timezone.localtime(notification.created_at).isoformat(),
    }
    if title:
        event_payload["title"] = title
    if url:
        event_payload["action_url"] = url
    if payload:
        event_payload.update(payload)

    transaction.on_commit(
        lambda: _publish_notification(user_id, event_payload)
    )
    return notification
