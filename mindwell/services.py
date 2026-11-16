# mindwell/services.py
from ai_service.services import analyze_consultation as _analyze_consultation


def analyze_consultation(text, language='fr'):
    """Delegate legacy consultation analysis to the central AI service."""
    language = language or 'fr'
    if language not in ('ar', 'darija', 'fr'):
        language = 'fr'
    result = _analyze_consultation(text, language=language)
    if not isinstance(result, dict) or not result.get('success'):
        error = result.get('error', 'AI analysis failed.') if isinstance(result, dict) else 'AI analysis failed.'
        return f"حدث خطأ في الاتصال بالذكاء الاصطناعي: {error}"
    return "\n".join(
        part
        for part in (
            result.get('summary', ''),
            f"Emotions: {', '.join(result.get('emotions', []))}" if result.get('emotions') else '',
            f"Keywords: {', '.join(result.get('keywords', []))}" if result.get('keywords') else '',
        )
        if part
    )