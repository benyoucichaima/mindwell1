import json
import logging
from datetime import datetime
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, F, Max, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from .services import (
    analyze_session_sentiment,
    analyze_session_full,
    analyze_consultation,
    generate_evolution_report,
    generate_session_summary,
)
from .models import (
    SessionSummary,
    EvolutionReport,
    StressAssessmentResult,
    SupportConversation,
    SupportMessage,
)
from accounts.models import CustomUser
from consultations.models import Consultation

logger = logging.getLogger(__name__)
MAX_ANALYSIS_TEXT_LENGTH = 20000
MAX_SUPPORT_MESSAGE_LENGTH = 2000

STRESS_ASSESSMENT_CONFIG = {
    "fr": {
        "page": {
            "title": "Évaluation du stress - PSS-10 et DASS-21",
            "intro": "Deux questionnaires complémentaires pour mieux comprendre votre stress.",
            "disclaimer_title": "À noter :",
            "disclaimer": "Ces questionnaires sont des outils d'évaluation et de dépistage. Ils ne permettent pas d'établir un diagnostic médical. Les résultats doivent être interprétés avec prudence et peuvent être discutés avec un psychologue qualifié.",
            "language_label": "Langue",
            "progress": "Progression",
            "progress_aria": "Progression du questionnaire",
            "progress_count": "{answered} sur {total}",
            "submit": "Voir mes résultats",
            "home": "Retour à l'accueil",
            "history": "Vos résultats précédents",
            "visitor_note": "Si vous êtes connecté, votre résultat est enregistré dans votre compte pour suivre son évolution. Les résultats des visiteurs ne sont pas conservés.",
            "error_all": "Veuillez répondre à toutes les questions avant d'afficher le résultat.",
            "back_assessments": "Retour aux évaluations",
            "questions_badge": "{count} questions",
            "start": "Commencer l'évaluation",
            "pss10_card_title": "PSS-10 — Évaluation du stress perçu",
            "pss10_card_desc": "Mesure votre niveau de stress perçu au cours du dernier mois à travers 10 questions.",
            "dass21_card_title": "DASS-21 — Évaluation psychologique",
            "dass21_card_desc": "Évalue trois dimensions — dépression, anxiété et stress — à travers 21 questions.",
        },
        "pss10": {
            "name": "PSS-10 (Échelle de stress perçu)",
            "instruction": "Les questions suivantes portent sur vos sentiments et vos expériences durant le mois dernier. Pour chaque question, choisissez la réponse qui correspond le mieux à votre expérience.",
            "period": "Dernier mois",
            "questions": [
                "Au cours du dernier mois, combien de fois avez-vous été contrarié(e) par un événement inattendu ?",
                "Au cours du dernier mois, combien de fois avez-vous eu le sentiment de ne pas pouvoir contrôler les choses importantes dans votre vie ?",
                "Au cours du dernier mois, combien de fois vous êtes-vous senti(e) nerveux(se) ou stressé(e) ?",
                "Au cours du dernier mois, combien de fois avez-vous eu confiance en votre capacité à gérer vos problèmes personnels ?",
                "Au cours du dernier mois, combien de fois avez-vous eu le sentiment que les choses se passaient comme vous le souhaitiez ?",
                "Au cours du dernier mois, combien de fois avez-vous pensé que vous ne pouviez pas faire face à toutes les choses que vous deviez accomplir ?",
                "Au cours du dernier mois, combien de fois avez-vous été capable de contrôler les irritations dans votre vie ?",
                "Au cours du dernier mois, combien de fois avez-vous eu le sentiment de maîtriser la situation ?",
                "Au cours du dernier mois, combien de fois avez-vous été irrité(e) par des événements qui échappaient à votre contrôle ?",
                "Au cours du dernier mois, combien de fois avez-vous eu le sentiment que les difficultés s'accumulaient à un point tel que vous ne pouviez pas les surmonter ?",
            ],
            "answers": [
                {"value": 0, "label": "Jamais"},
                {"value": 1, "label": "Presque jamais"},
                {"value": 2, "label": "Parfois"},
                {"value": 3, "label": "Assez souvent"},
                {"value": 4, "label": "Très souvent"},
            ],
            "reverse": [4, 5, 7, 8],  # 1-indexed
        },
        "dass21": {
            "name": "DASS-21 (Dépression, Anxiété, Stress)",
            "instruction": "Veuillez lire chaque affirmation et indiquer dans quelle mesure elle s'est appliquée à vous au cours de la semaine dernière. Il n'existe pas de bonnes ou de mauvaises réponses.",
            "period": "Semaine dernière",
            "questions": [
                "J'ai eu du mal à me détendre.",
                "J'ai eu la bouche sèche.",
                "Je n'ai ressenti aucune émotion positive.",
                "J'ai éprouvé des difficultés à respirer sans avoir fait d'effort physique (par exemple, respiration excessivement rapide ou essoufflement).",
                "J'ai eu du mal à prendre l'initiative de faire des choses.",
                "J'ai eu tendance à réagir de manière excessive aux situations.",
                "J'ai ressenti des tremblements (par exemple, au niveau des mains).",
                "J'ai senti que je dépensais beaucoup d'énergie nerveuse.",
                "J'ai eu peur de me retrouver dans des situations où je pourrais paniquer ou me ridiculiser.",
                "J'ai eu l'impression de n'avoir rien à attendre de l'avenir.",
                "Je me suis senti(e) facilement agité(e).",
                "J'ai eu du mal à me détendre.",
                "Je me suis senti(e) triste et déprimé(e).",
                "Je n'ai pas supporté ce qui m'empêchait de poursuivre ce que je faisais.",
                "J'ai eu l'impression d'être sur le point de paniquer.",
                "Je n'ai pas réussi à m'enthousiasmer pour quoi que ce soit.",
                "J'ai eu le sentiment de ne pas valoir grand-chose en tant que personne.",
                "Je me suis senti(e) irritable.",
                "J'ai remarqué les battements de mon cœur sans avoir fait d'effort physique.",
                "J'ai ressenti de la peur sans raison apparente.",
                "J'ai eu le sentiment que la vie n'avait aucun sens.",
            ],
            "answers": [
                {"value": 0, "label": "Ne s'applique pas du tout à moi."},
                {
                    "value": 1,
                    "label": "S'applique à moi dans une certaine mesure ou parfois.",
                },
                {
                    "value": 2,
                    "label": "S'applique assez souvent à moi ou pendant une bonne partie du temps.",
                },
                {
                    "value": 3,
                    "label": "S'applique beaucoup à moi ou la plupart du temps.",
                },
            ],
            "scales": {
                "depression": [3, 5, 10, 13, 16, 17, 21],
                "anxiety": [2, 4, 7, 9, 15, 19, 20],
                "stress": [1, 6, 8, 11, 12, 14, 18],
            },
        },
        "result": {
            "title": "Résultats de votre évaluation",
            "pss10_title": "Score PSS-10",
            "pss10_explanation": "Le PSS-10 mesure la perception du stress au cours du dernier mois.",
            "dass21_title": "DASS-21 - Dépression, Anxiété, Stress",
            "disclaimer": "Ces questionnaires sont des outils d'évaluation et de dépistage. Ils ne permettent pas d'établir un diagnostic médical. Les résultats doivent être interprétés avec prudence et peuvent être discutés avec un psychologue qualifié.",
            "recommendation": "Si vous éprouvez une détresse importante, nous vous recommandons de consulter un psychologue qualifié.",
            "retake": "Refaire l'évaluation",
            "home": "Accueil",
            "history": "Historique",
            "dimensions": {
                "depression": "Dépression",
                "anxiety": "Anxiété",
                "stress": "Stress",
            },
            "severity": {
                "depression": [
                    (9, "Normal"),
                    (13, "Léger"),
                    (20, "Modéré"),
                    (27, "Sévère"),
                    (float("inf"), "Extrêmement sévère"),
                ],
                "anxiety": [
                    (7, "Normal"),
                    (9, "Léger"),
                    (14, "Modéré"),
                    (19, "Sévère"),
                    (float("inf"), "Extrêmement sévère"),
                ],
                "stress": [
                    (14, "Normal"),
                    (18, "Léger"),
                    (25, "Modéré"),
                    (33, "Sévère"),
                    (float("inf"), "Extrêmement sévère"),
                ],
            },
        },
    },
    "en": {
        "page": {
            "title": "Stress Assessment - PSS-10 and DASS-21",
            "intro": "Two complementary questionnaires to better understand your stress.",
            "disclaimer_title": "Note:",
            "disclaimer": "These questionnaires are screening and assessment tools. They do not provide a medical diagnosis. Results should be interpreted with caution and may be discussed with a qualified psychologist.",
            "language_label": "Language",
            "progress": "Progress",
            "progress_aria": "Questionnaire completion progress",
            "progress_count": "{answered} of {total}",
            "submit": "View my results",
            "home": "Back to home",
            "history": "Your previous results",
            "visitor_note": "If you are signed in, your result is saved to your account to track changes over time. Visitor results are not saved.",
            "error_all": "Please answer all questions before viewing the results.",
            "back_assessments": "Back to assessments",
            "questions_badge": "{count} questions",
            "start": "Start the assessment",
            "pss10_card_title": "PSS-10 — Perceived Stress Assessment",
            "pss10_card_desc": "Measures your perceived stress over the last month through 10 questions.",
            "dass21_card_title": "DASS-21 — Psychological Assessment",
            "dass21_card_desc": "Assesses three dimensions — depression, anxiety and stress — through 21 questions.",
        },
        "pss10": {
            "name": "PSS-10 (Perceived Stress Scale)",
            "instruction": "The questions in this scale ask you about your feelings and thoughts during the last month. In each case, please indicate how often you felt or thought a certain way.",
            "period": "Last month",
            "questions": [
                "In the last month, how often have you been upset because of something that happened unexpectedly?",
                "In the last month, how often have you felt that you were unable to control the important things in your life?",
                "In the last month, how often have you felt nervous and stressed?",
                "In the last month, how often have you felt confident about your ability to handle your personal problems?",
                "In the last month, how often have you felt that things were going your way?",
                "In the last month, how often have you found that you could not cope with all the things that you had to do?",
                "In the last month, how often have you been able to control irritations in your life?",
                "In the last month, how often have you felt that you were on top of things?",
                "In the last month, how often have you been angered because of things that were outside of your control?",
                "In the last month, how often have you felt difficulties were piling up so high that you could not overcome them?",
            ],
            "answers": [
                {"value": 0, "label": "Never"},
                {"value": 1, "label": "Almost never"},
                {"value": 2, "label": "Sometimes"},
                {"value": 3, "label": "Fairly often"},
                {"value": 4, "label": "Very often"},
            ],
            "reverse": [4, 5, 7, 8],
        },
        "dass21": {
            "name": "DASS-21 (Depression, Anxiety, Stress Scales)",
            "instruction": "Please read each statement and circle a number 0, 1, 2 or 3 which indicates how much the statement applied to you over the past week. There are no right or wrong answers.",
            "period": "Past week",
            "questions": [
                "I found it hard to wind down.",
                "I was aware of dryness of my mouth.",
                "I couldn't seem to experience any positive feeling at all.",
                "I experienced breathing difficulty (e.g. excessively rapid breathing, breathlessness in the absence of physical exertion).",
                "I found it difficult to work up the initiative to do things.",
                "I tended to over-react to situations.",
                "I experienced trembling (e.g. in the hands).",
                "I felt that I was using a lot of nervous energy.",
                "I was worried about situations in which I might panic and make a fool of myself.",
                "I felt that I had nothing to look forward to.",
                "I found myself getting agitated.",
                "I found it difficult to relax.",
                "I felt down-hearted and blue.",
                "I was intolerant of anything that kept me from getting on with what I was doing.",
                "I felt I was close to panic.",
                "I was unable to become enthusiastic about anything.",
                "I felt I wasn't worth much as a person.",
                "I felt that I was rather touchy.",
                "I was aware of the action of my heart in the absence of physical exertion (e.g. sense of heart rate increase, heart missing a beat).",
                "I felt scared without any good reason.",
                "I felt that life was meaningless.",
            ],
            "answers": [
                {"value": 0, "label": "Did not apply to me at all"},
                {
                    "value": 1,
                    "label": "Applied to me to some degree, or some of the time",
                },
                {
                    "value": 2,
                    "label": "Applied to me to a considerable degree, or a good part of time",
                },
                {"value": 3, "label": "Applied to me very much, or most of the time"},
            ],
            "scales": {
                "depression": [3, 5, 10, 13, 16, 17, 21],
                "anxiety": [2, 4, 7, 9, 15, 19, 20],
                "stress": [1, 6, 8, 11, 12, 14, 18],
            },
        },
        "result": {
            "title": "Your Assessment Results",
            "pss10_title": "PSS-10 Score",
            "pss10_explanation": "The PSS-10 measures perceived stress during the last month.",
            "dass21_title": "DASS-21 - Depression, Anxiety, Stress",
            "disclaimer": "These questionnaires are screening and assessment tools. They do not provide a medical diagnosis. Results should be interpreted with caution and may be discussed with a qualified psychologist.",
            "recommendation": "If you are experiencing significant distress, we recommend consulting a qualified psychologist.",
            "retake": "Retake Assessment",
            "home": "Home",
            "history": "History",
            "dimensions": {
                "depression": "Depression",
                "anxiety": "Anxiety",
                "stress": "Stress",
            },
            "severity": {
                "depression": [
                    (9, "Normal"),
                    (13, "Mild"),
                    (20, "Moderate"),
                    (27, "Severe"),
                    (float("inf"), "Extremely Severe"),
                ],
                "anxiety": [
                    (7, "Normal"),
                    (9, "Mild"),
                    (14, "Moderate"),
                    (19, "Severe"),
                    (float("inf"), "Extremely Severe"),
                ],
                "stress": [
                    (14, "Normal"),
                    (18, "Mild"),
                    (25, "Moderate"),
                    (33, "Severe"),
                    (float("inf"), "Extremely Severe"),
                ],
            },
        },
    },
    "ar": {
        "page": {
            "title": "تقييم الإجهاد - مقياس PSS-10 و DASS-21",
            "intro": "استبيانان مكملان لفهم مستوى الإجهاد لديك بشكل أفضل.",
            "disclaimer_title": "ملاحظة:",
            "disclaimer": "هذه الاستبيانات هي أدوات تقييم وفحص، ولا تسمح بوضع تشخيص طبي. يجب تفسير النتائج بحذر ويمكن مناقشتها مع أخصائي نفسي مؤهل.",
            "language_label": "اللغة",
            "progress": "التقدم",
            "progress_aria": "نسبة إكمال الاستبيان",
            "progress_count": "{answered} من {total}",
            "submit": "عرض نتائجي",
            "home": "العودة للرئيسية",
            "history": "نتائجك السابقة",
            "visitor_note": "إذا كنت مسجلاً الدخول، تُحفظ النتيجة في حسابك لمتابعة تطورها. لا تُحفظ نتائج الزوار.",
            "error_all": "يرجى الإجابة على جميع الأسئلة قبل عرض النتائج.",
            "back_assessments": "العودة إلى التقييمات",
            "questions_badge": "{count} أسئلة",
            "start": "ابدأ التقييم",
            "pss10_card_title": "PSS-10 — تقييم الإجهاد المتصور",
            "pss10_card_desc": "يقيس مستوى الإجهاد المتصور لديك خلال الشهر الماضي عبر 10 أسئلة.",
            "dass21_card_title": "DASS-21 — التقييم النفسي",
            "dass21_card_desc": "يقيّم ثلاثة أبعاد — الاكتئاب والقلق والإجهاد — عبر 21 سؤالاً.",
        },
        "pss10": {
            "name": "PSS-10 (مقياس الإجهاد المتصور)",
            "instruction": "الأسئلة التالية تتعلق بمشاعرك وتجاربك خلال الشهر الماضي. بالنسبة لكل سؤال، اختر الإجابة التي تتوافق أكثر مع تجربتك.",
            "period": "الشهر الماضي",
            "questions": [
                "خلال الشهر الماضي، كم مرة شعرت بالضيق بسبب حدث غير متوقع؟",
                "خلال الشهر الماضي، كم مرة شعرت بعدم قدرتك على السيطرة على الأمور الهامة في حياتك؟",
                "خلال الشهر الماضي، كم مرة شعرت بالتوتر أو القلق؟",
                "خلال الشهر الماضي، كم مرة كنت واثقًا(ة) من قدرتك على التعامل مع مشاكلك الشخصية؟",
                "خلال الشهر الماضي، كم مرة شعرت أن الأمور تسير كما تريد؟",
                "خلال الشهر الماضي، كم مرة شعرت أنك لا تستطيع التعامل مع جميع ما عليك القيام به؟",
                "خلال الشهر الماضي، كم مرة تمكنت من السيطرة على الانزعاجات في حياتك؟",
                "خلال الشهر الماضي، كم مرة شعرت أنك تسيطر على الموقف؟",
                "خلال الشهر الماضي، كم مرة شعرت بالانزعاج بسبب أحداث خارجة عن سيطرتك؟",
                "خلال الشهر الماضي، كم مرة شعرت أن الصعوبات تتراكم لدرجة لا يمكنك التغلب عليها؟",
            ],
            "answers": [
                {"value": 0, "label": "أبداً"},
                {"value": 1, "label": "تقريباً أبداً"},
                {"value": 2, "label": "أحياناً"},
                {"value": 3, "label": "غالباً جداً"},
                {"value": 4, "label": "دائماً تقريباً"},
            ],
            "reverse": [4, 5, 7, 8],
        },
        "dass21": {
            "name": "DASS-21 (مقياس الاكتئاب والقلق والإجهاد)",
            "instruction": "يرجى قراءة كل عبارة والإشارة إلى مدى تطبيقها عليك خلال الأسبوع الماضي. لا توجد إجابات صحيحة أو خاطئة.",
            "period": "الأسبوع الماضي",
            "questions": [
                "وجدت صعوبة في الاسترخاء.",
                "لاحظت جفافاً في فمي.",
                "لم أتمكن من الشعور بأي مشاعر إيجابية على الإطلاق.",
                "عانيت من صعوبات في التنفس دون بذل مجهود بدني (مثال: تنفس سريع جداً أو ضيق في التنفس).",
                "وجدت صعوبة في البدء في القيام بالأشياء.",
                "كنت أميل إلى المبالغة في رد الفعل تجاه المواقف.",
                "عانيت من رعشة (مثال: في اليدين).",
                "شعرت أني أستخدم الكثير من الطاقة العصبية.",
                "خفت من الوقوع في مواقف قد أصاب فيها بالذعر أو أُضحك عليّ.",
                "شعرت أن ليس لدي ما أتطلع إليه في المستقبل.",
                "وجدت نفسي سريع الانفعال.",
                "وجدت صعوبة في الاسترخاء.",
                "شعرت بالحزن والكآبة.",
                "لم أتحمل الأشياء التي تمنعني من مواصلة ما أقوم به.",
                "شعرت أني على وشك الذعر.",
                "لم أتمكن من الانخراط أو الاستمتاع بأي شيء.",
                "شعرت أنني لا قيمة لي كإنسان.",
                "شعرت بالتهيج بسهولة.",
                "لاحظت ضربات قلبي دون بذل مجهود بدني.",
                "شعرت بالخوف دون سبب واضح.",
                "شعرت أن الحياة لا معنى لها.",
            ],
            "answers": [
                {"value": 0, "label": "لا ينطبق عليّ مطلقاً"},
                {"value": 1, "label": "ينطبق عليّ إلى حد ما أو أحياناً"},
                {"value": 2, "label": "ينطبق عليّ كثيراً أو معظم الوقت"},
                {"value": 3, "label": "ينطبق عليّ جداً أو دائمًا تقريبًا"},
            ],
            "scales": {
                "depression": [3, 5, 10, 13, 16, 17, 21],
                "anxiety": [2, 4, 7, 9, 15, 19, 20],
                "stress": [1, 6, 8, 11, 12, 14, 18],
            },
        },
        "result": {
            "title": "نتائج التقييم",
            "pss10_title": "نتيجة مقياس PSS-10",
            "pss10_explanation": "يقيس مقياس PSS-10 مستوى الإجهاد المتصور خلال الشهر الماضي.",
            "dass21_title": "DASS-21 - الاكتئاب والقلق والإجهاد",
            "disclaimer": "هذه الاستبيانات هي أدوات تقييم وفحص، ولا تسمح بوضع تشخيص طبي. يجب تفسير النتائج بحذر ويمكن مناقشتها مع أخصائي نفسي مؤهل.",
            "recommendation": "إذا كنت تعاني من ضيق كبير، نوصي بالتحدث مع أخصائي نفسي مؤهل.",
            "retake": "إعادة التقييم",
            "home": "الرئيسية",
            "history": "السجل",
            "dimensions": {
                "depression": "الاكتئاب",
                "anxiety": "القلق",
                "stress": "الإجهاد",
            },
            "severity": {
                "depression": [
                    (9, "طبيعي"),
                    (13, "خفيف"),
                    (20, "متوسط"),
                    (27, "شديد"),
                    (float("inf"), "شديد للغاية"),
                ],
                "anxiety": [
                    (7, "طبيعي"),
                    (9, "خفيف"),
                    (14, "متوسط"),
                    (19, "شديد"),
                    (float("inf"), "شديد للغاية"),
                ],
                "stress": [
                    (14, "طبيعي"),
                    (18, "خفيف"),
                    (25, "متوسط"),
                    (33, "شديد"),
                    (float("inf"), "شديد للغاية"),
                ],
            },
        },
    },
}


