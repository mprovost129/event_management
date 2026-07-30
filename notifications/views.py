from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.pagination import paginate

from .models import Notification


@login_required
def notification_list(request):
    notifications = paginate(
        request, request.user.notifications.select_related("site"), per_page=25
    )
    return render(
        request,
        "notifications/list.html",
        {"notifications": notifications, "page_obj": notifications},
    )


@login_required
@require_POST
def mark_read(request, notification_id):
    notification = get_object_or_404(
        Notification, pk=notification_id, recipient=request.user
    )
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=("read_at",))
    return redirect(notification.action_url or "notifications:list")


@login_required
@require_POST
def mark_all_read(request):
    request.user.notifications.filter(read_at__isnull=True).update(
        read_at=timezone.now()
    )
    return redirect("notifications:list")
