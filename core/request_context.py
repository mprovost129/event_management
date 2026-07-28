from contextvars import ContextVar

request_id_var = ContextVar("request_id", default="-")
site_id_var = ContextVar("site_id", default="-")


def set_site_id(site_id):
    """Attach a tenant identifier after future host-resolution middleware runs."""
    return site_id_var.set(str(site_id) if site_id else "-")
