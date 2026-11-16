from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime, timedelta
from consultations.models import WeeklyAvailabilityRule, Creneau, AvailabilityException

class Command(BaseCommand):
    help = 'توليد فترات العمل (Créneaux) تلقائياً بناءً على قواعد التوفر الأسبوعي'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=30, help='عدد الأيام لتوليد المواعيد')

    def handle(self, *args, **kwargs):
        days_to_generate = kwargs['days']
        today = timezone.now().date()
        end_date = today + timedelta(days=days_to_generate)
        
        rules = WeeklyAvailabilityRule.objects.filter(is_active=True)
        generated_count = 0

        for rule in rules:
            current_date = today
            while current_date <= end_date:
                if current_date.weekday() == rule.weekday:
                    is_closed = AvailabilityException.objects.filter(
                        psychologue=rule.psychologue,
                        date=current_date,
                        kind='closed',
                        is_active=True
                    ).exists()

                    if not is_closed:
                        slot_start = datetime.combine(current_date, rule.start_time)
                        slot_end_limit = datetime.combine(current_date, rule.end_time)
                        
                        duration = timedelta(minutes=60)
                        
                        while slot_start + duration <= slot_end_limit:
                            slot_end = slot_start + duration
                            
                            exists = Creneau.objects.filter(
                                psychologue=rule.psychologue,
                                date=current_date,
                                heure_debut=slot_start.time()
                            ).exists()
                            
                            if not exists:
                                Creneau.objects.create(
                                    psychologue=rule.psychologue,
                                    date=current_date,
                                    heure_debut=slot_start.time(),
                                    heure_fin=slot_end.time(),
                                    statut='libre',
                                    is_generated=True
                                )
                                generated_count += 1
                            
                            slot_start = slot_end
                
                current_date += timedelta(days=1)

        self.stdout.write(self.style.SUCCESS(f'تم توليد {generated_count} فترة عمل (Créneau) بنجاح.'))