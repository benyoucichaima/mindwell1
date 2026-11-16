from django.urls import translate_url


def language_switch_urls(request):
    return {
        "language_switch_urls": {
            language: translate_url(request.get_full_path(), language)
            for language in ("fr", "ar", "en")
        }
    }
