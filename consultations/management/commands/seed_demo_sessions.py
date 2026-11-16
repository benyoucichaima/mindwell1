from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.urls import reverse
from django.conf import settings
from django.db.models import Q
from datetime import datetime, date, time, timedelta
import json
from pathlib import Path

from accounts.models import CustomUser
from consultations.models import Consultation, Creneau, PaymentRecord
from consultations.access import has_room_time_access, consultation_time_bounds


# Date fixe de la d\u00e9mo : 05/11/2026 (Africa/Algiers = fuseau du projet).
DEMO_DATE = date(2026, 11, 5)
DEMO_START = time(20, 0)
DEMO_END = time(21, 0)
DEMO_DURATION_MINUTES = 60

STATE_FILE = Path(settings.BASE_DIR) / 'seed_demo_sessions_state.json'


def resolve_user(value):
    """R\u00e9sout un identifiant par email, username ou nom complet (pr\u00e9nom NOM)."""
    value = value.strip()
    if not value:
        return None
    user = (
        CustomUser.objects.filter(email__iexact=value).first()
        or CustomUser.objects.filter(username__iexact=value).first()
    )
    if user:
        return user
    parts = value.split()
    if len(parts) >= 2:
        user = CustomUser.objects.filter(
            first_name__iexact=parts[0], last_name__iexact=parts[-1]
        ).first()
        if user:
            return user
    return CustomUser.objects.filter(
        Q(first_name__icontains=value) | Q(last_name__icontains=value)
    ).first()


def full_name(user):
    return f"{user.first_name} {user.last_name}".strip() or user.username


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_state(entries):
    STATE_FILE.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding='utf-8')


