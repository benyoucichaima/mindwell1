from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import Http404
from django.db.models import Q
from django.db.models import Avg, Count
from django.utils import timezone
from django.utils.translation import gettext_lazy
from accounts.models import PsychologueProfile, CustomUser
from consultations.models import Consultation, PaymentRecord
from .models import Psychologue, Specialite
from .forms import ContactForm
import uuid

# 1. إصلاح دالة عرض الأخصائيين
def psychologue_list(request):
    search_query = request.GET.get('q', '')
    selected_specialty = request.GET.get('specialty', '')
    
    # نستخدم PsychologueProfile لأنه المرتبط بالمستخدم (CustomUser) والحجز
    psychologists = PsychologueProfile.objects.filter(
        is_verified=True,
        user__is_active=True,
    ).select_related('user').annotate(
        rating_average=Avg('user__ratings_received__rating'),
        rating_count=Count('user__ratings_received', distinct=True),
    )
    
    if search_query:
        psychologists = psychologists.filter(
            Q(user__first_name__icontains=search_query) | 
            Q(user__last_name__icontains=search_query)
        )
        
    if selected_specialty:
        psychologists = psychologists.filter(specialites__slug=selected_specialty)
        
    return render(request, 'pages/psychologists.html', { # أو psychologue_list.html حسب اسم قالبك
        'psychologists': psychologists.distinct(),
        'search_query': search_query,
        'selected_specialty': selected_specialty,
        'specialties': Specialite.objects.all().order_by('ordre'),
    })

# 2. لوحة تحكم المريض (تعرض المواعيد وزر الدفع)
@login_required
def patient_dashboard(request):
    if request.user.user_type == 'psychologue':
        return redirect('accounts:psychologue_dashboard')
    if request.user.user_type != 'patient':
        return redirect('home')
    return redirect('accounts:patient_dashboard')

# 3. لوحة تحكم الأخصائي (تعرض المواعيد وزر القبول)
@login_required
def psychologue_dashboard(request):
    if request.user.user_type == 'patient':
        return redirect('accounts:patient_dashboard')
    if request.user.user_type != 'psychologue':
        return redirect('home')
    return redirect('accounts:psychologue_dashboard')

# 4. دالة قبول الأخصائي للموعد
@login_required
def confirm_appointment(request, consultation_id):
    from accounts.views import confirm_appointment as confirm_account_appointment
    return confirm_account_appointment(request, consultation_id)

# 5. صفحة الدفع (تظهر فقط إذا كان الموعد confirmed وغير مدفوع)
@login_required
def payment_page(request, consultation_id):
    return redirect('accounts:payment_page', consultation_id=consultation_id)

# 6. معالجة الدفع (المحاكاة)
@login_required
def process_payment(request, consultation_id):
    from accounts.views import process_payment as process_account_payment
    return process_account_payment(request, consultation_id)

# 7. صفحة نجاح الدفع
@login_required
def payment_success(request, consultation_id):
    return redirect('accounts:payment_success', consultation_id=consultation_id)

