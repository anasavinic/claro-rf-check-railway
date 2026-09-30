"""Explicit checks for non-dev settings. Kept separate so tests do not load production."""

from django.core.exceptions import ImproperlyConfigured


def require_explicit_hosts(raw: str) -> list[str]:
    hosts = [host.strip() for host in (raw or "").split(",") if host.strip()]
    if not hosts or "*" in hosts:
        raise ImproperlyConfigured(
            "ALLOWED_HOSTS must be set to one or more explicit hosts in production (wildcard '*' is not allowed)."
        )
    return hosts


def require_csrf_origins(raw: str) -> list[str]:
    origins = [origin.strip() for origin in (raw or "").split(",") if origin.strip()]
    if not origins:
        raise ImproperlyConfigured("CSRF_TRUSTED_ORIGINS must list at least one https origin in production.")
    return origins


def require_object_storage(enabled: bool) -> None:
    if not enabled:
        raise ImproperlyConfigured(
            "USE_OBS_MEDIA=True is required in staging and production; local MEDIA_ROOT is not supported."
        )
