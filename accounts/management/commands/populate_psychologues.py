# accounts/management/commands/populate_psychologues.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from accounts.models import PsychologueProfile
from django.utils import timezone

User = get_user_model()

class Command(BaseCommand):
    help = 'إنشاء أو تحديث بيانات الـ 15 أخصائي النفسي للعرض التجريبي'

    def handle(self, *args, **kwargs):
        psychologists_data = [
            {
                "first_name": "Amel", "last_name": "Benali", "email": "amel.benali@mindwell-demo.dz",
                "phone": "0550123456", "city": "Alger", "languages": "Français, Arabe, Anglais",
                "title": "Docteur en Psychologie Clinique", "specialty": "tcc",
                "sub_specialties": "Anxiété, Dépression, Gestion du stress",
                "diploma": "Doctorat en Psychologie Clinique", "university": "Université Alger 2",
                "graduation_year": 2009, "experience_years": 15,
                "registration_number": "AGR-ALG-2010-0452", "consultation_mode": "both",
                "hourly_rate": 4000.00, "session_duration": 50, "work_days": "Lundi - Vendredi", "work_hours": "09h00 - 17h00",
                "biography": "Spécialisée dans le traitement de l'anxiété et de la dépression, j'accompagne mes patients avec bienveillance."
            },
            {
                "first_name": "Karim", "last_name": "Mansouri", "email": "karim.mansouri@mindwell-demo.dz",
                "phone": "0661234567", "city": "Oran", "languages": "Français, Arabe",
                "title": "Psychologue Clinicien", "specialty": "systemique",
                "sub_specialties": "Thérapie de couple, Conflits familiaux",
                "diploma": "Magistère en Psychologie Systémique", "university": "Université Oran 2",
                "graduation_year": 2012, "experience_years": 12,
                "registration_number": "AGR-ORN-2013-1120", "consultation_mode": "cabinet",
                "hourly_rate": 3500.00, "session_duration": 60, "work_days": "Samedi - Mercredi", "work_hours": "08h30 - 16h30",
                "biography": "J'aide les couples et les familles à surmonter leurs difficultés relationnelles."
            },
            {
                "first_name": "Leila", "last_name": "Boumediene", "email": "leila.boumediene@mindwell-demo.dz",
                "phone": "0770987654", "city": "Constantine", "languages": "Français, Arabe",
                "title": "Docteur en Psychologie de l'Enfant", "specialty": "enfant_ado",
                "sub_specialties": "TDAH, Anxiété scolaire, Estime de soi",
                "diploma": "Doctorat en Psychologie du Développement", "university": "Université Constantine 3",
                "graduation_year": 2014, "experience_years": 10,
                "registration_number": "AGR-CST-2015-0899", "consultation_mode": "both",
                "hourly_rate": 3500.00, "session_duration": 45, "work_days": "Dimanche - Jeudi", "work_hours": "08h00 - 15h00",
                "biography": "Passionnée par la psychologie de l'enfant, j'accompagne les jeunes de 3 à 18 ans.",
            },
            {
                "first_name": "Yacine", "last_name": "Belkadi", "email": "yacine.belkadi@mindwell-demo.dz",
                "phone": "0555112233", "city": "Blida", "languages": "Français, Arabe, Kabyle",
                "title": "Psychologue Clinicien Certifié EMDR", "specialty": "emdr",
                "sub_specialties": "Traumatismes, SSPT, Deuil",
                "diploma": "Master 2 Psychologie Clinique + Certification EMDR", "university": "Université de Blida 1",
                "graduation_year": 2016, "experience_years": 8,
                "registration_number": "AGR-BLI-2017-0334", "consultation_mode": "both",
                "hourly_rate": 4500.00, "session_duration": 60, "work_days": "Lundi, Mercredi, Vendredi", "work_hours": "10h00 - 18h00",
                "biography": "Certifié EMDR, je me spécialise dans le traitement des traumatismes.",
            },
            {
                "first_name": "Nadia", "last_name": "Cherifi", "email": "nadia.cherifi@mindwell-demo.dz",
                "phone": "0665443322", "city": "Béjaïa", "languages": "Français, Arabe, Kabyle",
                "title": "Psychologue Spécialisée en TCA", "specialty": "clinique",
                "sub_specialties": "Anorexie, Boulimie, Image corporelle",
                "diploma": "Master 2 Psychologie de la Santé", "university": "Université de Béjaïa",
                "graduation_year": 2013, "experience_years": 11,
                "registration_number": "AGR-BEJ-2014-0771", "consultation_mode": "online",
                "hourly_rate": 3000.00, "session_duration": 50, "work_days": "Mardi - Samedi", "work_hours": "09h00 - 16h00",
                "biography": "Spécialisée dans les troubles du comportement alimentaire.",
            },
            {
                "first_name": "Samia", "last_name": "Hamdi", "email": "samia.hamdi@mindwell-demo.dz",
                "phone": "0779887766", "city": "Sétif", "languages": "Français, Arabe",
                "title": "Docteur en Psychopathologie", "specialty": "clinique",
                "sub_specialties": "Dépression, Troubles bipolaires, Psychoéducation",
                "diploma": "Doctorat en Psychopathologie Clinique", "university": "Université Sétif 2",
                "graduation_year": 2010, "experience_years": 14,
                "registration_number": "AGR-SET-2011-0215", "consultation_mode": "both",
                "hourly_rate": 4000.00, "session_duration": 60, "work_days": "Dimanche - Jeudi", "work_hours": "08h00 - 16h00",
                "biography": "Experte dans l'accompagnement des troubles de l'humeur.",
            },
            {
                "first_name": "Farid", "last_name": "Benali", "email": "farid.benali@mindwell-demo.dz",
                "phone": "0550998877", "city": "Tlemcen", "languages": "Français, Arabe",
                "title": "Psychologue Addictologue", "specialty": "addictologie",
                "sub_specialties": "Alcool, Jeux d'argent, Dépendances",
                "diploma": "DU d'Addictologie + Master 2 Psychologie", "university": "Université de Tlemcen",
                "graduation_year": 2011, "experience_years": 13,
                "registration_number": "AGR-TLM-2012-0556", "consultation_mode": "cabinet",
                "hourly_rate": 3500.00, "session_duration": 50, "work_days": "Lundi - Vendredi", "work_hours": "08h30 - 17h30",
                "biography": "Addictologue certifié, j'accompagne les personnes souffrant d'addictions.",
            },
            {
                "first_name": "Sarah", "last_name": "Kaddour", "email": "sarah.kaddour@mindwell-demo.dz",
                "phone": "0661223344", "city": "Alger", "languages": "Français, Arabe, Anglais",
                "title": "Psychologue Clinicienne", "specialty": "systemique",
                "sub_specialties": "Thérapie de couple, Communication, Conflits",
                "diploma": "Master 2 Psychologie Clinique", "university": "Université Alger 1",
                "graduation_year": 2014, "experience_years": 10,
                "registration_number": "AGR-ALG-2015-0992", "consultation_mode": "both",
                "hourly_rate": 4500.00, "session_duration": 75, "work_days": "Mardi - Samedi", "work_hours": "10h00 - 18h00",
                "biography": "Spécialisée en thérapie de couple, j'aide les partenaires à restaurer la communication.",
            },
            {
                "first_name": "Rachid", "last_name": "Messaoudi", "email": "rachid.messaoudi@mindwell-demo.dz",
                "phone": "0770112233", "city": "Batna", "languages": "Français, Arabe",
                "title": "Psychologue Clinicien", "specialty": "clinique",
                "sub_specialties": "Psychotraumatologie, Violences, Enfants",
                "diploma": "Master 2 Psychologie Clinique", "university": "Université de Batna 2",
                "graduation_year": 2013, "experience_years": 11,
                "registration_number": "AGR-BAT-2014-0443", "consultation_mode": "both",
                "hourly_rate": 3000.00, "session_duration": 50, "work_days": "Dimanche - Jeudi", "work_hours": "08h00 - 15h00",
                "biography": "Formé à la psychotraumatologie, j'accompagne les enfants et adultes.",
            },
            {
                "first_name": "Amina", "last_name": "Ziani", "email": "amina.ziani@mindwell-demo.dz",
                "phone": "0555667788", "city": "Annaba", "languages": "Français, Arabe",
                "title": "Docteur en Psychologie Humaniste", "specialty": "humaniste",
                "sub_specialties": "Deuil, Accompagnement existentiel",
                "diploma": "Doctorat en Psychologie Humaniste", "university": "Université Badji Mokhtar Annaba",
                "graduation_year": 2015, "experience_years": 9,
                "registration_number": "AGR-ANN-2016-0112", "consultation_mode": "online",
                "hourly_rate": 3500.00, "session_duration": 50, "work_days": "Lundi, Mercredi, Vendredi", "work_hours": "09h00 - 17h00",
                "biography": "J'offre un espace d'écoute empathique pour traverser les épreuves de la vie.",
            },
            {
                "first_name": "Karim", "last_name": "Bouzid", "email": "karim.bouzid@mindwell-demo.dz",
                "phone": "0660998877", "city": "Tizi Ouzou", "languages": "Français, Arabe, Kabyle",
                "title": "Psychologue du Travail", "specialty": "travail",
                "sub_specialties": "Burn-out, Stress professionnel",
                "diploma": "Master 2 Psychologie du Travail", "university": "Université Mouloud Mammeri Tizi Ouzou",
                "graduation_year": 2017, "experience_years": 7,
                "registration_number": "AGR-TIZ-2018-0334", "consultation_mode": "both",
                "hourly_rate": 4000.00, "session_duration": 50, "work_days": "Dimanche - Jeudi", "work_hours": "08h30 - 16h30",
                "biography": "Spécialisé dans les risques psychosociaux au travail.",
            },
            {
                "first_name": "Lina", "last_name": "Merabet", "email": "lina.merabet@mindwell-demo.dz",
                "phone": "0771234567", "city": "Biskra", "languages": "Français, Arabe",
                "title": "Docteur en Psychologie Clinique", "specialty": "clinique",
                "sub_specialties": "Troubles du sommeil, Anxiété généralisée",
                "diploma": "Doctorat en Psychologie Clinique", "university": "Université de Biskra",
                "graduation_year": 2012, "experience_years": 12,
                "registration_number": "AGR-BIS-2013-0556", "consultation_mode": "both",
                "hourly_rate": 3000.00, "session_duration": 50, "work_days": "Samedi - Mercredi", "work_hours": "09h00 - 17h00",
                "biography": "J'accompagne les personnes souffrant d'insomnies et d'anxiété généralisée.",
            },
            {
                "first_name": "Yassine", "last_name": "Toumi", "email": "yassine.toumi@mindwell-demo.dz",
                "phone": "0550123987", "city": "Sidi Bel Abbès", "languages": "Français, Arabe",
                "title": "Psychologue Scolaire", "specialty": "enfant_ado",
                "sub_specialties": "Orientation scolaire, TDAH",
                "diploma": "Master 2 Psychologie de l'Éducation", "university": "Université Djillali Liabès",
                "graduation_year": 2016, "experience_years": 8,
                "registration_number": "AGR-SBA-2017-0221", "consultation_mode": "cabinet",
                "hourly_rate": 2500.00, "session_duration": 45, "work_days": "Dimanche - Jeudi", "work_hours": "08h00 - 16h00",
                "biography": "J'aide les adolescents et leurs familles à naviguer dans les difficultés scolaires.",
            },
            {
                "first_name": "Nour El Houda", "last_name": "Benali", "email": "nour.elhouda@mindwell-demo.dz",
                "phone": "0665432109", "city": "Ouargla", "languages": "Français, Arabe",
                "title": "Psychologue Clinicienne", "specialty": "integrative",
                "sub_specialties": "Psychologie positive, Développement personnel",
                "diploma": "Master 2 Psychologie Clinique", "university": "Université de Ouargla",
                "graduation_year": 2014, "experience_years": 10,
                "registration_number": "AGR-ORG-2015-0119", "consultation_mode": "online",
                "hourly_rate": 3500.00, "session_duration": 60, "work_days": "Lundi - Vendredi", "work_hours": "09h00 - 17h00",
                "biography": "Je vous accompagne vers une meilleure connaissance de soi.",
            },
            {
                "first_name": "Mehdi", "last_name": "Saidi", "email": "mehdi.saidi@mindwell-demo.dz",
                "phone": "0770889900", "city": "Mostaganem", "languages": "Français, Arabe",
                "title": "Psychologue Clinicien", "specialty": "tcc",
                "sub_specialties": "Phobies, TOC, Troubles anxieux",
                "diploma": "Master 2 Psychologie Clinique", "university": "Université Abdelhamid Ibn Badis",
                "graduation_year": 2015, "experience_years": 9,
                "registration_number": "AGR-MOS-2016-0445", "consultation_mode": "both",
                "hourly_rate": 3000.00, "session_duration": 50, "work_days": "Dimanche - Jeudi", "work_hours": "08h30 - 16h30",
                "biography": "Spécialisé dans les troubles anxieux et obsessionnels, j'utilise les TCC."
            }
        ]

        created_count = 0
        updated_count = 0

        for data in psychologists_data:
            # 1. إنشاء أو تحديث حساب المستخدم (CustomUser)
            user, user_created = User.objects.update_or_create(
                email=data["email"],
                defaults={
                    "username": data["email"],
                    "first_name": data["first_name"],
                    "last_name": data["last_name"],
                    "phone": data["phone"],
                    "user_type": "psychologue",
                    "is_active": True,
                }
            )

            # 2. إنشاء أو تحديث ملف الأخصائي النفسي
            profile, profile_created = PsychologueProfile.objects.update_or_create(
                user=user,
                defaults={
                    "title": data["title"],
                    "specialty": data["specialty"],
                    "sub_specialties": data["sub_specialties"],
                    "diploma": data["diploma"],
                    "university": data["university"],
                    "graduation_year": data["graduation_year"],
                    "experience_years": data["experience_years"],
                    "registration_number": data["registration_number"],
                    "consultation_mode": data["consultation_mode"],
                    "city": data["city"],
                    "languages": data["languages"],
                    "hourly_rate": data["hourly_rate"],
                    "session_duration": data["session_duration"],
                    "work_days": data["work_days"],
                    "work_hours": data["work_hours"],
                    "biography": data["biography"],
                    "average_rating": None,
                    "review_count": 0,
                    "is_verified": True,  # تم التحقق منهم تلقائياً لأغراض العرض التجريبي
                    "verification_status": "approved",
                    "verification_date": timezone.now(),
                }
            )

            if profile_created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'✅ نجاح: تم إنشاء {created_count} أخصائي جديد، وتحديث {updated_count} أخصائي موجود.'
        ))