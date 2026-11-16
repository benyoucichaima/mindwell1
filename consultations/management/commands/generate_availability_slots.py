from django.core.management.base import BaseCommand

from accounts.models import PsychologueProfile

from consultations.scheduling import generate_slots


class Command(BaseCommand):
    help = 'Generate and reconcile psychologist availability for the next 28 calendar days.'

    def handle(self, *args, **options):
        profiles = PsychologueProfile.objects.filter(
            is_verified=True,
            user__is_active=True,
            user__user_type='psychologue',
        ).select_related('user')
        total_created = 0
        total_warnings = 0
        for profile in profiles.iterator():
            result = generate_slots(profile.user)
            total_created += result['created']
            total_warnings += len(result['warnings'])
            for warning in result['warnings']:
                self.stdout.write(self.style.WARNING(
                    f'{profile.user_id}: {warning}'
                ))
        self.stdout.write(self.style.SUCCESS(
            f'Created {total_created} slots; reported {total_warnings} scheduling warning(s).'
        ))
