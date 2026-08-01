from django.db import DatabaseError


def notifications(request):
    try:
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return {
                "unread_notification_count": 0,
                "recent_notifications": [],
            }
    except DatabaseError:
        return {
            "unread_notification_count": 0,
            "recent_notifications": [],
        }

    try:
        unread = user.notifications.filter(read_at__isnull=True)
        return {
            "unread_notification_count": unread.count(),
            "recent_notifications": list(unread.select_related("site")[:5]),
        }
    except DatabaseError:
        return {
            "unread_notification_count": 0,
            "recent_notifications": [],
        }
