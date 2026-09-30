"""Single-service Railway settings.

No Redis, Celery worker, or object storage. Postgres comes from the Railway
plugin, uploads sit on a volume, and long jobs run in background threads.
"""

import os

# base.py reads this while it is imported. Force filesystem media for this deploy.
os.environ["USE_OBS_MEDIA"] = "False"

from django.core.exceptions import ImproperlyConfigured

from claro_rf_check.json_logging import build_json_logging
from claro_rf_check.railway_tasks import install_thread_tasks

from .base import *  # noqa: F401, F403
from .base import STORAGES, env_bool

DEBUG = False

_hosts = [
    host.strip()
    for host in (os.getenv("DJANGO_ALLOWED_HOSTS") or os.getenv("ALLOWED_HOSTS") or "").split(",")
    if host.strip()
]
for _name in ("RAILWAY_PUBLIC_DOMAIN", "RAILWAY_PRIVATE_DOMAIN"):
    _domain = (os.getenv(_name) or "").strip()
    if _domain and _domain not in _hosts:
        _hosts.append(_domain)
if not _hosts or "*" in _hosts:
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS must list explicit hosts. RAILWAY_PUBLIC_DOMAIN is included when Railway sets it."
    )
ALLOWED_HOSTS = _hosts

_origins = [origin.strip() for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if origin.strip()]
_public = (os.getenv("RAILWAY_PUBLIC_DOMAIN") or "").strip()
if _public:
    _origin = f"https://{_public}"
    if _origin not in _origins:
        _origins.append(_origin)
CSRF_TRUSTED_ORIGINS = _origins

MEDIA_URL = "/media/"
MEDIA_ROOT = os.getenv("MEDIA_ROOT", "/data/media")
USE_OBS_MEDIA = False
STORAGES["default"] = {"BACKEND": "django.core.files.storage.FileSystemStorage"}
STORAGES["staticfiles"] = {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"}
STATICFILES_STORAGE = "whitenoise.storage.CompressedStaticFilesStorage"

# One replica: locmem is enough for the upload rate limit. Do not scale out.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "claro-rf-railway",
    }
}

# Tasks are dispatched by railway_tasks, not a broker.
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_EAGER_PROPAGATES = False
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

CLARO_RF_TEST_AUTH_ENABLED = env_bool("CLARO_RF_TEST_AUTH_ENABLED", default=True)
CLARO_RF_TEST_AUTH_USERNAME = os.environ.get("CLARO_RF_TEST_AUTH_USERNAME", "")
CLARO_RF_TEST_AUTH_PASSWORD = os.environ.get("CLARO_RF_TEST_AUTH_PASSWORD", "")

# The test release signs in with a local user. Core Connect SSO stays unused.
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"
MIDDLEWARE = [
    "claro_rf_check.test_auth.TestEnvironmentBasicAuthMiddleware",
    *[item for item in MIDDLEWARE if item != "users.middleware.IdentityRefreshMiddleware"],
]

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOGGING = build_json_logging(LOG_LEVEL)

CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "True").lower() in ("1", "true", "yes")
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"

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

install_thread_tasks()
