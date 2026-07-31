def notifications(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {
            "unread_notification_count": 0,
            "recent_notifications": [],
        }
    unread = request.user.notifications.filter(read_at__isnull=True)
    return {
        "unread_notification_count": unread.count(),
        "recent_notifications": list(unread.select_related("site")[:5]),
    }
