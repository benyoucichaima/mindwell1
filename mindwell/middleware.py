from django.conf import settings
from django.middleware.locale import LocaleMiddleware
from django.utils.cache import patch_vary_headers
from django.utils import translation


class PreferredLanguageMiddleware(LocaleMiddleware):
    def process_view(self, request, view_func, view_args, view_kwargs):
        language = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
        if language and translation.check_for_language(language):
            translation.activate(translation.get_supported_language_variant(language))
            request.LANGUAGE_CODE = translation.get_language()
            request._preferred_language_applied = True

    def process_response(self, request, response):
        response = super().process_response(request, response)
        if getattr(request, "_preferred_language_applied", False):
            patch_vary_headers(response, ("Cookie",))
        return response