STRESS_LOCALIZED_COPY = {
    "ar": {
        "categories": {
            "physical": {"label": "الجوانب الجسدية"},
            "emotional": {"label": "الجوانب العاطفية"},
            "social": {"label": "الجوانب الاجتماعية"},
            "work": {"label": "العمل أو الدراسة والمسؤوليات"},
        },
        "advice": {
            "low": {
                "label": "منخفض",
                "summary": "تشير إجاباتك إلى ضغط منخفض في الوقت الحالي.",
                "recommendations": ["حافظ على فترات راحة منتظمة ونوم كافٍ."],
            },
            "moderate": {
                "label": "متوسط",
                "summary": "تشير إجاباتك إلى وجود ضغط يستحق الانتباه.",
                "recommendations": ["قسّم المهام إلى خطوات صغيرة."],
            },
            "high": {
                "label": "مرتفع",
                "summary": "تُظهر إجاباتك ضغطاً مرتفعاً قد يؤثر في حياتك اليومية.",
                "recommendations": ["فكر في حجز موعد مع أخصائي نفسي."],
            },
            "severe": {
                "label": "شديد",
                "summary": "تُظهر إجاباتك مستوى مرتفعاً جداً من الضغط.",
                "recommendations": [
                    "اطلب دعماً من أخصائي نفسي أو طبيب في أقرب وقت ممكن."
                ],
            },
        },
        "ui": {
            "language_label": "اللغة",
            "result_title": "نتيجة تقييم الضغط",
            "average": "المتوسط العام:",
            "saved": "حُفظت هذه النتيجة في حسابك لمتابعة التغيّر بمرور الوقت.",
            "not_saved": "لم تُحفظ النتيجة لأنك لم تكن مسجلاً الدخول عند إجراء التقييم.",
            "categories_title": "النتائج حسب الفئة",
            "recommendations_title": "خطوات مقترحة",
            "elevated": "قد يساعدك التحدث مع مختص نفسي في مناقشة ما تمر به.",
            "find_specialist": "البحث عن أخصائي",
            "urgent_help": "معلومات المساعدة العاجلة",
            "result_note": "هذه النتيجة أداة تأمل غير تشخيصية، ولا تحدد وجود اضطراب أو حالة طبية.",
            "retake": "إعادة التقييم",
            "home_link": "الرئيسية",
        },
    },
    "fr": {
        "categories": {
            "physical": {"label": "Aspects physiques"},
            "emotional": {"label": "Aspects émotionnels"},
            "social": {"label": "Aspects sociaux"},
            "work": {"label": "Travail, études et responsabilités"},
        },
        "advice": {
            "low": {
                "label": "Faible",
                "summary": "Vos réponses indiquent un niveau de stress faible actuellement.",
                "recommendations": [
                    "Prévoyez des pauses régulières et veillez à votre sommeil."
                ],
            },
            "moderate": {
                "label": "Modéré",
                "summary": "Vos réponses indiquent un stress qui mérite attention.",
                "recommendations": ["Divisez les tâches en étapes."],
            },
            "high": {
                "label": "Élevé",
                "summary": "Vos réponses indiquent un niveau de stress élevé qui peut affecter votre quotidien.",
                "recommendations": [
                    "Envisagez de prendre rendez-vous avec un psychologue."
                ],
            },
            "severe": {
                "label": "Très élevé",
                "summary": "Vos réponses indiquent un niveau de stress très élevé.",
                "recommendations": [
                    "Demandez dès que possible le soutien d'un psychologue ou d'un médecin."
                ],
            },
        },
        "ui": {
            "language_label": "Langue",
            "result_title": "Résultat de l’auto-évaluation",
            "average": "Moyenne générale :",
            "saved": "Ce résultat a été enregistré dans votre compte pour suivre son évolution.",
            "not_saved": "Ce résultat n’a pas été enregistré, car vous n’étiez pas connecté lors de l’évaluation.",
            "categories_title": "Résultats par catégorie",
            "recommendations_title": "Quelques pistes",
            "elevated": "Un échange avec un psychologue peut vous aider à parler de ce que vous traversez.",
            "find_specialist": "Trouver un psychologue",
            "urgent_help": "Aide et ressources d’urgence",
            "result_note": "Ce résultat est un outil de réflexion non diagnostique. Il ne permet pas d’identifier un trouble ou un problème médical.",
            "retake": "Refaire le bilan",
            "home_link": "Accueil",
        },
    },
    "en": {
        "categories": {
            "physical": {"label": "Physical well-being"},
            "emotional": {"label": "Emotional well-being"},
            "social": {"label": "Social well-being"},
            "work": {"label": "Work, study, and responsibilities"},
        },
        "advice": {
            "low": {
                "label": "Low",
                "summary": "Your answers suggest a low level of stress at this time.",
                "recommendations": ["Take regular breaks and try to get enough sleep."],
            },
            "moderate": {
                "label": "Moderate",
                "summary": "Your answers suggest stress that deserves attention.",
                "recommendations": ["Break tasks into smaller steps."],
            },
            "high": {
                "label": "High",
                "summary": "Your answers suggest a high level of stress that may affect daily life.",
                "recommendations": [
                    "Consider booking an appointment with a psychologist."
                ],
            },
            "severe": {
                "label": "Very high",
                "summary": "Your answers suggest a very high level of stress.",
                "recommendations": [
                    "Seek support from a psychologist or doctor as soon as possible."
                ],
            },
        },
        "ui": {
            "language_label": "Language",
            "result_title": "Stress check-in result",
            "average": "Overall average:",
            "saved": "This result was saved to your account so you can track changes over time.",
            "not_saved": "This result was not saved because you were not signed in when you completed the check-in.",
            "categories_title": "Results by category",
            "recommendations_title": "Suggested next steps",
            "elevated": "Talking with a psychologist may help you discuss what you are going through.",
            "find_specialist": "Find a psychologist",
            "urgent_help": "Urgent help information",
            "result_note": "This result is a non-diagnostic reflection tool. It does not identify a disorder or medical condition.",
            "retake": "Take the check-in again",
            "home_link": "Home",
        },
    },
}