SPECIALITES = {

    "depression": {
        "nom": "Dépression",
        "description": "Accompagnement psychologique pour les personnes souffrant de dépression.",
        "approche": "Thérapie cognitive et comportementale (TCC)",
        "symptomes": [
            "Tristesse persistante",
            "Perte d'intérêt",
            "Fatigue importante",
            "Difficultés de concentration"
        ],
        "icone": "fa-cloud-rain"
    },

    "anxiete": {
        "nom": "Anxiété & Angoisse",
        "description": "Pensées persistantes, émotions difficiles à gérer, crises d'angoisse ou phobies du quotidien.",
        "approche": "Thérapies Cognitivo-Comportementales (TCC)",
        "symptomes": [
            "Palpitations et sueurs",
            "Sentiment de panique",
            "Évitement des situations",
            "Tensions musculaires"
        ],
        "icone": "fa-brain"
    },

    "depression-humeur": {
        "nom": "Dépression & Humeur",
        "description": "Perte de motivation, difficultés émotionnelles, découragement profond ou tristesse persistante.",
        "approche": "Thérapie intégrative et TCC",
        "symptomes": [
            "Tristesse persistante",
            "Perte d'intérêt",
            "Fatigue chronique",
            "Troubles du sommeil"
        ],
        "icone": "fa-cloud-rain"
    },

    "stress": {
        "nom": "Stress & Surcharge mentale",
        "description": "Tension permanente, perfectionnisme paralysant, difficulté à déconnecter.",
        "approche": "Biofeedback et techniques de relaxation",
        "symptomes": [
            "Irritabilité",
            "Tensions musculaires",
            "Difficultés de concentration",
            "Fatigue"
        ],
        "icone": "fa-bolt"
    },

    "addiction": {
        "nom": "Addictions & Dépendances",
        "description": "Relations compulsives avec l'alcool, les écrans, le travail ou d'autres comportements.",
        "approche": "Entretien motivationnel et TCC",
        "symptomes": [
            "Perte de contrôle",
            "Craving (envie irrépressible)",
            "Conséquences négatives ignorées",
            "Isolement"
        ],
        "icone": "fa-hand-holding-medical"
    },

    "burn-out": {
        "nom": "Burn-out professionnel",
        "description": "Épuisement profond lié au travail ou à une surcharge de responsabilités.",
        "approche": "Psychologie du travail et TCC",
        "symptomes": [
            "Épuisement émotionnel",
            "Cynisme au travail",
            "Baisse d'efficacité",
            "Détachement"
        ],
        "icone": "fa-battery-empty"
    },

    "relations-couple": {
        "nom": "Relations & Couple",
        "description": "Conflits récurrents, séparations difficiles, distance émotionnelle ou difficultés familiales.",
        "approche": "Théorie de l'attachement et thérapie systémique",
        "symptomes": [
            "Conflits récurrents",
            "Jalousie excessive",
            "Dépendance affective",
            "Communication rompue"
        ],
        "icone": "fa-users"
    },

    "troubles-du-sommeil": {
        "nom": "Sommeil & Insomnie",
        "description": "Réveils nocturnes, ruminations anxieuses, difficultés d'endormissement.",
        "approche": "Protocole TCC-I (Insomnie)",
        "symptomes": [
            "Difficultés d'endormissement",
            "Réveils nocturnes",
            "Sommeil non réparateur",
            "Fatigue diurne"
        ],
        "icone": "fa-moon"
    },

    "estime-de-soi": {
    "nom": "Estime de soi & Confiance",
    "description": "Sentiment d'infériorité, autocritique excessive, difficulté à poser des limites.",
    "approche": "Thérapie des schémas et affirmation de soi",
    "symptomes": [
        "Auto-dévalorisation",
        "Syndrome de l'imposteur",
        "Difficulté à dire non",
        "Peur du jugement"
    ],
    "icone": "fa-shield-alt"
},

    "difficultes-adolescent": {
        "nom": "Difficultés chez l'adolescent",
        "description": "Accompagnement psychologique des adolescents confrontés à des difficultés émotionnelles, scolaires, sociales ou familiales.",
        "approche": "Approche intégrative et thérapie cognitivo-comportementale (TCC)",
        "symptomes": [
            "Changements d'humeur",
            "Difficultés scolaires",
            "Isolement social",
            "Conflits familiaux"
        ],
        "icone": "fa-user-graduate"
    },
        "confiance-en-soi": {
        "nom": "Estime de soi & Confiance",
        "description": "Sentiment d'infériorité, autocritique excessive, difficulté à poser des limites.",
        "approche": "Thérapie des schémas et affirmation de soi",
        "symptomes": [
            "Auto-dévalorisation",
            "Syndrome de l'imposteur",
            "Difficulté à dire non",
            "Peur du jugement"
        ],
        "icone": "fa-shield-alt"
    },

        "phobies": {
        "nom": "Phobies",
        "description": "Accompagnement psychologique des personnes confrontées à des peurs intenses ou persistantes face à certaines situations, objets ou contextes.",
        "approche": "Thérapie cognitivo-comportementale (TCC)",
        "symptomes": [
            "Peur intense",
            "Évitement des situations",
            "Anxiété anticipatoire",
            "Réactions physiques d'anxiété"
        ],
        "icone": "fa-exclamation-circle"
    },

        "toc": {
        "nom": "Troubles obsessionnels compulsifs (TOC)",
        "description": "Accompagnement psychologique des personnes confrontées à des pensées obsessionnelles et à des comportements ou rituels compulsifs.",
        "approche": "Thérapie cognitivo-comportementale (TCC)",
        "symptomes": [
            "Pensées obsessionnelles",
            "Besoin de vérifier ou répéter certaines actions",
            "Anxiété importante",
            "Difficulté à contrôler les pensées ou comportements"
        ],
        "icone": "fa-sync-alt"
    },

        "troubles-alimentaires": {
        "nom": "Troubles alimentaires",
        "description": "Accompagnement psychologique des personnes confrontées à des difficultés liées à l'alimentation, à l'image corporelle ou à la relation avec la nourriture.",
        "approche": "Approche intégrative et thérapie cognitivo-comportementale (TCC)",
        "symptomes": [
            "Relation difficile avec la nourriture",
            "Préoccupation excessive concernant le poids",
            "Insatisfaction corporelle",
            "Comportements alimentaires perturbés"
        ],
        "icone": "fa-utensils"
    },

        "gestion-des-emotions": {
        "nom": "Gestion des émotions",
        "description": "Accompagnement psychologique pour mieux comprendre, exprimer et réguler les émotions au quotidien.",
        "approche": "Approche intégrative et thérapie cognitivo-comportementale (TCC)",
        "symptomes": [
            "Difficulté à gérer les émotions",
            "Réactions émotionnelles intenses",
            "Irritabilité",
            "Difficulté à exprimer ses émotions"
        ],
        "icone": "fa-heart"
    },

        "traumatismes": {
        "nom": "Traumatismes",
        "description": "Accompagnement psychologique des personnes confrontées aux conséquences émotionnelles de situations traumatiques ou d'événements difficiles.",
        "approche": "Approche intégrative et thérapie cognitivo-comportementale (TCC)",
        "symptomes": [
            "Souvenirs ou pensées intrusives",
            "Anxiété et hypervigilance",
            "Évitement de certaines situations",
            "Difficultés émotionnelles persistantes"
        ],
        "icone": "fa-shield-alt"
    },

        "gestion-de-la-colere": {
        "nom": "Gestion de la colère",
        "description": "Accompagnement psychologique pour mieux comprendre, exprimer et réguler la colère de manière constructive.",
        "approche": "Approche intégrative et thérapie cognitivo-comportementale (TCC)",
        "symptomes": [
            "Irritabilité fréquente",
            "Réactions de colère intenses",
            "Difficulté à contrôler ses réactions",
            "Tensions et frustrations persistantes"
        ],
        "icone": "fa-fire"
    },

        "solitude": {
        "nom": "Solitude & Isolement",
        "description": "Accompagnement psychologique des personnes confrontées à un sentiment de solitude, d'isolement ou de déconnexion sociale.",
        "approche": "Approche intégrative et thérapie cognitivo-comportementale (TCC)",
        "symptomes": [
            "Sentiment de solitude",
            "Isolement social",
            "Difficulté à créer ou maintenir des relations",
            "Sentiment de déconnexion"
        ],
        "icone": "fa-user"
    },

    "deuil": {
        "nom": gettext_lazy("Deuil et séparation"),
        "description": gettext_lazy(
            "Un accompagnement pour traverser la perte d'un proche, une séparation "
            "ou une transition de vie, à votre rythme."
        ),
        "approche": gettext_lazy("Accompagnement psychologique centré sur le deuil"),
        "symptomes": [
            gettext_lazy("Tristesse persistante après une perte"),
            gettext_lazy("Difficulté à accepter un décès ou une séparation"),
            gettext_lazy("Sentiment d'isolement"),
            gettext_lazy("Difficulté à reprendre les activités quotidiennes"),
        ],
        "icone": "fa-heart-broken",
    },

    "difficultes-relationnelles": {
        "nom": gettext_lazy("Difficultés relationnelles"),
        "description": gettext_lazy(
            "Un accompagnement pour mieux comprendre les conflits, les difficultés "
            "de communication et les schémas relationnels répétitifs."
        ),
        "approche": gettext_lazy("Approches relationnelle et systémique"),
        "symptomes": [
            gettext_lazy("Conflits récurrents"),
            gettext_lazy("Difficultés à communiquer ou à poser des limites"),
            gettext_lazy("Sentiment de distance ou d'incompréhension"),
            gettext_lazy("Répétition de relations difficiles"),
        ],
        "icone": "fa-people-arrows",
    },

    "difficultes-familiales": {
        "nom": gettext_lazy("Difficultés familiales"),
        "description": gettext_lazy(
            "Un accompagnement pour faire face aux tensions familiales, aux conflits "
            "entre générations ou aux difficultés liées à la parentalité."
        ),
        "approche": gettext_lazy("Approche systémique et familiale"),
        "symptomes": [
            gettext_lazy("Conflits répétés au sein de la famille"),
            gettext_lazy("Difficultés de communication entre générations"),
            gettext_lazy("Tensions liées à la parentalité"),
            gettext_lazy("Sentiment de ne pas trouver sa place dans la famille"),
        ],
        "icone": "fa-house-user",
    },

    "soutien-general": {
    "nom": "Soutien général",
    "description": "Accompagnement psychologique pour les personnes qui souhaitent parler de leurs difficultés, de leurs émotions ou de leur situation personnelle dans un cadre bienveillant.",
    "approche": "Approche intégrative",
    "symptomes": [
        "Difficultés émotionnelles",
        "Besoin d'écoute",
        "Période difficile",
        "Questionnements personnels"
    ],
    "icone": "fa-comments"
},
}


