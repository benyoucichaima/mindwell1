from django.urls import path

from .consumers import ConsultationRoomConsumer


websocket_urlpatterns = [
    path(
        "ws/consultations/<uuid:consultation_id>/",
        ConsultationRoomConsumer.as_asgi(),
    ),
]