STRESS_LOCALIZED_COPY = {
    "ar": {
        "categories": {
            "physical": {"label": "الجوانب الجسدية"},
            "emotional": {"label": "الجوانب العاطفية"},
            "social": {"label": "الجوانب الاجتماعية"},
            "work": {"label": "العمل أو الدراسة والمسؤوليات"},
        },
        "advice": {
            "low": {
                "label": "منخفض",
                "summary": "تشير إجاباتك إلى ضغط منخفض في الوقت الحالي.",
                "recommendations": ["حافظ على فترات راحة منتظمة ونوم كافٍ."],
            },
            "moderate": {
                "label": "متوسط",
                "summary": "تشير إجاباتك إلى وجود ضغط يستحق الانتباه.",
                "recommendations": ["قسّم المهام إلى خطوات صغيرة."],
            },
            "high": {
                "label": "مرتفع",
                "summary": "تُظهر إجاباتك ضغطاً مرتفعاً قد يؤثر في حياتك اليومية.",
                "recommendations": ["فكر في حجز موعد مع أخصائي نفسي."],
            },
            "severe": {
                "label": "شديد",
                "summary": "تُظهر إجاباتك مستوى مرتفعاً جداً من الضغط.",
                "recommendations": [
                    "اطلب دعماً من أخصائي نفسي أو طبيب في أقرب وقت ممكن."
                ],
            },
        },
        "ui": {
            "language_label": "اللغة",
            "result_title": "نتيجة تقييم الضغط",
            "average": "المتوسط العام:",
            "saved": "حُفظت هذه النتيجة في حسابك لمتابعة التغيّر بمرور الوقت.",
            "not_saved": "لم تُحفظ النتيجة لأنك لم تكن مسجلاً الدخول عند إجراء التقييم.",
            "categories_title": "النتائج حسب الفئة",
            "recommendations_title": "خطوات مقترحة",
            "elevated": "قد يساعدك التحدث مع مختص نفسي في مناقشة ما تمر به.",
            "find_specialist": "البحث عن أخصائي",
            "urgent_help": "معلومات المساعدة العاجلة",
            "result_note": "هذه النتيجة أداة تأمل غير تشخيصية، ولا تحدد وجود اضطراب أو حالة طبية.",
            "retake": "إعادة التقييم",
            "home_link": "الرئيسية",
        },
    },
    "fr": {
        "categories": {
            "physical": {"label": "Aspects physiques"},
            "emotional": {"label": "Aspects émotionnels"},
            "social": {"label": "Aspects sociaux"},
            "work": {"label": "Travail, études et responsabilités"},
        },
        "advice": {
            "low": {
                "label": "Faible",
                "summary": "Vos réponses indiquent un niveau de stress faible actuellement.",
                "recommendations": [
                    "Prévoyez des pauses régulières et veillez à votre sommeil."
                ],
            },
            "moderate": {
                "label": "Modéré",
                "summary": "Vos réponses indiquent un stress qui mérite attention.",
                "recommendations": ["Divisez les tâches en étapes."],
            },
            "high": {
                "label": "Élevé",
                "summary": "Vos réponses indiquent un niveau de stress élevé qui peut affecter votre quotidien.",
                "recommendations": [
                    "Envisagez de prendre rendez-vous avec un psychologue."
                ],
            },
            "severe": {
                "label": "Très élevé",
                "summary": "Vos réponses indiquent un niveau de stress très élevé.",
                "recommendations": [
                    "Demandez dès que possible le soutien d'un psychologue ou d'un médecin."
                ],
            },
        },
        "ui": {
            "language_label": "Langue",
            "result_title": "Résultat de l’auto-évaluation",
            "average": "Moyenne générale :",
            "saved": "Ce résultat a été enregistré dans votre compte pour suivre son évolution.",
            "not_saved": "Ce résultat n’a pas été enregistré, car vous n’étiez pas connecté lors de l’évaluation.",
            "categories_title": "Résultats par catégorie",
            "recommendations_title": "Quelques pistes",
            "elevated": "Un échange avec un psychologue peut vous aider à parler de ce que vous traversez.",
            "find_specialist": "Trouver un psychologue",
            "urgent_help": "Aide et ressources d’urgence",
            "result_note": "Ce résultat est un outil de réflexion non diagnostique. Il ne permet pas d’identifier un trouble ou un problème médical.",
            "retake": "Refaire le bilan",
            "home_link": "Accueil",
        },
    },
    "en": {
        "categories": {
            "physical": {"label": "Physical well-being"},
            "emotional": {"label": "Emotional well-being"},
            "social": {"label": "Social well-being"},
            "work": {"label": "Work, study, and responsibilities"},
        },
        "advice": {
            "low": {
                "label": "Low",
                "summary": "Your answers suggest a low level of stress at this time.",
                "recommendations": ["Take regular breaks and try to get enough sleep."],
            },
            "moderate": {
                "label": "Moderate",
                "summary": "Your answers suggest stress that deserves attention.",
                "recommendations": ["Break tasks into smaller steps."],
            },
            "high": {
                "label": "High",
                "summary": "Your answers suggest a high level of stress that may affect daily life.",
                "recommendations": [
                    "Consider booking an appointment with a psychologist."
                ],
            },
            "severe": {
                "label": "Very high",
                "summary": "Your answers suggest a very high level of stress.",
                "recommendations": [
                    "Seek support from a psychologist or doctor as soon as possible."
                ],
            },
        },
        "ui": {
            "language_label": "Language",
            "result_title": "Stress check-in result",
            "average": "Overall average:",
            "saved": "This result was saved to your account so you can track changes over time.",
            "not_saved": "This result was not saved because you were not signed in when you completed the check-in.",
            "categories_title": "Results by category",
            "recommendations_title": "Suggested next steps",
            "elevated": "Talking with a psychologist may help you discuss what you are going through.",
            "find_specialist": "Find a psychologist",
            "urgent_help": "Urgent help information",
            "result_note": "This result is a non-diagnostic reflection tool. It does not identify a disorder or medical condition.",
            "retake": "Take the check-in again",
            "home_link": "Home",
        },
    },
}