def specialite_detail(request, slug):
    print("SLUG REÇU :", slug)
    print("SLUGS DISPONIBLES :", list(SPECIALITES.keys()))

    specialite_data = SPECIALITES.get(slug)

    if not specialite_data:
        raise Http404("Cette spécialité n'existe pas.")

    return render(
        request,
        'pages/specialite_detail.html',
        {'specialite': specialite_data}
    )


def login_view(request):
    if request.user.is_authenticated:
        return redirect('accounts:patient_dashboard')
    
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        try:
            user = User.objects.get(email=email)
            user_auth = authenticate(request, username=user.username, password=password)
            
            if user_auth is not None:
                login(request, user_auth)
                messages.success(request, 'Connexion réussie !')
                
                if hasattr(user, 'user_type'):
                    if user.user_type == 'psychologue':
                        return redirect('accounts:psychologue_dashboard')
                    else:
                        return redirect('accounts:patient_dashboard')
                return redirect('home')
            else:
                messages.error(request, 'Email ou mot de passe incorrect.')
        except User.DoesNotExist:
            messages.error(request, 'Aucun compte trouvé avec cet email.')
    
    return render(request, 'pages/login.html')



def register_view(request):
    if request.user.is_authenticated:
        return redirect('accounts:patient_dashboard')
    
    if request.method == 'POST':
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        email = request.POST.get('email')
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')
        
        if password1 != password2:
            messages.error(request, 'Les mots de passe ne correspondent pas.')
            return render(request, 'pages/register.html')
        
        if len(password1) < 8:
            messages.error(request, 'Le mot de passe doit contenir au moins 8 caractères.')
            return render(request, 'pages/register.html')
        
        if User.objects.filter(email=email).exists():
            messages.error(request, 'Un compte existe déjà avec cet email.')
            return render(request, 'pages/register.html')
        
        user = User.objects.create_user(
            username=email,
            email=email,
            password=password1,
            first_name=first_name,
            last_name=last_name
        )
        
        login(request, user)
        messages.success(request, 'Compte créé avec succès ! Bienvenue sur MindWell.')
        return redirect('accounts:patient_dashboard')
    
    return render(request, 'pages/register.html')



