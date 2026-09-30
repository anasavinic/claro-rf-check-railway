"""Staging/production SSO policy."""

import os
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

from .base import env_bool


def _require_https_url(name, value):
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme == "https"
            and parsed.hostname
            and parsed.username is None
            and parsed.password is None
            and not parsed.fragment
        )
        # Access .port to reject malformed port numbers at startup as well.
        _ = parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise ImproperlyConfigured(f"{name} must be an HTTPS URL without credentials or fragments.")
    return parsed


def apply_secure_settings(config):
    hosts_raw = os.environ.get("DJANGO_ALLOWED_HOSTS") or os.environ.get("ALLOWED_HOSTS", "")
    allowed = [host.strip().lower() for host in hosts_raw.split(",") if host.strip()]
    if not allowed or any("*" in host or host.startswith(".") for host in allowed):
        raise ImproperlyConfigured(
            "DJANGO_ALLOWED_HOSTS (or ALLOWED_HOSTS) requires explicit hosts in staging/production."
        )
    config["ALLOWED_HOSTS"] = allowed

    environment = (config.get("CORE_CONNECT_SSO_ENVIRONMENT") or "").strip().lower()
    if environment not in {"staging", "production", "prod"}:
        raise ImproperlyConfigured("CORE_CONNECT_SSO_ENVIRONMENT must be staging or production.")
    config["CORE_CONNECT_SSO_ENVIRONMENT"] = "production" if environment == "prod" else environment
    if config.get("CORE_CONNECT_SSO_DEV") or env_bool("CORE_CONNECT_SSO_DEV"):
        raise ImproperlyConfigured("CORE_CONNECT_SSO_DEV cannot be enabled in staging/production.")

    for name in ("CORE_CONNECT_SSO_ISSUER", "CORE_CONNECT_SSO_CLIENT_ID", "CORE_CONNECT_SSO_REDIRECT_URI"):
        if not (config.get(name) or "").strip():
            raise ImproperlyConfigured(f"{name} is required in staging/production.")
        config[name] = config[name].strip()
    _require_https_url("CORE_CONNECT_SSO_ISSUER", config["CORE_CONNECT_SSO_ISSUER"])
    redirect = _require_https_url("CORE_CONNECT_SSO_REDIRECT_URI", config["CORE_CONNECT_SSO_REDIRECT_URI"])
    internal = (config.get("CORE_CONNECT_SSO_INTERNAL_ISSUER") or "").strip()
    if internal:
        _require_https_url("CORE_CONNECT_SSO_INTERNAL_ISSUER", internal)
    config["CORE_CONNECT_SSO_INTERNAL_ISSUER"] = internal or None
    if redirect.hostname.lower() not in allowed:
        raise ImproperlyConfigured("CORE_CONNECT_SSO_REDIRECT_URI host must belong to DJANGO_ALLOWED_HOSTS.")
    if redirect.path != "/claro-rf/sso/callback/" or redirect.query:
        raise ImproperlyConfigured("CORE_CONNECT_SSO_REDIRECT_URI must target /claro-rf/sso/callback/ without a query.")

    samesite = str(config.get("SESSION_COOKIE_SAMESITE", "Lax")).capitalize()
    if samesite not in {"Lax", "Strict"}:
        raise ImproperlyConfigured("SESSION_COOKIE_SAMESITE must be Lax or Strict.")
    config.update(
        SESSION_COOKIE_SAMESITE=samesite,
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        CSRF_COOKIE_SECURE=True,
        CORE_CONNECT_SSO_ALLOW_INSECURE_TRANSPORT=False,
        CORE_CONNECT_SSO_REFRESH_FAILURE_ACTION="logout",
        SECURE_SSL_REDIRECT=True,
        SECURE_CONTENT_TYPE_NOSNIFF=True,
        SECURE_REFERRER_POLICY="same-origin",
    )
    # Enable only behind a proxy that overwrites this header and prevents direct access.
    if env_bool("DJANGO_TRUST_PROXY_SSL_HEADER"):
        config["SECURE_PROXY_SSL_HEADER"] = ("HTTP_X_FORWARDED_PROTO", "https")
    origins = [origin.strip() for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if origin.strip()]
    for origin in origins:
        _require_https_url("CSRF_TRUSTED_ORIGINS", origin)
    config["CSRF_TRUSTED_ORIGINS"] = origins
