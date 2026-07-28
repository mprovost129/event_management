from django.conf import settings


def platform(request):
    return {
        "platform_name": settings.PLATFORM_NAME,
        "platform_domain": settings.PLATFORM_DOMAIN,
    }