def logout_view(request):
    logout(request)
    messages.success(request, 'Vous avez été déconnecté avec succès.')
    return redirect('home')


def home(request):
    featured_psychologists = PsychologueProfile.objects.filter(
        is_verified=True,
        user__is_active=True,
    ).select_related('user').annotate(
        rating_average=Avg('user__ratings_received__rating'),
        rating_count=Count('user__ratings_received', distinct=True),
    ).order_by('-rating_count', 'user__last_name')[:3]
    return render(
        request,
        'pages/home.html',
        {'featured_psychologists': featured_psychologists},
    )

def comment_ca_marche(request):
    return render(request, 'pages/comment_ca_marche.html')

@login_required
@user_passes_test(lambda user: user.is_superuser)
def admin_dashboard(request):
    from admin_panel.views import dashboard
    return dashboard(request)

def specialties(request):
    return render(request, 'pages/specialties.html')

def about(request):
    return render(request, 'pages/about.html')

def ethics(request):
    return render(request, 'pages/ethics.html')

def faq(request):
    return render(request, 'pages/faq.html')

def se_connecter(request):
    return redirect('accounts:login')

def register_patient(request):
    return redirect('accounts:register_patient')

def accueil(request):
    return redirect('home')

def tarifs(request):
    return render(request, 'pages/tarifs.html')