def _stress_language(request):
    language = request.COOKIES.get("stress_assessment_language", "fr").split("-", 1)[0]
    return language if language in STRESS_ASSESSMENT_CONFIG else "fr"


def _stress_page_context(language):
    config = STRESS_ASSESSMENT_CONFIG[language]
    pss10_count = len(config["pss10"]["questions"])
    dass21_count = len(config["dass21"]["questions"])
    total_questions = pss10_count + dass21_count
    badge_template = config["page"].get("questions_badge", "{count}")
    return {
        "language": language,
        "direction": "rtl" if language == "ar" else "ltr",
        "copy": config["page"],
        "pss10": config["pss10"],
        "dass21": config["dass21"],
        "total_questions": total_questions,
        "pss10_count": pss10_count,
        "dass21_count": dass21_count,
        "pss10_card_badge": badge_template.replace("{count}", str(pss10_count)),
        "dass21_card_badge": badge_template.replace("{count}", str(dass21_count)),
        "patient_only": _stress_patient_only_message(language),
    }


def _get_severity(dimension, score, config):
    for threshold, label in config["result"]["severity"][dimension]:
        if score <= threshold:
            return label
    return config["result"]["severity"][dimension][-1][1]


def _score_pss10(answers, config):
    total = 0
    for i in range(1, len(config["pss10"]["questions"]) + 1):
        value = answers[i]
        if i in config["pss10"]["reverse"]:
            value = 4 - value
        total += value
    return total


