from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils.translation import gettext as _

from accounts.models import CustomUser, Notification, PsychologueProfile
from mindwell.models import ContactMessage
from .models import Report


def notify_administrators(title, message, url):
    administrator_ids = CustomUser.objects.filter(
        is_staff=True,
        is_active=True,
    ).values_list("pk", flat=True)
    Notification.objects.bulk_create(
        [
            Notification(user_id=user_id, title=title, message=message, url=url)
            for user_id in administrator_ids
        ]
    )


@receiver(post_save, sender=PsychologueProfile)
def notify_pending_psychologist(sender, instance, created, **kwargs):
    if not created or instance.is_verified or instance.verification_status != "pending":
        return
    name = instance.user.get_full_name() or instance.user.username
    notify_administrators(
        _("New psychologist verification request"),
        _("%(name)s submitted a profile for verification.") % {"name": name},
        reverse("admin_verifications"),
    )


@receiver(post_save, sender=Report)
def notify_new_report(sender, instance, created, **kwargs):
    if not created:
        return
    notify_administrators(
        _("New report submitted"),
        _("A new report was submitted about %(name)s.")
        % {"name": instance.target.get_full_name() or instance.target.username},
        reverse("admin_reports"),
    )


@receiver(post_save, sender=ContactMessage)
def notify_new_contact_message(sender, instance, created, **kwargs):
    if not created:
        return
    notify_administrators(
        _("New contact message"),
        _("%(name)s sent a contact message.") % {"name": instance.name},
        reverse("admin_contact_messages"),
    )
