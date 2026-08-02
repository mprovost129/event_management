from django.shortcuts import render


def error_response(request, *, status, title, message):
    return render(
        request,
        "core/error.html",
        {
            "status_code": status,
            "error_title": title,
            "error_message": message,
            "request_id": getattr(request, "request_id", ""),
        },
        status=status,
    )


def bad_request(request, exception):
    return error_response(
        request,
        status=400,
        title="We could not process that request",
        message="Check the information and try again.",
    )


def permission_denied(request, exception):
    return error_response(
        request,
        status=403,
        title="You do not have access",
        message="Sign in with an authorized account or return to the previous page.",
    )


def page_not_found(request, exception):
    return error_response(
        request,
        status=404,
        title="Page not found",
        message="The link may be incorrect, expired, or no longer available.",
    )


def server_error(request):
    return error_response(
        request,
        status=500,
        title="Something went wrong",
        message="Please try again. If the problem continues, share the request ID with support.",
    )