def _score_dass21(answers, config):
    scales = config["dass21"]["scales"]
    raws = {
        "depression": sum(answers[q] for q in scales["depression"]),
        "anxiety": sum(answers[q] for q in scales["anxiety"]),
        "stress": sum(answers[q] for q in scales["stress"]),
    }
    scores = {}
    for dimension, raw in raws.items():
        score = raw * 2
        scores[dimension] = {
            "raw": raw,
            "score": score,
            "max": 42,
            "severity": _get_severity(dimension, score, config),
        }
    return scores


def _stress_instrument_payload(instrument, answers, config):
    if instrument == "pss10":
        total = _score_pss10(answers, config)
        return {
            "version": 2,
            "assessment_type": "pss10",
            "instruments": {
                "pss10": {
                    "total": total,
                    "max": 40,
                    "period": "previous_month",
                    "answers": [answers[i] for i in range(1, 11)],
                }
            },
        }
    scores = _score_dass21(answers, config)
    return {
        "version": 2,
        "assessment_type": "dass21",
        "instruments": {
            "dass21": {
                "period": "previous_week",
                "depression": scores["depression"],
                "anxiety": scores["anxiety"],
                "stress": scores["stress"],
            }
        },
    }


def _stress_patient_only_message(language):
    if language == "ar":
        return "هذا التقييم مخصص لحسابات المرضى."
    if language == "fr":
        return "Cette évaluation est réservée aux comptes patients."
    return "This assessment is available to patient accounts only."


def _stress_history_item(item):
    category_scores = (
        item.category_scores if isinstance(item.category_scores, dict) else {}
    )
    assessment_type = category_scores.get("assessment_type")
    if assessment_type in ("pss10", "dass21"):
        label = assessment_type.upper()
    elif category_scores.get("version") == 2:
        label = "PSS-10 & DASS-21"
    else:
        label = ""
    return {
        "pk": item.pk,
        "created_at": item.created_at,
        "label": label,
    }


def _stress_result_context(language, category_scores, saved, saved_result):
    config = STRESS_ASSESSMENT_CONFIG[language]
    if isinstance(category_scores, dict):
        instruments = category_scores.get("instruments", {})
        assessment_type = category_scores.get("assessment_type", "")
    else:
        instruments = {}
        assessment_type = ""
    if assessment_type in ("pss10", "dass21"):
        retake_url = reverse("ai_service:stress_assessment_take", args=[assessment_type])
    else:
        retake_url = reverse("ai_service:stress_assessment")
    return {
        "language": language,
        "direction": "rtl" if language == "ar" else "ltr",
        "copy": {
            **config["result"],
            "language_label": config["page"]["language_label"],
        },
        "page_copy": config["page"],
        "instruments": instruments,
        "assessment_type": assessment_type,
        "pss10_result": instruments.get("pss10"),
        "dass21_result": instruments.get("dass21"),
        "saved": saved,
        "saved_result": saved_result,
        "is_new": True,
        "retake_url": retake_url,
    }


def _json_body(request):
    if request.content_type != "application/json":
        return None
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


@login_required
@never_cache
def support_chat(request):
    if request.user.user_type != "patient":
        messages.error(request, "هذه الصفحة مخصصة لحسابات المرضى.")
        return redirect("home")
    conversations = SupportConversation.objects.filter(user=request.user)[:30]
    return render(
        request,
        "ai_service/support_chat.html",
        {"conversations": conversations},
    )


@login_required
@require_POST
def send_support_message(request):
    if request.user.user_type != "patient":
        return JsonResponse({"success": False, "error": "غير مصرح."}, status=403)
    data = _json_body(request)
    if data is None:
        return JsonResponse(
            {"success": False, "error": "يجب إرسال كائن JSON صالح."},
            status=400,
        )
    content = data.get("message")
    if not isinstance(content, str):
        return JsonResponse(
            {"success": False, "error": "اكتب رسالة نصية."},
            status=400,
        )
    content = content.strip()
    if not content or len(content) > MAX_SUPPORT_MESSAGE_LENGTH:
        return JsonResponse(
            {"success": False, "error": "يجب أن تكون الرسالة بين حرف واحد و2000 حرف."},
            status=400,
        )

    conversation_id = data.get("conversation_id")
    if conversation_id is None:
        conversation = SupportConversation.objects.create(user=request.user)
    else:
        if not isinstance(conversation_id, int) or isinstance(conversation_id, bool):
            return JsonResponse(
                {"success": False, "error": "معرّف المحادثة غير صالح."},
                status=400,
            )
        conversation = get_object_or_404(
            SupportConversation,
            pk=conversation_id,
            user=request.user,
        )

    with transaction.atomic():
        SupportMessage.objects.create(
            conversation=conversation,
            role="user",
            content=content,
        )
        if not conversation.title:
            conversation.title = "محادثة جديدة"
        conversation.save(update_fields=["title", "updated_at"])

    return JsonResponse(
        {
            "success": False,
            "conversation_id": conversation.pk,
            "error": (
                "تم حفظ رسالتك في سجلّك الخاص، لكن لم يتم تفعيل خدمة الرد الذكي "
                "بعد. لم تُرسل الرسالة إلى أي مزوّد خارجي."
            ),
            "code": "assistant_unavailable",
        },
        status=503,
    )


