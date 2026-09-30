import os

from claro_rf_check.json_logging import build_json_logging
from claro_rf_check.settings.hardening import require_csrf_origins, require_explicit_hosts, require_object_storage

from . import base as base_settings
from .base import *  # noqa: F401, F403
from .secure import apply_secure_settings

DEBUG = False

require_object_storage(base_settings.USE_OBS_MEDIA)
ALLOWED_HOSTS = require_explicit_hosts(os.getenv("ALLOWED_HOSTS", "") or os.getenv("DJANGO_ALLOWED_HOSTS", ""))
CSRF_TRUSTED_ORIGINS = require_csrf_origins(os.getenv("CSRF_TRUSTED_ORIGINS", ""))
apply_secure_settings(globals())

CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_EAGER_PROPAGATES = False
CELERY_WORKER_HIJACK_ROOT_LOGGER = False

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOGGING = build_json_logging(LOG_LEVEL)

# Security — assume TLS terminates at the reverse proxy / load balancer
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "True").lower() in ("1", "true", "yes")
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # must remain readable by JS / HTMX
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

# Alpine CSP build and HTMX are served from our static origin. No unsafe-inline.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'self'; "
    "form-action 'self'; "
    "script-src 'self'; "
    "script-src-attr 'none'; "
    "style-src 'self' https://fonts.googleapis.com; "
    "style-src-attr 'none'; "
    "img-src 'self' data:; "
    "font-src 'self' data: https://fonts.gstatic.com; "
    "connect-src 'self'"
)
PERMISSIONS_POLICY = "camera=(), geolocation=(), microphone=(), payment=(), usb=()"
