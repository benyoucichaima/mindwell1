from datetime import timedelta
from django.utils import timezone
from .models import OnlineVisitor

# Chemins excludes du suivi d'activite en ligne.
EXCLUDED_PREFIXES = ("/admin/", "/static/", "/media/", "/ws/")


class OnlineVisitorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        self._track_activity(request)

        return response

    def _track_activity(self, request):
        """Enregistre l'activite des utilisateurs authentifies.

        - Ignore les visiteurs anonymes.
        - Ignore les requetes admin, static, media et WebSocket.
        - Ecrit en base au plus une fois par minute et par utilisateur.
        """
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return

        path = request.path or ""
        if path.startswith(EXCLUDED_PREFIXES):
            return

        now = timezone.now()
        visitor = OnlineVisitor.objects.filter(user=user).first()

        if visitor is None:
            OnlineVisitor.objects.update_or_create(
                user=user,
                defaults={"last_seen": now},
            )
        elif now - visitor.last_seen >= timedelta(minutes=1):
            visitor.last_seen = now
            visitor.save(update_fields=["last_seen"])