@login_required
@never_cache
def support_chat_history(request):
    if request.user.user_type != "patient":
        return JsonResponse({"success": False, "error": "غير مصرح."}, status=403)
    conversations = SupportConversation.objects.filter(user=request.user)[:30]
    return JsonResponse(
        {
            "conversations": [
                {
                    "id": conversation.pk,
                    "title": conversation.title or "محادثة",
                    "updated_at": conversation.updated_at.isoformat(),
                }
                for conversation in conversations
            ]
        }
    )


@login_required
@never_cache
def support_chat_detail(request, conversation_id):
    if request.user.user_type != "patient":
        return JsonResponse({"success": False, "error": "غير مصرح."}, status=403)
    conversation = get_object_or_404(
        SupportConversation,
        pk=conversation_id,
        user=request.user,
    )
    return JsonResponse(
        {
            "id": conversation.pk,
            "messages": [
                {
                    "role": message.role,
                    "content": message.content,
                    "created_at": message.created_at.isoformat(),
                }
                for message in conversation.messages.all()
            ],
        }
    )


@login_required
@require_POST
@never_cache
def delete_support_conversation(request, conversation_id):
    if request.user.user_type != "patient":
        return JsonResponse({"success": False, "error": "غير مصرح."}, status=403)
    conversation = get_object_or_404(
        SupportConversation,
        pk=conversation_id,
        user=request.user,
    )
    conversation.delete()
    return JsonResponse({"success": True})


@login_required
@never_cache
def export_support_conversation(request, conversation_id):
    if request.user.user_type != "patient":
        return JsonResponse({"success": False, "error": "غير مصرح."}, status=403)
    conversation = get_object_or_404(
        SupportConversation,
        pk=conversation_id,
        user=request.user,
    )
    lines = ["# سجل محادثة MindWell", ""]
    for message in conversation.messages.all():
        speaker = "أنت" if message.role == "user" else "المساعد"
        lines.extend(
            [
                f"## {speaker} — {message.created_at:%Y-%m-%d %H:%M}",
                "",
                message.content,
                "",
            ]
        )
    response = HttpResponse(
        "\n".join(lines),
        content_type="text/markdown; charset=utf-8",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="mindwell-conversation-{conversation.pk}.md"'
    )
    return response


@require_http_methods(["GET"])
@never_cache
def stress_assessment(request):
    language = _stress_language(request)
    if (
        request.user.is_authenticated
        and getattr(request.user, "user_type", None) != "patient"
    ):
        messages.error(request, _stress_patient_only_message(language))
        return redirect("home")
    context = _stress_page_context(language)
    history = (
        StressAssessmentResult.objects.filter(user=request.user)[:10]
        if request.user.is_authenticated
        and getattr(request.user, "user_type", None) == "patient"
        else []
    )
    context["history"] = [_stress_history_item(item) for item in history]
    return render(request, "ai_service/stress_assessment.html", context)


@require_http_methods(["GET", "POST"])
@never_cache
def stress_assessment_take(request, instrument):
    if instrument not in ("pss10", "dass21"):
        raise Http404("Unknown assessment instrument.")
    language = _stress_language(request)
    if (
        request.user.is_authenticated
        and getattr(request.user, "user_type", None) != "patient"
    ):
        messages.error(request, _stress_patient_only_message(language))
        return redirect("home")

    config = STRESS_ASSESSMENT_CONFIG[language]
    instrument_config = config[instrument]
    total_questions = len(instrument_config["questions"])
    context = {
        "language": language,
        "direction": "rtl" if language == "ar" else "ltr",
        "instrument": instrument,
        "instrument_name": instrument_config["name"],
        "instruction": instrument_config["instruction"],
        "period": instrument_config["period"],
        "questions": instrument_config["questions"],
        "answers": instrument_config["answers"],
        "total_questions": total_questions,
        "copy": config["page"],
        "patient_only": _stress_patient_only_message(language),
    }
    template = "ai_service/stress_assessment_instrument.html"
    if request.method == "GET":
        return render(request, template, context)

    expected_ids = {f"{instrument}_{i}" for i in range(1, total_questions + 1)}
    if "answers" in request.POST:
        try:
            answers = json.loads(request.POST["answers"])
        except json.JSONDecodeError:
            answers = None
    else:
        answers = {qid: request.POST.get(qid) for qid in expected_ids}

    if not isinstance(answers, dict) or set(answers) != expected_ids:
        context["error"] = config["page"]["error_all"]
        return render(request, template, context, status=400)

    answer_max = 4 if instrument == "pss10" else 3
    parsed = {}
    for i in range(1, total_questions + 1):
        qid = f"{instrument}_{i}"
        value = answers[qid]
        if isinstance(value, str) and value.isdigit():
            value = int(value)
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value not in range(0, answer_max + 1)
        ):
            context["error"] = config["page"]["error_all"]
            return render(request, template, context, status=400)
        parsed[i] = value

    category_scores = _stress_instrument_payload(instrument, parsed, config)

    if (
        request.user.is_authenticated
        and getattr(request.user, "user_type", None) == "patient"
    ):
        saved_result = StressAssessmentResult.objects.create(
            user=request.user,
            score=None,
            level=None,
            category_scores=category_scores,
        )
        return redirect(
            "ai_service:stress_assessment_result",
            result_id=saved_result.pk,
        )

    return render(
        request,
        "ai_service/stress_assessment_result.html",
        _stress_result_context(
            language, category_scores, saved=False, saved_result=None
        ),
    )


@login_required
@never_cache
def stress_assessment_result(request, result_id):
    if getattr(request.user, "user_type", None) != "patient":
        return redirect("home")
    saved_result = get_object_or_404(
        StressAssessmentResult,
        pk=result_id,
        user=request.user,
    )
    language = _stress_language(request)
    config = STRESS_ASSESSMENT_CONFIG[language]
    cat_scores = saved_result.category_scores
    if isinstance(cat_scores, dict) and cat_scores.get("version") == 2:
        return render(
            request,
            "ai_service/stress_assessment_result.html",
            _stress_result_context(
                language, cat_scores, saved=True, saved_result=saved_result
            ),
        )
    # Old format compatibility
    try:
        score = float(saved_result.score) if saved_result.score is not None else 0
    except Exception:
        score = 0
    category_scores_old = cat_scores if isinstance(cat_scores, dict) else {}
    localized = STRESS_LOCALIZED_COPY.get(
        language, STRESS_LOCALIZED_COPY.get("fr", STRESS_LOCALIZED_COPY.get("en", {}))
    )
    if score <= 2:
        level_key = "low"
    elif score <= 3:
        level_key = "moderate"
    elif score <= 4:
        level_key = "high"
    else:
        level_key = "severe"
    advice = localized.get("advice", {}).get(
        level_key, {"label": level_key, "summary": "", "recommendations": []}
    )
    areas_to_watch = (
        sorted(
            (
                {
                    "key": key,
                    "label": localized.get("categories", {})
                    .get(key, {})
                    .get("label", key),
                    "score": value,
                    "percentage": (
                        float(value) * 20 if isinstance(value, (int, float)) else 0
                    ),
                }
                for key, value in category_scores_old.items()
                if key in ("physical", "emotional", "social", "work")
            ),
            key=lambda area: area["score"],
            reverse=True,
        )
        or []
    )
    ui_copy = localized.get("ui", {})
    if isinstance(ui_copy, dict):
        ui_copy = dict(ui_copy)
        if "language_label" not in ui_copy:
            ui_copy["language_label"] = (
                "Langue"
                if language == "fr"
                else ("اللغة" if language == "ar" else "Language")
            )
        if "submit" not in ui_copy:
            ui_copy["submit"] = ui_copy.get("retake", "Voir mes résultats")
        if "home" not in ui_copy:
            ui_copy["home"] = ui_copy.get("home_link", "Accueil")
    return render(
        request,
        "ai_service/stress_assessment_result.html",
        {
            "language": language,
            "direction": "rtl" if language == "ar" else "ltr",
            "copy": ui_copy,
            "page_copy": ui_copy,
            "score": score,
            "level_label": advice.get("label", level_key),
            "summary": advice.get("summary", ""),
            "recommendations": advice.get("recommendations", []),
            "category_results": areas_to_watch,
            "is_elevated": level_key in {"high", "severe"},
            "category_scores": category_scores_old,
            "saved": True,
            "saved_result": saved_result,
            "is_new": False,
            "retake_url": reverse("ai_service:stress_assessment"),
        },
    )


