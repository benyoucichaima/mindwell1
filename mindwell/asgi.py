import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mindwell.settings')

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

django_asgi_application = get_asgi_application()

from accounts.routing import websocket_urlpatterns
from consultations.routing import websocket_urlpatterns as consultation_websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": django_asgi_application,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            websocket_urlpatterns + consultation_websocket_urlpatterns
        )
    ),
})