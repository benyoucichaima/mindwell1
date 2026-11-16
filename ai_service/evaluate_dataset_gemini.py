"""
سكريبت مستقل لتقييم ميزة Full Session Analysis على Dataset المحادثات المتعددة اللغات.

يقرأ ai_service/datasets/conversations_multilingual.json فقط، ويمرر كل محادثة إلى
دالة analyze_transcript_full() الموجودة، ويحفظ النتائج في
ai_service/evaluation_results_gemini.json مع دعم الاستئناف.

لا يُجري أي استدعاء API فعلي في هذه المرحلة (يعتمد على mocks للاختبار).
لا يعدّل Dataset الأصلية، ولا قاعدة البيانات، ولا Models، ولا مigrations.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

# إعداد Django للسماح بالاستيراد من ai_service.services
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mindwell.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402

from ai_service.services import (  # noqa: E402
    SUPPORTED_LANGUAGES,
    analyze_transcript_full,
)

logger = logging.getLogger(__name__)

DATASET_PATH = BASE_DIR / "ai_service" / "datasets" / "conversations_multilingual.json"
RESULTS_PATH = BASE_DIR / "ai_service" / "evaluation_results_gemini.json"
RESULTS_PATH_TEST = BASE_DIR / "ai_service" / "evaluation_results_gemini_test.json"

REQUIRED_FIELDS = ("summary", "themes", "emotions", "keywords", "emotional_evolution", "risk_assessment_status", "risk_level")

# مصطلحات تشخيصية طبية يجب عدم ظهورها في التحليل (فحص آلي أولي)
MEDICAL_DIAGNOSIS_TERMS = (
    # Arabic
    "تشخيص",
    "تشخيصي",
    "متلازمة",
    "اضطراب نفسي",
    "اضطراب اكتئابي",
    "اضطراب قلق",
    "الاكتئاب الشديد",
    "الاضطراب الثنائي",
    "الفصام",
    "تشخيص الاكتئاب",
    "تشخيص القلق",
    "وصفة طبية",
    "دواء لعلاج",
    "علاج نفسي",
    "AI يمكن أن يشخص",
    "الذكاء الاصطناعي يشخص",
    # French
    "dépression majeure",
    "dépression clinique",
    "trouble bipolaire",
    "schizophrénie",
    "trouble de la personnalité",
    "diagnostic médical",
    "diagnostic psychologique",
    "prescription médicale",
    # English
    "case",
    "syndrome",
    "AI can diagnose",
    "AI can diagnose",
)


def load_dataset() -> list[dict[str, Any]]:
    """تحميل Dataset المحادثات قراءة فقط."""
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_existing_results(results_path: Path) -> list[dict[str, Any]]:
    """تحميل النتائج السابقة من مسار محدد، Otherwise قائمة فارغة."""
    if not results_path.exists():
        return []
    try:
        with open(results_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        logger.warning("ملف النتائج غير بصيغة قائمة، سيتم البدء بقائمة فارغة.")
        return []
    except (json.JSONDecodeError, OSError) as error:
        logger.warning("تعذر قراءة ملف النتائج السابق (%s)، سيتم البدء بقائمة فارغة.", error)
        return []


def save_results(results: list[dict[str, Any]], results_path: Path) -> None:
    """حفظ جميع النتائج في ملف JSON منفصل (لا يحذف النتائج السابقة عند الاستئناف)."""
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def is_result_complete(
    result: dict[str, Any],
    conversation_id: str,
    language: str,
    model: str,
) -> bool:
    """تحقق ما إذا كانت النتيجة مكتملة وتحتوي على الحقول الستة الصحيحة لنفس المحادثة واللغة والموديل."""
    if not isinstance(result, dict):
        return False
    if result.get("conversation_id") != conversation_id:
        return False
    if result.get("language") != language:
        return False
    if result.get("model_used") != model:
        return False
    if not result.get("success"):
        return False
    for field in REQUIRED_FIELDS:
        if field not in result:
            return False
        if field == "summary" or field == "emotional_evolution":
            if not isinstance(result[field], str) or not result[field].strip():
                return False
        elif field in ("themes", "emotions", "keywords"):
            if not isinstance(result[field], list):
                return False
        elif field == "risk_level":
            if result[field] is not None and result[field] not in ("low", "medium", "high"):
                return False
        elif field == "risk_assessment_status":
            if result[field] not in ("assessed", "insufficient_information"):
                return False
    return True


def build_transcript(conversation: dict[str, Any]) -> list[dict[str, str]]:
    """بناءنسخة المحادثة بالترتيب الأصلي مع تمييز speaker."""
    transcript: list[dict[str, str]] = []
    for message in conversation.get("messages", []):
        speaker = message.get("speaker", "")
        content = message.get("content", "")
        if not content or not content.strip():
            continue
        transcript.append(
            {
                "speaker": "Patient" if speaker == "patient" else "Psychologue",
                "text": content.strip(),
            }
        )
    return transcript


def validate_json_structure(result: dict[str, Any]) -> dict[str, list[str]]:
    """فحص بنية JSON وجودة الحقول الستة. يعيد قاموساً بـ errors و warnings."""
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(result, dict):
        errors.append("النتيجة ليست كائن JSON صالح")
        return {"errors": errors, "warnings": warnings}

    for field in REQUIRED_FIELDS:
        if field not in result:
            errors.append(f"الحقل مفقود: {field}")
            continue
        value = result[field]
        if field in ("summary", "emotional_evolution"):
            if not isinstance(value, str) or not value.strip():
                errors.append(f"الحقل {field} فارغ أو ليس نصًا")
        elif field in ("themes", "emotions", "keywords"):
            if not isinstance(value, list):
                errors.append(f"الحقل {field} ليست قائمة")
            elif any(not isinstance(item, str) or not item.strip() for item in value):
                errors.append(f"الحقل {field} يحتوي على عناصر غير نصية أو فارغة")
        elif field == "risk_level":
            if value is not None and value not in ("low", "medium", "high"):
                errors.append(f"الحقل risk_level غير صالح: {value}")
        elif field == "risk_assessment_status":
            if value not in ("assessed", "insufficient_information"):
                errors.append(f"الحقل risk_assessment_status غير صالح: {value}")

    return {"errors": errors, "warnings": warnings}


def validate_language_match(result: dict[str, Any], conversation_language: str) -> dict[str, list[str]]:
    """فحص أن لغة التحليل تتطابق مع لغة المحادثة الأصلية (فحص أولي)."""
    errors: list[str] = []
    warnings: list[str] = []
    summary = result.get("summary", "")
    emotional_evolution = result.get("emotional_evolution", "")
    combined_text = f"{summary} {emotional_evolution}".lower()

    # مؤشرات بسيطة لكل لغة (ليست قاطعة، للفحص الأولي فقط)
    language_indicators = {
        "ar": [
            "هذا",
            "هذه",
            "التي",
            "الذي",
            "أنا",
            "لدي",
            "عندي",
            "أشعر",
            "يعبر",
            "المريض",
            "القلق",
            "التوتر",
            "هدوء",
            "مشاعر",
            "تشعر",
            "أحس",
            "لا يوجد",
            "هناك",
        ],
        "fr": ["le", "la", "et", "en", "je", "suis", "que", "pas", "pour", "avec"],
        "en": ["the", "and", "in", "i", "am", "is", "that", "not", "for", "with"],
    }

    expected_indicators = language_indicators.get(conversation_language, [])
    if not expected_indicators:
        return {"errors": errors, "warnings": warnings}  # لغة غير معروفة، لا يمكننا الفحص

    # Use word-boundary regex matching to avoid false positives (e.g., "en" inside "patient").
    # Arabic is written without spaces between a clitic/letter and the following word, so
    # \b…\b never matches attached forms (e.g. "ال" inside "المريض"). For Arabic, match
    # multi-character function words on a left/right non-word boundary; standalone phrases
    # (containing a space) are matched as substrings.
    if conversation_language == "ar":
        found_indicators = [
            ind
            for ind in expected_indicators
            if (
                ind in combined_text
                if " " in ind
                else re.search(r"(?<!\w)" + re.escape(ind) + r"(?!\w)", combined_text)
            )
        ]
    else:
        found_indicators = [
            ind
            for ind in expected_indicators
            if re.search(r"\b" + re.escape(ind) + r"\b", combined_text)
        ]
    if len(found_indicators) == 0 and len(combined_text.strip()) > 0:
        warnings.append(f"لغة التحليل قد لا تتطابق مع لغة المحادثة ({conversation_language})")

    return {"errors": errors, "warnings": warnings}


def validate_no_diagnoses(result: dict[str, Any]) -> dict[str, list[str]]:
    """فحص عدم وجود تشخيصات طبية أو ادعاءات بالقدرة على التشخيص."""
    errors: list[str] = []
    warnings: list[str] = []
    combined_text = " ".join(
        str(result.get(field, "")) for field in ("summary", "emotional_evolution", "themes")
    ).lower()

    for term in MEDICAL_DIAGNOSIS_TERMS:
        if term.lower() in combined_text:
            errors.append(f"يُحتمل وجود مصطلح تشخيصي/طبي: '{term}'")

    return {"errors": errors, "warnings": warnings}


def validate_speaker_separation(conversation: dict[str, Any], result: dict[str, Any]) -> dict[str, list[str]]:
    """فحص عدم الخلط بين كلام المريض وكلام الأخصائي في emotional_evolution."""
    errors: list[str] = []
    warnings: list[str] = []
    patient_texts = []
    psychologue_texts = []

    for message in conversation.get("messages", []):
        speaker = message.get("speaker", "")
        content = message.get("content", "")
        if speaker == "patient":
            patient_texts.append(content.lower())
        elif speaker == "psychologue":
            psychologue_texts.append(content.lower())

    evolution = result.get("emotional_evolution", "").lower()

    # إذا كان emotional_evolution يحتوي على نص ينسب بشكل صريح إلى الأخصائي مشاعر المريض، نعلق عليه
    # هذا فحص أولي بسيط
    attribution_indicators = ["الأخصائي قال", "الطبيب قال", "psychologue said", "doctor said"]
    for indicator in attribution_indicators:
        if indicator in evolution:
            warnings.append(f"يُحتمل إسناد مشاعر إلى الأخصائي: '{indicator}'")

    return {"errors": errors, "warnings": warnings}


def validate_risk_assessment(result: dict[str, Any]) -> dict[str, list[str]]:
    """فحص أن غياب كلمات الخطر ليس دليلاً كافياً على risk_level منخفض."""
    errors: list[str] = []
    warnings: list[str] = []
    risk_level = result.get("risk_level")
    summary = result.get("summary", "").lower()
    emotional_evolution = result.get("emotional_evolution", "").lower()
    combined = f"{summary} {emotional_evolution}"

    risk_keywords = (
        "trans suicide",
        "automutilation",
        "self-harm",
        "égoïsme",
        "mourir",
        "mort",
        "تطوع بالانتحار",
        "إيذاء النفس",
        "أريد الموت",
        "أريد الانتحار",
        "je veux mourir",
        "je veux me tuer",
    )

    has_risk_keywords = any(kw in combined for kw in risk_keywords)

    if risk_level == "low" and not has_risk_keywords:
        # هذا ليس خطأ قاطعًا، بل تنبيه للمراجعة البشرية لأن غياب الكلمات ليس دليلاً كافياً
        warnings.append(
            "تنبيه: risk_level منخفض بدون وجود كلمات خطر صريحة — يتطلب مراجعة بشرية للتأكد من أن غياب المعلومات ليس دليلاً على السلامة"
        )

    return {"errors": errors, "warnings": warnings}


def validate_risk_consistency(
    conversation: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, list[str]]:
    """
    Cross-validate risk_level against transcript content and summary.
    Uses patient-only statements, clause-aware negation detection, and context windows.
    Negation does not suppress risk indicators when credible imminent danger evidence
    (explicit plan, access to means, near-term timeframe, clear statement of acting soon)
    co-occurs in the same patient message.
    Returns warnings only — never errors that would reject model output.
    """
    warnings: list[str] = []

    risk_level = result.get("risk_level")
    summary = result.get("summary", "")
    emotional_evolution = result.get("emotional_evolution", "")
    combined_output = f"{summary} {emotional_evolution}".lower()

    # Extract patient-only messages with boundaries preserved
    patient_messages = [
        m["content"].lower()
        for m in conversation.get("messages", [])
        if m.get("speaker") == "patient"
    ]
    patient_text = " | ".join(patient_messages)  # Preserve message boundaries

    # Imminent danger evidence patterns — must be explicit and intent-linked
    # These are checked within the SAME patient message as the risk indicator
    IMMINENT_DANGER_PATTERNS = {
        "fr": [
            r"\b(?:plan|projet|intention)\b.{0,30}\b(?:ce soir|demain|tout à l'heure|bientôt|prochainement)\b",
            r"\b(?:j'ai|je possède|j'ai accès à)\b.{0,30}\b(?:couteau|pilules?|médicaments?|corde|arme|produit)\b",
            r"\b(?:ce soir|demain|tout à l'heure|bientôt|prochainement)\b.{0,30}\b(?:je vais|je ferai|j'irai|passer à l'acte|agir)\b",
            r"\b(?:proche de|sur le point de|prêt à)\b.{0,20}\b(?:passer à l'acte|agir|le faire)\b",
            r"\b(?:perdu|perds?|plus de)\s+contr[oô]le\b",
        ],
        "ar": [
            r"(?:خطة|مشروع|نية).{0,30}(?:هذه الليلة|غداً|قريباً|قريب)",
            r"(?:لدي|أملك|أمتلك).{0,30}(?:سكين|حبوب|دواء|حبل|سلاح|سم)",
            r"(?:هذه الليلة|غداً|قريباً|قريب).{0,30}(?:سأفعل|سأقوم|سأتصرف|سأنتحر)",
            r"(?:قريب من|على وشك|مستعد).{0,20}(?:التصرف|القيام بالفعل|الانتحار)",
            r"(?:فقدت|أفقد|لا أملك)\s+السيطرة",
        ],
        "dz": [
            r"(?:مخطط|برنامج|نية).{0,30}(?:هاد الصباح|هاد اللّيل|قريب|غدوة)",
            r"(?:عنديا|عمري|ملقاة).{0,30}(?:سكينة|حبوبات|الدواء|حبال|السّم|سم)",
            r"(?:هاد الصباح|هاد اللّيل|قريب|غدوة).{0,30}(?:نخدم|نعمل|نتصرف|ننحر روحي)",
            r"(?:قريب|قاش|على وشك).{0,20}(?:نخدم فيها|نعمل فيها|ننحر)",
            r"(?:مشي|فقدت|ما بقياش).{0,15}السيطرة",
        ],
    }

    def _has_imminent_danger(message: str, language: str) -> bool:
        """Check if a single patient message contains credible imminent danger evidence."""
        patterns = IMMINENT_DANGER_PATTERNS.get(language, [])
        for pattern in patterns:
            if re.search(pattern, message):
                return True
        return False

    # Helper: check if indicator appears in non-negated context
    def has_indicator(text: str, indicators: list[str], context_chars: int = 50) -> bool:
        import re
        lang = conversation.get("language", "fr")
        
        # Split text back into individual patient messages for message-level checks
        msg_list = [m.strip() for m in text.split(" | ")]
        
        for ind in indicators:
            pos = text.find(ind)
            while pos != -1:
                # Find which message this indicator belongs to
                char_count = 0
                msg_idx = -1
                for i, msg in enumerate(msg_list):
                    if char_count <= pos < char_count + len(msg):
                        msg_idx = i
                        break
                    char_count += len(msg) + 3  # " | " separator
                
                current_message = msg_list[msg_idx] if msg_idx >= 0 else ""
                
                # CONTEXT-AWARE OVERRIDE: If this message contains credible imminent danger
                # evidence, do NOT suppress the indicator even if negation is present
                if _has_imminent_danger(current_message, lang):
                    return True
                
                # Check for negation in context BEFORE and AFTER the indicator (not within it)
                before_start = max(0, pos - context_chars)
                before_end = pos
                after_start = pos + len(ind)
                after_end = min(len(text), pos + len(ind) + context_chars)
                
                before_window = text[before_start:before_end]
                after_window = text[after_start:after_end]
                combined_window = before_window + " " + after_window
                
                has_negation = False
                
                # French: ne ... pas/jamais/plus/rien/personne — clause-aware
                # Only checks the clause containing the negation marker
                has_french_negation = False
                ne_pos = before_window.find(" ne ")
                ne_apos_pos = before_window.find(" n'")
                if ne_pos != -1 or ne_apos_pos != -1:
                    last_period = max(before_window.rfind("."), before_window.rfind("!"), before_window.rfind("?"))
                    clause = before_window[last_period + 1:] if last_period != -1 else before_window
                    
                    neg_words = [" pas ", " jamais ", " plus ", " rien ", " personne ",
                                 "pas ", "jamais ", "plus ", "rien ", "personne ",
                                 "pas.", "jamais.", "plus.", "rien.", "personne."]
                    for neg_w in neg_words:
                        if neg_w in clause:
                            has_french_negation = True
                            break
                
                # Also check AFTER window for French (negation follows, e.g., "mais je ne le ferais jamais")
                if not has_french_negation:
                    ne_pos = after_window.find(" ne ")
                    ne_apos_pos = after_window.find(" n'")
                    if ne_pos != -1 or ne_apos_pos != -1:
                        first_period = after_window.find(".")
                        first_excl = after_window.find("!")
                        first_quest = after_window.find("?")
                        first_end = len(after_window)
                        for p in [first_period, first_excl, first_quest]:
                            if p != -1 and p < first_end:
                                first_end = p + 1
                        clause = after_window[:first_end]
                        
                        neg_words = [" pas ", " jamais ", " plus ", " rien ", " personne ",
                                     "pas ", "jamais ", "plus ", "rien ", "personne ",
                                     "pas.", "jamais.", "plus.", "rien.", "personne."]
                        for neg_w in neg_words:
                            if neg_w in clause:
                                has_french_negation = True
                                break
                
                if has_french_negation:
                    has_negation = True
                
                # English: don't, doesn't, didn't, not, never, without
                if not has_negation:
                    eng_negs = [" don't ", " doesn't ", " didn't ", " not ", " never ", " without ",
                                "don't ", "doesn't ", "didn't ", "not ", "never ", "without ",
                                "not.", "never."]
                    for neg_w in eng_negs:
                        if neg_w in combined_window:
                            has_negation = True
                            break
                
                # Arabic (MSA): لا , لم , لن , ما — support prefixed forms (لا أريد، لم أعد، لن أفعل، ما أريد)
                # Check before_window for standalone or prefixed negation particles
                if not has_negation:
                    # First check if current message has Darija "ما...ش" patterns
                    # If so, skip MSA "ما" pattern to avoid false positives on Darija "ما...ش"
                    has_dz_negation = False
                    dz_skip_patterns = [
                        r"ما\s+\w+\s*ش\b",   # ما ... ش
                        r"ما\s+بغيتش\b",
                        r"ما\s+باش\b",
                        r"ما\s+عنديش\b",
                    ]
                    for pattern in dz_skip_patterns:
                        if re.search(pattern, current_message):
                            has_dz_negation = True
                            break
                    
                    # Patterns match negation particle at start of word or after whitespace
                    msa_neg_patterns = [
                        r"(^|\s)لا\w*($|\s|[.,؛])",   # لا، لا أريد، لا أفعل، etc.
                        r"(^|\s)لم\w*($|\s|[.,؛])",   # لم، لم أعد، لم أفعل، etc.
                        r"(^|\s)لن\w*($|\s|[.,؛])",   # لن، لن أفعل، لن أذهب، etc.
                    ]
                    # Only add MSA "ما" pattern if no Darija "ما...ش" in current message
                    if not has_dz_negation:
                        msa_neg_patterns.append(r"(^|\s)ما\w*($|\s|[.,؛])")
                    
                    for pattern in msa_neg_patterns:
                        if re.search(pattern, before_window):
                            has_negation = True
                            break
                
                # Algerian Darija: ما بغيتش، ما...ش، ما باش، ما عنديش
                # Use word-boundary-aware patterns that require grammatical context
                if not has_negation:
                    dz_neg_patterns = [
                        r"ما\s+بغيتش\b",              # ما بغيتش
                        r"ما\s+باش\b",                 # ما باش
                        r"ما\s+عنديش\b",               # ما عنديش
                        r"ما\s+ن\w+\s*ش\b",            # ما ن...ش (1st person verbs: نموتش، نخدمش، نقولش...)
                        r"ما\s+ت\w+\s*ش\b",            # ما ت...ش (2nd person verbs)
                        r"ما\s+ي\w+\s*ش\b",            # ما ي...ش (3rd person masculine)
                        r"ما\s+ن\w+\s*ش\b",            # what ت...ش (3rd person feminine)
                    ]
                    for pattern in dz_neg_patterns:
                        if re.search(pattern, before_window) or re.search(pattern, current_message):
                            has_negation = True
                            break
                
                if not has_negation:
                    return True
                
                pos = text.find(ind, pos + 1)
        return False

    # HIGH indicators — explicit ideation only
    high_indicators = [
        "je veux mourir", "i want to die", "je veux me tuer", "i want to kill myself",
        "je vais me tuer", "i'm going to kill myself", "je vais me faire du mal",
        "i'm going to hurt myself", "je veux me faire du mal", "i want to hurt myself",
        "suicide", "automutilation", "self-harm", "me tuer", "me faire du mal",
        "أريد أن أموت", "أريد أن أقتل نفسي", "أقتل نفسي", "أؤذي نفسي",
        "بغيت نموت", "بغيت نقتل روحي", "بغيت نقتل راس", "قتل روحي",
    ]

    # MEDIUM indicators — explicit patterns
    medium_indicators = [
        "plus rien n'a de sens", "nothing matters", "nothing will ever get better",
        "ça n'a plus de sens", "j'abandonne complètement", "i give up completely",
        "je n'ai plus d'espoir", "no hope", "je ne me fais pas confiance",
        "i don't trust myself", "proche de passer à l'acte", "close to acting",
        "je bois pour", "i drink to", "je prends pour", "i take ", "pour oublier", "to numb",
        "je bois jusqu", "i drink until", "pour m'év", "to pass out",
        "أ 포기", "لا أمل", "أشرب لـ", "أأخذ حبوب",
        "لم يعد لأي شيء معنى", "استسلمت تماماً", "ما عادش في أمل", "خلاص عندي",
        "ما بقاش في شي معنى", "مشيت فيها", "ما باقيش نقدر",
    ]

    has_high = has_indicator(patient_text, high_indicators)
    has_medium = has_indicator(patient_text, medium_indicators)

    # Warnings only — never errors that override model
    if risk_level == "high" and not has_high:
        warnings.append(
            f"risk_level=high but no explicit self-harm/suicidal ideation found in patient statements (negation-aware check). "
            f"Model output summary: '{summary[:120]}...' — Psychologist must verify."
        )

    if risk_level == "medium" and not (has_medium or has_high):
        warnings.append(
            f"risk_level=medium but no explicit hopelessness/substance/loss-of-control indicators found in patient statements. "
            f"Consider if distress/impairment alone should be low. Output: '{summary[:120]}...'"
        )

    if risk_level == "low" and has_high:
        warnings.append(
            f"risk_level=low but explicit self-harm/suicidal ideation detected in patient statements. "
            f"URGENT: Psychologist must review immediately."
        )

    if risk_level == "low" and has_medium:
        # Check if summary acknowledges why medium not assigned
        ack_terms = ["insufficient", "insuffisant", "aucune", "no explicit", "pas d'indicateur", "not found"]
        if not any(term in combined_output for term in ack_terms):
            warnings.append(
                f"risk_level=low with explicit hopelessness/substance/loss-of-control indicators present. "
                f"Summary should explain why medium was not assigned. Output: '{summary[:120]}...'"
            )

    if risk_level == "low" and not has_medium and not has_high:
        # Check for mandatory insufficient-evidence note
        evidence_terms = ["insufficient evidence", "insuffisant", "aucune preuve", "no explicit", "pas d'indicateur"]
        if not any(term in combined_output for term in evidence_terms):
            warnings.append(
                f"risk_level=low with no explicit indicators — summary should include "
                f"mandatory note: 'Risk level set to low due to insufficient evidence...' per protocol."
            )

    return {"errors": [], "warnings": warnings}


def run_quality_checks(
    conversation: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, dict[str, list[str]]]:
    """تشغيل جميع فحوصات الجودة الآلية وإرجاع القاموس حسب الفئة مع فصل errors/warnings."""
    return {
        "json_structure": validate_json_structure(result),
        "language_match": validate_language_match(result, conversation.get("language", "")),
        "no_diagnoses": validate_no_diagnoses(result),
        "speaker_separation": validate_speaker_separation(conversation, result),
        "risk_assessment": validate_risk_assessment(result),
        "risk_consistency": validate_risk_consistency(conversation, result),
    }


def evaluate_conversation(
    conversation: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    """تقييم محادثة واحدة وإرجاع نتيجة كاملة معmetadata."""
    conversation_id = conversation.get("id", "unknown")
    language = conversation.get("language", "fr")

    transcript = build_transcript(conversation)

    if not transcript:
        return {
            "conversation_id": conversation_id,
            "scenario_id": conversation.get("scenario_id"),
            "language": language,
            "theme": conversation.get("theme"),
            "model_used": model,
            "success": False,
            "error": "Transcript is empty after filtering.",
            "summary": "",
            "themes": [],
            "emotions": [],
            "keywords": [],
            "emotional_evolution": "",
            "risk_level": "low",
        }

    if language not in SUPPORTED_LANGUAGES:
        return {
            "conversation_id": conversation_id,
            "scenario_id": conversation.get("scenario_id"),
            "language": language,
            "theme": conversation.get("theme"),
            "model_used": model,
            "success": False,
            "error": f"Unsupported language: {language}",
            "summary": "",
            "themes": [],
            "emotions": [],
            "keywords": [],
            "emotional_evolution": "",
            "risk_level": "low",
        }

    try:
        analysis_result = analyze_transcript_full(transcript, language)
    except Exception as error:  # noqa: BLE001
        logger.exception("فشل تحليل المحادثة %s", conversation_id)
        return {
            "conversation_id": conversation_id,
            "scenario_id": conversation.get("scenario_id"),
            "language": language,
            "theme": conversation.get("theme"),
            "model_used": model,
            "success": False,
            "error": f"Unexpected error: {type(error).__name__}",
            "summary": "",
            "themes": [],
            "emotions": [],
            "keywords": [],
            "emotional_evolution": "",
            "risk_level": "low",
        }

    result_record = {
        "conversation_id": conversation_id,
        "scenario_id": conversation.get("scenario_id"),
        "language": language,
        "theme": conversation.get("theme"),
        "model_used": model,
        "success": analysis_result.get("success", False),
        "error": analysis_result.get("error"),
        "summary": analysis_result.get("summary", ""),
        "themes": analysis_result.get("themes", []),
        "emotions": analysis_result.get("emotions", []),
        "keywords": analysis_result.get("keywords", []),
        "emotional_evolution": analysis_result.get("emotional_evolution", ""),
        "risk_level": analysis_result.get("risk_level", "low"),
    }

    # تشغيل فحوصات الجودة وإضافتها إلى النتيجة
    quality_checks = run_quality_checks(conversation, result_record)
    result_record["quality_checks"] = quality_checks

    # quality_passed يعتمد على غياب الأخطاء فقط (errors)
    result_record["quality_passed"] = all(
        len(checks.get("errors", [])) == 0 for checks in quality_checks.values()
    )

    # requires_human_review يُفعّل عند وجود أي تحذيرات (warnings)
    result_record["requires_human_review"] = any(
        len(checks.get("warnings", [])) > 0 for checks in quality_checks.values()
    )

    return result_record


def main() -> None:
    """نقطة الدخول الرئيسية للسكريبت."""
    parser = argparse.ArgumentParser(
        description="تقييم ميزة Full Session Analysis على محادثات محددة عبر Gemini."
    )
    parser.add_argument(
        "--ids",
        type=str,
        default=None,
        help="معرفات المحادثات المراد تحليلها، مفصولة بفاصلة (مثال: conv_001,conv_002,conv_003).",
    )
    args = parser.parse_args()

    # في وضع التجربة، يجب تحديد IDs صراحةً
    if not args.ids:
        logger.error("يجب تحديد --ids لمعرفة المحادثات المراد تحليلها في وضع التجربة.")
        print(
            "خطأ: يجب تحديد --ids لمعرفة المحادثات المراد تحليلها. "
            "مثال: python ai_service/evaluate_dataset_gemini.py --ids conv_001,conv_002,conv_003"
        )
        sys.exit(1)

    requested_ids = [cid.strip() for cid in args.ids.split(",") if cid.strip()]

    # التحقق من مزود الذكاء الاصطناعي
    ai_provider = getattr(settings, "AI_PROVIDER", "openai")
    if ai_provider != "gemini":
        logger.error(
            "AI_PROVIDER محدد حاليًا إلى '%s'. يجب تعيينه إلى 'gemini' لتشغيل هذا السكريبت.",
            ai_provider,
        )
        print(
            f"خطأ: AI_PROVIDER = '{ai_provider}'. السكريبت يدعم Gemini فقط حاليًا. "
            "حدد متغير البيئة AI_PROVIDER=gemini قبل التشغيل."
        )
        sys.exit(1)

    if not getattr(settings, "GEMINI_API_KEY", ""):
        logger.error("GEMINI_API_KEY غير مضبوط في الإعدادات.")
        print("خطأ: GEMINI_API_KEY غير مضبوط. حدد متغير البيئة قبل التشغيل.")
        sys.exit(1)

    model = getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")

    logger.info(
        "بدء تقييم experiencia على %d محادثة باستخدام المزود: %s والموديل: %s",
        len(requested_ids),
        ai_provider,
        model,
    )

    conversations = load_dataset()
    logger.info("تم تحميل %d محادثة من Dataset.", len(conversations))

    # فلترة المحادثات بناءً على الـ IDs المطلوبة
    id_set = set(requested_ids)
    filtered_conversations = [
        c for c in conversations if c.get("id") in id_set
    ]

    if len(filtered_conversations) != len(requested_ids):
        found_ids = {c.get("id") for c in filtered_conversations}
        missing_ids = id_set - found_ids
        logger.warning(
            "بعض المعرفات المطلوبة غير موجودة في Dataset: %s", sorted(missing_ids)
        )
        print(
            "تحذير: المعرفات التالية غير موجودة في Dataset: "
            + ", ".join(sorted(missing_ids))
        )

    # استخدام ملف نتائج منفصل للتجربة
    results_path = RESULTS_PATH_TEST

    existing_results = load_existing_results(results_path)
    completed_ids = {
        (r.get("conversation_id"), r.get("language"), r.get("model_used"))
        for r in existing_results
        if is_result_complete(
            r, r.get("conversation_id", ""), r.get("language", ""), r.get("model_used", "")
        )
    }

    results = list(existing_results)
    skipped = 0
    processed = 0
    succeeded = 0
    failed = 0

    for conversation in filtered_conversations:
        conversation_id = conversation.get("id", "unknown")
        language = conversation.get("language", "fr")

        if (conversation_id, language, model) in completed_ids:
            skipped += 1
            continue

        result_record = evaluate_conversation(conversation, model)
        results.append(result_record)

        # حفظ فوري بعد كل محادثة (لا يتم حذف النتائج السابقة)
        save_results(results, results_path)

        processed += 1
        if result_record["success"]:
            succeeded += 1
        else:
            failed += 1
            logger.warning(
                "فشل تحليل المحادثة %s (اللغة: %s): %s",
                conversation_id,
                language,
                result_record.get("error", "غير معروف"),
            )

    logger.info(
        "اكتمل التقييم التجريبي. المعالجة: %d، التخطي: %d، النجاح: %d، الفشل: %d",
        processed,
        skipped,
        succeeded,
        failed,
    )

    print(
        f"اكتمل التقييم التجريبي: المعالجة={processed}, التخطي={skipped}, "
        f"النجاح={succeeded}, الفشل={failed}. النتائج محفوظة في: {results_path}"
    )


if __name__ == "__main__":
    main()
