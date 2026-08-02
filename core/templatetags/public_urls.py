from django import template

from core.public_urls import build_public_site_url

register = template.Library()


@register.filter
def site_public_url(hostname, request):
    return build_public_site_url(request, hostname)