@login_required
@require_POST
def analyze_view(request):
    if request.user.user_type != "psychologue":
        return JsonResponse({"success": False, "error": "Non autorisé."}, status=403)
    if request.content_type != "application/json":
        return JsonResponse(
            {"success": False, "error": "Le contenu doit être au format JSON."},
            status=415,
        )

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"success": False, "error": "JSON invalide."}, status=400)

    if not isinstance(data, dict):
        return JsonResponse(
            {"success": False, "error": "Un objet JSON est requis."}, status=400
        )

    text = data.get("text")
    if not isinstance(text, str):
        return JsonResponse(
            {"success": False, "error": "Le texte doit être une chaîne."}, status=400
        )
    text = text.strip()
    if len(text) < 10:
        return JsonResponse(
            {"success": False, "error": "Le texte est trop court."}, status=400
        )
    if len(text) > MAX_ANALYSIS_TEXT_LENGTH:
        return JsonResponse(
            {"success": False, "error": "Le texte dépasse la limite autorisée."},
            status=413,
        )

    language = data.get("language", "fr")
    if not isinstance(language, str) or language not in ("fr", "ar", "en", "darja"):
        return JsonResponse(
            {"success": False, "error": "Langue non prise en charge."}, status=400
        )

    try:
        result = analyze_consultation(text, language=language)
    except Exception:
        logger.exception("AI consultation analysis request failed.")
        return JsonResponse(
            {
                "success": False,
                "error": "Le service d’analyse est momentanément indisponible.",
            },
            status=503,
        )

    if not isinstance(result, dict) or not result.get("success"):
        return JsonResponse(
            {
                "success": False,
                "error": "Le service d’analyse est momentanément indisponible.",
            },
            status=503,
        )
    return JsonResponse({"success": True, "analysis": result})


@login_required
@never_cache
def ai_summaries_dashboard(request):
    """واجهة ملخصات المرضى للأخصائي"""
    if request.user.user_type != "psychologue":
        messages.error(request, _("Unauthorized access."))
        return redirect("home")

    patients = (
        CustomUser.objects.filter(
            user_type="patient",
            patient_consultations__psychologue=request.user,
        )
        .distinct()
        .annotate(
            consultation_count=Count(
                "patient_consultations",
                filter=Q(patient_consultations__psychologue=request.user),
            ),
            last_consultation=Max(
                "patient_consultations__date",
                filter=Q(patient_consultations__psychologue=request.user),
            ),
        )
        .select_related("patient_profile")
    )

    total_patients = patients.count()
    query = request.GET.get("q", "").strip()[:100]
    sort_by = request.GET.get("sort", "recent")
    if sort_by not in {"recent", "sessions", "alphabetical"}:
        sort_by = "recent"
    if query:
        patients = patients.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(username__icontains=query)
        )

    ordering = {
        "recent": (F("last_consultation").desc(nulls_last=True), "-id"),
        "sessions": (
            "-consultation_count",
            F("last_consultation").desc(nulls_last=True),
            "-id",
        ),
        "alphabetical": ("first_name", "last_name", "username"),
    }[sort_by]
    page_obj = Paginator(patients.order_by(*ordering), 12).get_page(
        request.GET.get("page")
    )

    context = {
        "patients": page_obj.object_list,
        "page_obj": page_obj,
        "query": query,
        "sort_by": sort_by,
        "total_patients": total_patients,
    }
    return render(request, "ai_service/summaries_dashboard.html", context)


@login_required
@require_POST
def generate_session_summary_view(request, consultation_id):
    """Generate a draft session summary for the assigned psychologist."""
    if request.user.user_type != "psychologue":
        return JsonResponse({"error": _("Unauthorized.")}, status=403)

    consultation = get_object_or_404(
        Consultation, id=consultation_id, psychologue=request.user
    )
    result = generate_session_summary(
        consultation_id, custom_text=_extract_custom_text(request)
    )

    if result.get("success"):
        messages.success(
            request,
            _(
                "AI summary draft created. It must be professionally reviewed and is not a diagnosis."
            ),
        )
    else:
        messages.error(
            request,
            _("Unable to create summary draft: {error}").format(
                error=result.get("error")
            ),
        )

    return redirect("ai_service:patient_file", patient_id=consultation.patient.id)


@login_required
@require_POST
def generate_evolution_report_view(request, patient_id):
    """توليد تقرير تطور المريض"""
    if request.user.user_type != "psychologue":
        return JsonResponse({"error": _("Unauthorized.")}, status=403)

    patient = get_object_or_404(
        CustomUser.objects.filter(
            user_type="patient",
            patient_consultations__psychologue=request.user,
        ).distinct(),
        id=patient_id,
    )
    result = generate_evolution_report(patient_id, request.user.id)

    if result.get("success"):
        messages.success(request, _("Progress report generated successfully."))
    else:
        messages.error(
            request,
            _("Generation failed: {error}").format(error=result.get("error")),
        )

    return redirect("ai_service:patient_file", patient_id=patient_id)


@login_required
@never_cache
def patient_file(request, patient_id):
    """ملف المريض مع كل تحليلات الذكاء الاصطناعي"""
    if request.user.user_type != "psychologue":
        messages.error(request, _("Unauthorized access."))
        return redirect("home")

    patient = get_object_or_404(
        CustomUser.objects.filter(
            user_type="patient",
            patient_consultations__psychologue=request.user,
        ).distinct(),
        id=patient_id,
    )

    consultations = (
        Consultation.objects.filter(patient=patient, psychologue=request.user)
        .select_related("ai_session_summary")
        .order_by("-date", "-start_time", "-pk")
    )

    evolution_reports = EvolutionReport.objects.filter(
        patient=patient, psychologue=request.user
    ).order_by("-created_at", "-pk")

    total_sessions = consultations.count()
    report_count = evolution_reports.count()
    last_consultation = consultations.first()
    latest_ai_summary = (
        consultations.filter(ai_session_summary__summary__gt="")
        .values_list("ai_session_summary__summary", flat=True)
        .first()
    )
    latest_report = evolution_reports.first()

    timeline_total = total_sessions + evolution_reports.count()
    timeline_paginator = Paginator(range(timeline_total), 10)
    timeline_page = timeline_paginator.get_page(request.GET.get("timeline_page"))
    page_end = timeline_page.end_index()
    timeline_items = list(consultations[:page_end]) + list(evolution_reports[:page_end])

    def timeline_sort_key(item):
        if isinstance(item, Consultation):
            event_date = datetime.combine(item.date, item.start_time)
            return timezone.make_aware(event_date, timezone.get_current_timezone())
        return item.created_at

    timeline_items.sort(key=timeline_sort_key, reverse=True)
    page_items = timeline_items[timeline_page.start_index() - 1 : page_end]
    timeline_page.object_list = [
        {
            "kind": "consultation" if isinstance(item, Consultation) else "report",
            "record": item,
        }
        for item in page_items
    ]

    summary_query = {
        "q": request.GET.get("return_q", ""),
        "sort": request.GET.get("return_sort", "recent"),
        "page": request.GET.get("return_page", "1"),
    }
    summary_query = {
        key: value
        for key, value in summary_query.items()
        if value and (key != "page" or value.isdigit())
    }
    back_fallback_url = reverse("ai_service:ai_summaries_dashboard")
    if summary_query:
        back_fallback_url = f"{back_fallback_url}?{urlencode(summary_query)}"

    context = {
        "patient": patient,
        "consultations": consultations,
        "evolution_reports": evolution_reports,
        "total_sessions": total_sessions,
        "report_count": report_count,
        "last_consultation": last_consultation,
        "latest_ai_summary": latest_ai_summary,
        "latest_report": latest_report,
        "timeline_page": timeline_page,
        "back_fallback_url": back_fallback_url,
    }
    return render(request, "ai_service/patient_file.html", context)


