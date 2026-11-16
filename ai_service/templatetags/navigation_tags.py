from urllib.parse import urlsplit

from django import template
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme


register = template.Library()


@register.inclusion_tag("partials/back_button.html", takes_context=True)
def back_button(context, fallback_url_name="home", fallback_url=""):
    request = context.get("request")
    if request is None:
        return {"back_url": fallback_url or reverse(fallback_url_name), "referer": ""}

    if not fallback_url:
        fallback_url = reverse(fallback_url_name)
    if not url_has_allowed_host_and_scheme(
        fallback_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        fallback_url = reverse(fallback_url_name)

    referer = request.META.get("HTTP_REFERER", "")
    safe_referer = ""
    if url_has_allowed_host_and_scheme(
        referer,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        referer_parts = urlsplit(referer)
        current_parts = urlsplit(request.build_absolute_uri())
        if (referer_parts.path, referer_parts.query) != (
            current_parts.path,
            current_parts.query,
        ):
            safe_referer = referer

    return {
        "back_url": safe_referer or fallback_url,
        "referer": safe_referer,
    }
