from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from .models import Site, SiteRole


def site_role_required(
    *allowed_roles,
    require_operational=False,
    allow_inactive=False,
    recovery_dashboard=False,
):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapped(request, site_id, *args, **kwargs):
            site = get_object_or_404(Site, pk=site_id)
            role = SiteRole.objects.filter(
                site=site, user=request.user, is_active=True
            ).first()
            if role is None or role.role not in allowed_roles:
                raise PermissionDenied
            if not site.accepts_public_traffic:
                if allow_inactive:
                    subscriber_recovery = True
                else:
                    subscriber_recovery = (
                        role.role == SiteRole.Role.SUBSCRIBER_ADMIN
                        and recovery_dashboard
                    )
                if require_operational or not subscriber_recovery:
                    raise PermissionDenied
            request.authorized_site = site
            request.site_role = role
            return view_func(request, site_id, *args, **kwargs)

        return wrapped

    return decorator


site_staff_required = site_role_required(
    SiteRole.Role.SUBSCRIBER_ADMIN,
    SiteRole.Role.SITE_MANAGER,
    require_operational=True,
)
subscriber_admin_required = site_role_required(
    SiteRole.Role.SUBSCRIBER_ADMIN, require_operational=True
)
subscriber_recovery_required = site_role_required(
    SiteRole.Role.SUBSCRIBER_ADMIN, allow_inactive=True
)
site_dashboard_required = site_role_required(
    SiteRole.Role.SUBSCRIBER_ADMIN,
    SiteRole.Role.SITE_MANAGER,
    recovery_dashboard=True,
)