def carriere(request):
    return render(request, 'pages/carriere.html')

def presse(request):
    return render(request, 'pages/press.html')

def blog(request):
    return render(request, 'pages/blog.html')

def contact(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, gettext_lazy('Votre message a été envoyé.'))
            return redirect('contact')
        messages.error(request, gettext_lazy('Veuillez corriger les erreurs du formulaire.'))
    else:
        form = ContactForm()
    return render(request, 'pages/contact.html', {'form': form})

def urgence(request):
    return render(request, 'pages/urgence.html')

def aide(request):
    return render(request, 'pages/aide.html')

def mentions_legales(request):
    return render(request, 'pages/mentions_legales.html')

def cgv(request):
    return render(request, 'pages/cgv.html')

def cookies(request):
    return render(request, 'pages/cookies.html')

def confidentialite(request):
    return render(request, 'pages/confidentialite.html')

def ai_analyze_consultation(request):
    if not request.user.is_authenticated:
        return redirect('accounts:login')
    if request.user.user_type != 'psychologue':
        return redirect('home')
    return redirect('ai_service:ai_summaries_dashboard')




def nos_specialistes(request):
    psychologists = PsychologueProfile.objects.filter(
        is_verified=True,
        user__is_active=True,
    ).select_related('user').annotate(
        rating_average=Avg('user__ratings_received__rating'),
        rating_count=Count('user__ratings_received', distinct=True),
    )
    return render(request, 'pages/nos_specialistes.html', {'psychologists': psychologists})

def psychologists(request):
    psychologists_list = PsychologueProfile.objects.filter(
        is_verified=True,
        user__is_active=True,
    ).select_related('user').annotate(
        rating_average=Avg('user__ratings_received__rating'),
        rating_count=Count('user__ratings_received', distinct=True),
    ).order_by('-rating_count', 'user__last_name')
    return render(request, 'pages/psychologists.html', {'psychologists': psychologists_list})

def psychologist_detail(request, psychologist_id):
    print(f"Fetching profile ID: {psychologist_id}")
    psychologist = get_object_or_404(PsychologueProfile, pk=psychologist_id, is_verified=True)
    print(f"Got PsychologueProfile pk={psychologist.pk}, user_id={psychologist.user_id}")
    return render(request, 'pages/psychologist_detail.html', {'psychologist': psychologist})

@login_required
def booking(request, psychologist_id):
    return redirect(
        'accounts:book_consultation',
        psychologue_id=psychologist_id,
    )


def confirm_booking(request):
    return redirect('accounts:trouver_psychologue')


@login_required
def patient_file(request, patient_id):
    return redirect('ai_service:patient_file', patient_id=patient_id)


from django.shortcuts import render


def blog(request):
    return render(request, "pages/blog.html")


def article_sante_mentale(request):
    return render(request, "pages/articles/sante-mentale.html")


def article_stress(request):
    return render(request, "pages/articles/stress.html")


def article_psychologue(request):
    return render(request, "pages/articles/psychologue.html")


def article_anxiete(request):
    return render(request, "pages/articles/anxiete.html")


def article_teleconsultation(request):
    return render(request, "pages/articles/teleconsultation.html")


def article_bien_etre(request):
    return render(request, "pages/articles/bien-etre.html")