def _extract_custom_text(request):
    """Read a manual transcript / notes text from a JSON or form POST body.

    Lets the AI analyse audio/video sessions from notes typed by the
    psychologist instead of failing when there are no text messages.
    """
    # Read the raw body first so ``request.POST`` can still be parsed from it
    # (accessing POST first consumes the stream and makes body inaccessible).
    try:
        raw_body = request.body
    except Exception:
        raw_body = b""

    custom_text = request.POST.get("custom_text") or request.POST.get("notes_text")
    if not custom_text and raw_body:
        try:
            data = json.loads(raw_body or b"{}")
        except (ValueError, TypeError):
            data = None
        if isinstance(data, dict):
            custom_text = data.get("custom_text") or data.get("notes_text")
    return (custom_text or "").strip() or None


@login_required
@require_POST
def ai_analyze_keywords(request, consultation_id):

    consultation = get_object_or_404(
        Consultation,
        id=consultation_id,
        psychologue=request.user,
    )

    lang = getattr(request, "LANGUAGE_CODE", None) or "fr"

    SUPPORTED_LANGS = {
        "ar": "darija",
        "ar-fusha": "arabic",
        "fr": "french",
        "en": "english",
    }

    ai_lang = SUPPORTED_LANGS.get(lang, "french")

    result = analyze_session_sentiment(
        consultation.pk,
        language=ai_lang,
        custom_text=_extract_custom_text(request),
    )

    if not result.get("success"):
        if result.get("reason") == "no_input":
            return JsonResponse(
                {"status": "no_input", "message": result.get("error")},
                status=200,
            )
        error_msg = result.get("error") or _("Analysis unavailable.")
        return JsonResponse(
            {"status": "error", "message": error_msg},
            status=503,
        )

    return JsonResponse(
        {
            "status": "success",
            "sentiment": result["sentiment"],
            "keywords": result["keywords"],
            "themes": result["themes"],
            "emotions": result["emotions"],
            "message_analyses": result["message_analyses"],
            "risk_level": result["risk_level"],
            "risk_assessment_status": result["risk_assessment_status"],
            "requires_professional_review": result["requires_professional_review"],
            "language": ai_lang,
        }
    )


@login_required
@require_POST
def ai_generate_summary(request, consultation_id):
    consultation = get_object_or_404(
        Consultation,
        id=consultation_id,
        psychologue=request.user,
    )
    result = generate_session_summary(
        consultation.pk, custom_text=_extract_custom_text(request)
    )
    if not result.get("success"):
        if result.get("reason") == "no_input":
            return JsonResponse(
                {"status": "no_input", "message": result.get("error")},
                status=200,
            )
        error_msg = result.get("error") or _("Summary unavailable.")
        return JsonResponse(
            {"status": "error", "message": error_msg},
            status=503,
        )

    summary = result["data"]["summary"]
    consultation.ai_summary = summary
    consultation.save(update_fields=["ai_summary"])
    return JsonResponse(
        {
            "status": "success",
            "summary": summary,
            "themes": result["data"]["themes"],
            "emotions": result["data"].get("emotions", []),
            "risk_level": result["data"].get("risk_level"),
            "risk_assessment_status": result["data"].get(
                "risk_assessment_status"
            ),
            "requires_professional_review": True,
        }
    )

@login_required
@require_POST
def ai_analyze_sentiment(request, consultation_id):
    if request.user.user_type != "psychologue":
        return JsonResponse({"status": "error", "message": "غير مصرح"}, status=403)

    consultation = get_object_or_404(
        Consultation,
        id=consultation_id,
        psychologue=request.user,
    )
    result = analyze_session_sentiment(
        consultation.pk, custom_text=_extract_custom_text(request)
    )
    if not result.get("success"):
        if result.get("reason") == "no_input":
            return JsonResponse(
                {
                    "status": "no_input",
                    "message": result.get("error"),
                },
                status=200,
            )
        return JsonResponse(
            {
                "status": "error",
                "message": result.get("error", "تحليل المشاعر غير متاح."),
            },
            status=503,
        )

    return JsonResponse(
        {
            "status": "success",
            "sentiment": result["sentiment"],
            "emotions": result["emotions"],
            "themes": result["themes"],
            "keywords": result["keywords"],
            "message_analyses": result["message_analyses"],
            "risk_level": result["risk_level"],
            "risk_assessment_status": result["risk_assessment_status"],
            "requires_professional_review": True,
        }
    )


@login_required
@require_POST
def ai_analyze_full(request, consultation_id):
    if request.user.user_type != "psychologue":
        return JsonResponse({"status": "error", "message": "غير مصرح"}, status=403)

    consultation = get_object_or_404(
        Consultation,
        id=consultation_id,
        psychologue=request.user,
    )

    lang = request.GET.get("lang") or getattr(request, "LANGUAGE_CODE", None)
    if not lang:
        lang = "fr"
    elif lang not in ("ar", "fr", "en", "darija"):
        return JsonResponse(
            {
                "status": "error",
                "message": f"اللغة غير مدعومة: {lang}. اللغات المدعومة: ar, fr, en.",
            },
            status=400,
        )

    result = analyze_session_full(
        consultation.pk,
        language=lang,
        custom_text=_extract_custom_text(request),
    )
    if not result.get("success"):
        if result.get("reason") == "no_input":
            return JsonResponse(
                {
                    "status": "no_input",
                    "message": result.get("error"),
                },
                status=200,
            )
        return JsonResponse(
            {
                "status": "error",
                "message": result.get("error", "Analysis unavailable."),
            },
            status=503,
        )

    return JsonResponse(
        {
            "status": "success",
            "emotions": result["emotions"],
            "keywords": result["keywords"],
            "themes": result["themes"],
            "summary": result["summary"],
            "emotional_evolution": result["emotional_evolution"],
            "risk_level": result["risk_level"],
            "risk_assessment_status": result["risk_assessment_status"],
            "requires_professional_review": True,
        }
    )


@login_required
@require_POST
def ai_save_notes(request, consultation_id):
    """Enregistre les notes du psychologue."""
    consultation = get_object_or_404(Consultation, id=consultation_id)

    if consultation.psychologue != request.user:
        return JsonResponse({"status": "error", "message": "Non autorisé"}, status=403)

    try:
        data = json.loads(request.body)
        notes = data.get("notes", "")
    except json.JSONDecodeError:
        return JsonResponse(
            {"status": "error", "message": "Données invalides"}, status=400
        )

    if not notes:
        return JsonResponse({"status": "error", "message": "Notes vides"}, status=400)

    consultation.psychologue_notes = notes
    consultation.save(update_fields=["psychologue_notes"])

    return JsonResponse(
        {"status": "success", "message": "Notes enregistrées avec succès"}
    )