class Command(BaseCommand):
    help = 'S\u00e9mence trois consultations de d\u00e9mo le 05/11/2026 de 20:00 \u00e0 21:00 (vid\u00e9o, audio, chat).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--psychologues',
            nargs=3,
            metavar='ID',
            help='Trois identifiants (email ou username) dans l\u2019ordre : vid\u00e9o, audio, chat.',
        )
        parser.add_argument(
            '--patients',
            nargs='+',
            metavar='ID',
            help='Un ou trois identifiants (email ou username) de patient(s).',
        )
        parser.add_argument(
            '--cleanup',
            action='store_true',
            help='Supprime uniquement les consultations/cr\u00e9neaux/paiements cr\u00e9\u00e9s par ce script.',
        )

    def handle(self, *args, **kwargs):
        if kwargs['cleanup']:
            self._cleanup()
            return

        psychologue_ids = kwargs['psychologues']
        patient_ids = kwargs['patients']

        if not psychologue_ids or len(psychologue_ids) != 3:
            raise CommandError(
                '--psychologues doit contenir exactement 3 identifiants (vid\u00e9o, audio, chat).'
            )
        if not patient_ids or len(patient_ids) not in (1, 3):
            raise CommandError(
                '--patients doit contenir 1 ou 3 identifiants de patient.'
            )

        # --- R\u00e9solution des psychologues ---
        raw_psychos = [resolve_user(v) for v in psychologue_ids]
        missing = [v for v, u in zip(psychologue_ids, raw_psychos) if u is None]
        if missing:
            raise CommandError(
                "Psychologue(s) introuvable(s) : %s. "
                "Utilisez un email ou un username existant." % ', '.join(missing)
            )

        video_psy, audio_psy, chat_psy = raw_psychos

        # R\u00e8gle 1 : la VID\u00c9O est obligatoirement Nour El Houda Benali.
        if full_name(video_psy).lower() != 'nour el houda benali':
            raise CommandError(
                "Le psychologue de la VID\u00c9O doit \u00eatre 'Nour El Houda Benali'. "
                f"Vous avez fourni : {full_name(video_psy)} ({video_psy.username})."
            )

        # R\u00e8gle 2 : AUDIO et CHAT = deux AUTRES psychologues v\u00e9rifi\u00e9s, actifs.
        for label, psy in (('AUDIO', audio_psy), ('CHAT', chat_psy)):
            if psy.user_type != 'psychologue':
                raise CommandError(f"{label} n\u2019est pas un psychologue : {full_name(psy)}.")
            try:
                profile = psy.psychologue_profile
            except CustomUser.psychologue_profile.RelatedObjectDoesNotExist:
                raise CommandError(f"{label} n\u2019a pas de profil : {full_name(psy)}.")
            if not profile.is_verified:
                raise CommandError(f"{label} n\u2019est pas v\u00e9rifi\u00e9 : {full_name(psy)}.")
            if not psy.is_active:
                raise CommandError(f"{label} est inactif : {full_name(psy)}.")

        if audio_psy.pk == video_psy.pk or chat_psy.pk == video_psy.pk or audio_psy.pk == chat_psy.pk:
            raise CommandError(
                "Les trois psychologues doivent \u00eatre distincts (vid\u00e9o, audio, chat)."
            )

        # Liste affichage (r\u00e8gle 4 : jamais de choix implicite sans confirmation).
        self.stdout.write('')
        self.stdout.write('Psychologues r\u00e9solus pour la d\u00e9mo :')
        self.stdout.write(f"  VID\u00c9O  -> {full_name(video_psy)} ({video_psy.username})")
        self.stdout.write(f"  AUDIO    -> {full_name(audio_psy)} ({audio_psy.username})")
        self.stdout.write(f"  CHAT     -> {full_name(chat_psy)} ({chat_psy.username})")

        # --- R\u00e9solution des patients ---
        raw_patients = [resolve_user(v) for v in patient_ids]
        missing = [v for v, u in zip(patient_ids, raw_patients) if u is None]
        if missing:
            raise CommandError(
                "Patient(s) introuvable(s) : %s." % ', '.join(missing)
            )
        for p in raw_patients:
            if p.user_type != 'patient':
                raise CommandError(f"{full_name(p)} n\u2019est pas un patient.")

        # R\u00e8gle 3 : un seul patient \u00e0 trois cr\u00e9neaux qui se chevauchent.
        # Le mod\u00e8le Consultation.clean() v\u00e9rifie le chevauchement par psychologue uniquement,
        # il n\u2019y a pas d\u2019interdiction au niveau patient. Un patient unique est donc utilisable.
        if len(raw_patients) == 1:
            self.stdout.write(
                '\nUn seul patient fourni : l\u2019application n\u2019interdit pas '
                'qu\u2019un m\u00eame patient ait trois consultations simultan\u00e9es '
                '(le contr\u00f4le de chevauchement porte sur le psychologue). '
                f"Utilisation de {full_name(raw_patients[0])} pour les trois consultations."
            )
            patients = raw_patients * 3
        else:
            patients = raw_patients

        self.stdout.write('')
        self.stdout.write('Patient(s) :')
        for idx, p in enumerate(patients):
            self.stdout.write(f"  {idx+1}. {full_name(p)} ({p.username})")

        self.stdout.write(self.style.WARNING(
            '\nConfirmez-vous la cr\u00e9ation de ces trois consultations de d\u00e9mo ? '
            '(Ce script ne fait pas de pause interactive ; passez --cleanup pour annuler apr\u00e8s coup.)'
        ))

        # --- Cr\u00e9ation / r\u00e9utilisation idempotente ---
        tz = timezone.get_current_timezone()
        start_aware = timezone.make_aware(datetime.combine(DEMO_DATE, DEMO_START), tz)
        end_aware = timezone.make_aware(datetime.combine(DEMO_DATE, DEMO_END), tz)

        sessions = [
            ('vid\u00e9o', Consultation.SessionType.VIDEO, video_psy, patients[0]),
            ('audio', Consultation.SessionType.AUDIO, audio_psy, patients[1]),
            ('chat', Consultation.SessionType.CHAT, chat_psy, patients[2]),
        ]

        state_entries = load_state()
        existing_pk_set = {e['consultation_id'] for e in state_entries}
        created = []

        for label, session_type, psychologue, patient in sessions:
            # Cr\u00e9neau : r\u00e9utiliser s\u2019il existe (psychologue, date, heure_debut).
            creneau, _ = Creneau.objects.get_or_create(
                psychologue=psychologue,
                date=DEMO_DATE,
                heure_debut=DEMO_START,
                defaults={
                    'heure_fin': DEMO_END,
                    'statut': Creneau.Statut.RESERVE,
                    'is_generated': False,
                    'is_bookable': False,
                },
            )
            if (
                creneau.heure_fin != DEMO_END
                or creneau.statut != Creneau.Statut.RESERVE
            ):
                creneau.heure_fin = DEMO_END
                creneau.statut = Creneau.Statut.RESERVE
                creneau.is_bookable = False
                creneau.save()

            # Consultation : r\u00e9utiliser si d\u00e9j\u00e0 li\u00e9e \u00e0 ce cr\u00e9neau.
            consultation = Consultation.objects.filter(creneau=creneau).first()
            price = getattr(
                getattr(psychologue, 'psychologue_profile', None), 'hourly_rate', None
            ) or 3000.00

            if consultation is None:
                consultation = Consultation(
                    patient=patient,
                    psychologue=psychologue,
                    creneau=creneau,
                    date=DEMO_DATE,
                    start_time=DEMO_START,
                    duration_minutes=DEMO_DURATION_MINUTES,
                    session_type=session_type,
                    status=Consultation.Status.CONFIRMED,
                    payment_status=Consultation.PaymentStatus.PAID,
                    price=price,
                )
                consultation.save()
            else:
                consultation.patient = patient
                consultation.psychologue = psychologue
                consultation.date = DEMO_DATE
                consultation.start_time = DEMO_START
                consultation.duration_minutes = DEMO_DURATION_MINUTES
                consultation.session_type = session_type
                consultation.status = Consultation.Status.CONFIRMED
                consultation.payment_status = Consultation.PaymentStatus.PAID
                consultation.price = price
                consultation.save(update_fields=[
                    'patient', 'psychologue', 'date', 'start_time', 'duration_minutes',
                    'session_type', 'status', 'payment_status', 'price', 'updated_at',
                ])

            # PaymentRecord : coh\u00e9rence exig\u00e9e par consultation_chat.
            payment, _ = PaymentRecord.objects.get_or_create(
                consultation=consultation,
                defaults={
                    'amount': consultation.price,
                    'method': 'CIB',
                    'status': 'success',
                },
            )
            if (
                payment.amount != consultation.price
                or payment.status != 'success'
                or payment.method != 'CIB'
            ):
                payment.amount = consultation.price
                payment.method = 'CIB'
                payment.status = 'success'
                payment.save(update_fields=['amount', 'method', 'status'])

            room_url = reverse('consultations:consultation_chat', args=[consultation.pk])
            created.append({
                'label': label,
                'consultation_id': str(consultation.pk),
                'creneau_id': str(creneau.pk),
                'payment_id': str(payment.pk),
                'psychologue': full_name(psychologue),
                'patient': full_name(patient),
                'session_type': session_type,
                'room_url': room_url,
                'accessible_from': start_aware.isoformat(),
            })

        # Enregistre l\u2019\u00e9tat pour le nettoyage --cleanup.
        known = {e['consultation_id'] for e in state_entries}
        for entry in created:
            if entry['consultation_id'] not in known:
                state_entries.append(entry)
                known.add(entry['consultation_id'])
        save_state(state_entries)

        # --- Rendu du tableau ---
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=== Consultations de d\u00e9mo cr\u00e9\u00e9es (05/11/2026, 20:00-21:00) ==='))
        header = f"{'Type':<8} | {'Psychologue':<26} | {'Patient':<20} | {'ID consultation':<36} | {'URL salle'}"
        self.stdout.write(header)
        self.stdout.write('-' * len(header))
        for entry in created:
            self.stdout.write(
                f"{entry['label']:<8} | {entry['psychologue']:<26} | {entry['patient']:<20} | "
                f"{entry['consultation_id']:<36} | {entry['room_url']}"
            )
        self.stdout.write('')
        self.stdout.write(f"Heure d\u2019ouverture de la salle (has_room_time_access) : {start_aware:%Y-%m-%d %H:%M %Z}")
        self.stdout.write(
            f"Fuseau : {settings.TIME_ZONE}. La salle est accessible de 20:00 \u00e0 21:00, "
            f"tant que la consultation n\u2019est pas d\u00e9pass\u00e9e."
        )

        # --- V\u00e9rification du support de chaque type par la salle ---
        self.stdout.write('')
        self.stdout.write('=== Support des types de consultation par la salle (consultation_chat) ===')
        ice_ok = bool(getattr(settings, 'WEBRTC_ICE_SERVERS', None))
        ice_label = 'configur\u00e9' if ice_ok else 'ABSENT'
        self.stdout.write(
            "- VID\u00c9O : WebRTC (consultation_chat, settings.WEBRTC_ICE_SERVERS=%s)." % ice_label
        )
        if not ice_ok:
            self.stdout.write(self.style.WARNING(
                "  ATTENTION : WEBRTC_ICE_SERVERS n\u2019est pas configur\u00e9 ; la vid\u00e9o pourrait ne pas s\u2019ouvrir correctement."
            ))
        self.stdout.write("- AUDIO : m\u00eame vue consultation_chat, aucune restriction de type ; s\u2019ouvre normalement si acc\u00e8s valide.")
        self.stdout.write("- CHAT : m\u00eame vue consultation_chat, aucune restriction de type ; s\u2019ouvre normalement si acc\u00e8s valide.")
        self.stdout.write('')
        self.stdout.write(
            "Acc\u00e8s \u00e0 la salle r\u00e9quis : statut confirm\u00e9e, payment_status pay\u00e9, "
            "PaymentRecord(status='success', amount == price), et horaire dans [20:00, 21:00)."
        )
        self.stdout.write('')
        self.stdout.write("Pour nettoyer : python manage.py seed_demo_sessions --cleanup")

    def _cleanup(self):
        state_entries = load_state()
        if not state_entries:
            self.stdout.write(self.style.WARNING("Aucune session de d\u00e9mo \u00e0 nettoyer (état vide)."))
            return

        deleted = {'consultation': 0, 'creneau': 0, 'payment': 0}
        for entry in state_entries:
            # Paiement d\u2019abord (FK vers Consultation), puis consultation, puis cr\u00e9neau.
            try:
                PaymentRecord.objects.filter(consultation_id=entry['consultation_id']).delete()
                deleted['payment'] += 1
            except PaymentRecord.DoesNotExist:
                pass
            try:
                Consultation.objects.filter(pk=entry['consultation_id']).delete()
                deleted['consultation'] += 1
            except Consultation.DoesNotExist:
                pass
            try:
                Creneau.objects.filter(pk=entry['creneau_id']).delete()
                deleted['creneau'] += 1
            except Creneau.DoesNotExist:
                pass

        save_state([])
        self.stdout.write(self.style.SUCCESS(
            f"Nettoyage termin\u00e9 : {deleted['consultation']} consultation(s), "
            f"{deleted['creneau']} cr\u00e9neau(x), {deleted['payment']} paiement(s) supprim\u00e9(s)."
        ))
