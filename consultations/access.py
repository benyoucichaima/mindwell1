from datetime import datetime, timedelta

from django.db.models import F, Q
from django.utils import timezone

from .models import Consultation, PaymentRecord


def consultation_time_bounds(consultation):
    current_timezone = timezone.get_current_timezone()
    start = timezone.make_aware(
        datetime.combine(consultation.date, consultation.start_time),
        current_timezone,
    )
    end = timezone.make_aware(
        datetime.combine(consultation.date, consultation.end_time),
        current_timezone,
    )
    if consultation.end_time <= consultation.start_time:
        end += timedelta(days=1)
    return start, end


def consultation_has_started(consultation, now=None):
    start, _ = consultation_time_bounds(consultation)
    return (now or timezone.now()) >= start


def consultation_has_ended(consultation, now=None):
    _, end = consultation_time_bounds(consultation)
    return (now or timezone.now()) >= end


def complete_expired_consultations(queryset, now=None):
    now = now or timezone.now()
    local_now = timezone.localtime(now)
    return queryset.filter(
        status__in=(
            Consultation.Status.PENDING,
            Consultation.Status.CONFIRMED,
            Consultation.Status.IN_PROGRESS,
        )
    ).filter(
        Q(date__lt=local_now.date())
        | Q(
            date=local_now.date(),
            end_time__gt=F("start_time"),
            end_time__lte=local_now.time(),
        )
    ).update(status=Consultation.Status.COMPLETED, updated_at=now)


def complete_if_expired(consultation, now=None):
    if (
        consultation.status in {
            Consultation.Status.PENDING,
            Consultation.Status.CONFIRMED,
            Consultation.Status.IN_PROGRESS,
        }
        and consultation_has_ended(consultation, now)
    ):
        now = now or timezone.now()
        Consultation.objects.filter(
            pk=consultation.pk,
            status=consultation.status,
        ).update(status=Consultation.Status.COMPLETED, updated_at=now)
        consultation.status = Consultation.Status.COMPLETED
        consultation.updated_at = now
        return True
    return False


def has_room_time_access(consultation, now=None):
    now = now or timezone.now()
    start, end = consultation_time_bounds(consultation)
    return start <= now < end


def has_paid_confirmed_room_access(consultation):
    if consultation.status not in {
        Consultation.Status.CONFIRMED,
        Consultation.Status.IN_PROGRESS,
    }:
        return False
    if consultation.payment_status != Consultation.PaymentStatus.PAID:
        return False

    try:
        payment = consultation.payment_record
    except PaymentRecord.DoesNotExist:
        return False
    return payment.status == "success" and payment.amount == consultation.price
