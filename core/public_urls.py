def request_scheme(request):
    return "https" if request.is_secure() else "http"


def _local_hostname(hostname):
    value = (hostname or "").strip().lower().rstrip(".")
    return value == "localhost" or value == "127.0.0.1" or value.endswith(".localhost")


def build_public_site_url(request, hostname, path=""):
    host = (hostname or "").strip().lower().rstrip(".")
    if not host:
        return ""

    if _local_hostname(host):
        request_authority = request.get_host().rstrip(".")
        port = ""
        if ":" in request_authority:
            candidate = request_authority.rsplit(":", 1)[1]
            if candidate.isdigit():
                port = candidate
        if not port:
            port = request.get_port()
        if port and port not in {"80", "443"}:
            host = f"{host}:{port}"

    normalized_path = path or ""
    if normalized_path and not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"

    return f"{request_scheme(request)}://{host}{normalized_path}"
