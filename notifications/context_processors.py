def notifications(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {"unread_notification_count": 0}
    return {
        "unread_notification_count": request.user.notifications.filter(
            read_at__isnull=True
        ).count()
    }
