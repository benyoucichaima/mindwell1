from django.conf import settings
from django.db import models
from django.utils import timezone
from datetime import timedelta


class OnlineVisitor(models.Model):
    """Utilisateur authentifié actuellement actif sur le site.

    Une ligne par utilisateur connecte, mise a jour au plus une fois par
    minute pour eviter de saturer PostgreSQL sur Render.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="online_visits",
        db_index=True,
    )
    last_seen = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user"], name="unique_online_visitor_per_user"
            )
        ]

    @classmethod
    def count_online(cls, minutes=2):
        """Nombre d'utilisateurs distincts actifs dans les N dernieres minutes."""
        limit = timezone.now() - timedelta(minutes=minutes)
        return cls.objects.filter(last_seen__gte=limit).count()
