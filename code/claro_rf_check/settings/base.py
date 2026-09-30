"""
Django settings for the Claro RF Check project.

Defaults match the Core Connect contract: ``SECRET_KEY`` is required, object
storage is opt-in, and staging/production harden cookies and hosts.
"""

import os
from pathlib import Path
from shutil import which

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = (os.getenv("SECRET_KEY") or os.getenv("DJANGO_SECRET_KEY") or "").strip()
if not SECRET_KEY:
    raise ImproperlyConfigured(
        "SECRET_KEY (or DJANGO_SECRET_KEY) environment variable is required and must be non-empty."
    )

DEBUG = os.getenv("DEBUG", "FALSE") == "True"

ALLOWED_HOSTS = ["*"]


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in ("1", "true", "yes", "on")


# --- Core Connect SSO (browser relying party) ---
CORE_CONNECT_SSO_ISSUER = os.environ.get("CORE_CONNECT_SSO_ISSUER") or ""
CORE_CONNECT_SSO_INTERNAL_ISSUER = os.environ.get("CORE_CONNECT_SSO_INTERNAL_ISSUER") or None
CORE_CONNECT_SSO_CLIENT_ID = os.environ.get("CORE_CONNECT_SSO_CLIENT_ID") or ""
CORE_CONNECT_SSO_REDIRECT_URI = os.environ.get("CORE_CONNECT_SSO_REDIRECT_URI") or ""
CORE_CONNECT_SSO_SCOPES = os.environ.get(
    "CORE_CONNECT_SSO_SCOPES",
    "openid profile email",
)
CORE_CONNECT_SSO_ALLOW_INSECURE_TRANSPORT = env_bool(
    "CORE_CONNECT_SSO_ALLOW_INSECURE_TRANSPORT",
)
CORE_CONNECT_SSO_ENVIRONMENT = os.environ.get("CORE_CONNECT_SSO_ENVIRONMENT") or ""
_raw_sso_dev = os.environ.get("CORE_CONNECT_SSO_DEV")
CORE_CONNECT_SSO_DEV = None if _raw_sso_dev is None else env_bool("CORE_CONNECT_SSO_DEV")
CORE_CONNECT_SSO_USER_MAPPER = "users.sso.map_core_connect_identity"
CORE_CONNECT_SSO_AUTH_BACKEND = "users.backends.CoreConnectBackend"
CORE_CONNECT_SSO_LOGIN_REDIRECT_URL = os.environ.get(
    "CORE_CONNECT_SSO_LOGIN_REDIRECT_URL",
    "/",
)
CORE_CONNECT_SSO_LOGOUT_REDIRECT_URL = os.environ.get(
    "CORE_CONNECT_SSO_LOGOUT_REDIRECT_URL",
    "/claro-rf/sso/login/",
)
CORE_CONNECT_SSO_REFRESH_FAILURE_ACTION = "logout"

LOGIN_URL = "/claro-rf/sso/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/claro-rf/sso/login/"

INTERNAL_IPS = ["127.0.0.1"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_celery_beat",
    "django_htmx",
    "tailwind",
    "theme",
    "users",
    "home",
    "ep_import",
    "precheck",
    "poscheck",
    "reports",
    "combined",
]

TAILWIND_APP_NAME = "theme"
NPM_BIN_PATH = which("npm") or which("npm.cmd")

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "users.middleware.IdentityRefreshMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "claro_rf_check.middleware.SecurityHeadersMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "DEFAULT_AUTHENTICATION_CLASSES": ("users.authentication.CoreConnectSessionAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
}

ROOT_URLCONF = "claro_rf_check.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "claro_rf_check.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "claro_rf_check"),
        "USER": os.getenv("POSTGRES_USER", "postgres"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
        "HOST": os.getenv("DB_HOST", "postgres"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
}

AUTH_USER_MODEL = "users.User"
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",  # Local Django admin maintenance accounts.
    CORE_CONNECT_SSO_AUTH_BACKEND,
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
WHITENOISE_MAX_AGE = int(os.getenv("WHITENOISE_MAX_AGE", str(60 * 60 * 24 * 365)))

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# EP regionals can exceed Django's default 2.5MB request limit. Keep the request
# cap at 50MB, but spool the file to disk above the default in-memory threshold.
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = int(os.getenv("FILE_UPLOAD_MAX_MEMORY_SIZE", str(2_621_440)))

EP_IMPORT_RETENTION_DAYS = int(os.getenv("EP_IMPORT_RETENTION_DAYS", "15"))
EP_IMPORT_SOFT_TIME_LIMIT = int(os.getenv("EP_IMPORT_SOFT_TIME_LIMIT", str(20 * 60)))
EP_IMPORT_TIME_LIMIT = int(os.getenv("EP_IMPORT_TIME_LIMIT", str(25 * 60)))
EP_IMPORT_STUCK_AFTER_SECONDS = int(os.getenv("EP_IMPORT_STUCK_AFTER_SECONDS", str(25 * 60)))
EP_IMPORT_UPLOAD_RATE_LIMIT = int(os.getenv("EP_IMPORT_UPLOAD_RATE_LIMIT", "20"))
EP_IMPORT_UPLOAD_RATE_WINDOW = int(os.getenv("EP_IMPORT_UPLOAD_RATE_WINDOW", str(60 * 60)))

CHECK_SOFT_TIME_LIMIT = int(os.getenv("CHECK_SOFT_TIME_LIMIT", str(10 * 60)))
CHECK_TIME_LIMIT = int(os.getenv("CHECK_TIME_LIMIT", str(12 * 60)))
CHECK_STUCK_AFTER_SECONDS = int(os.getenv("CHECK_STUCK_AFTER_SECONDS", str(12 * 60)))

# Object storage (MinIO locally / Huawei OBS in staging-prod). When False, use MEDIA_ROOT.
USE_OBS_MEDIA = os.getenv("USE_OBS_MEDIA", "False") == "True"
OBS_BUCKET_NAME = (os.getenv("OBS_BUCKET_NAME") or "").strip()
OBS_ENDPOINT = (os.getenv("OBS_ENDPOINT") or "").strip()
OBS_ACCESS_KEY = (os.getenv("OBS_ACCESS_KEY") or "").strip()
OBS_SECRET_KEY = (os.getenv("OBS_SECRET_KEY") or "").strip()
OBS_CUSTOM_DOMAIN = (os.getenv("OBS_CUSTOM_DOMAIN") or "").strip()
OBS_PUBLIC_ENDPOINT = (os.getenv("OBS_PUBLIC_ENDPOINT") or "").strip()
OBS_URL_PROTOCOL = (os.getenv("OBS_URL_PROTOCOL") or "").strip()
# MinIO in Docker needs path-style (bucket is not a DNS subdomain). OBS cloud uses virtual.
_OBS_ADDRESSING_STYLE = (os.getenv("OBS_ADDRESSING_STYLE") or "virtual").strip().lower()
OBS_ADDRESSING_STYLE = _OBS_ADDRESSING_STYLE if _OBS_ADDRESSING_STYLE in {"path", "virtual"} else "virtual"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

if USE_OBS_MEDIA:
    from botocore.config import Config

    if not all([OBS_BUCKET_NAME, OBS_ENDPOINT, OBS_ACCESS_KEY, OBS_SECRET_KEY]):
        raise ImproperlyConfigured(
            "USE_OBS_MEDIA=True requires OBS_BUCKET_NAME, OBS_ENDPOINT, OBS_ACCESS_KEY, and OBS_SECRET_KEY."
        )

    def _obs_public_endpoint():
        if OBS_PUBLIC_ENDPOINT:
            return OBS_PUBLIC_ENDPOINT.rstrip("/")
        if not OBS_CUSTOM_DOMAIN:
            return ""
        host = OBS_CUSTOM_DOMAIN.split("/", 1)[0].strip()
        if not host:
            return ""
        proto = OBS_URL_PROTOCOL or ("http:" if "localhost" in host or host.startswith("127.") else "https:")
        return f"{proto.rstrip(':')}://{host}"

    _public_endpoint = _obs_public_endpoint()
    _s3_options = {
        "access_key": OBS_ACCESS_KEY,
        "secret_key": OBS_SECRET_KEY,
        "bucket_name": OBS_BUCKET_NAME,
        "endpoint_url": OBS_ENDPOINT,
        "addressing_style": OBS_ADDRESSING_STYLE,
        "default_acl": None,
        "querystring_auth": True,
        "file_overwrite": False,
        "signature_version": "s3v4",
        "querystring_expire": int(os.getenv("OBS_URL_EXPIRE_SECONDS", "3600")),
        "object_parameters": {"CacheControl": "public, max-age=86400"},
        "client_config": Config(
            signature_version="s3v4",
            request_checksum_calculation="WHEN_REQUIRED",
            response_checksum_validation="WHEN_REQUIRED",
            s3={"addressing_style": OBS_ADDRESSING_STYLE},
        ),
    }
    if _public_endpoint:
        _s3_options["public_endpoint_url"] = _public_endpoint

    STORAGES["default"] = {
        "BACKEND": "claro_rf_check.storage.OBSMediaStorage",
        "OPTIONS": _s3_options,
    }
    AWS_S3_ADDRESSING_STYLE = OBS_ADDRESSING_STYLE
    AWS_S3_SIGNATURE_VERSION = "s3v4"
    if OBS_CUSTOM_DOMAIN:
        proto = (OBS_URL_PROTOCOL or ("http:" if "localhost" in OBS_CUSTOM_DOMAIN else "https:")).rstrip(":")
        MEDIA_URL = f"{proto}://{OBS_CUSTOM_DOMAIN.rstrip('/')}/"
    elif _public_endpoint:
        MEDIA_URL = f"{_public_endpoint}/{OBS_BUCKET_NAME}/"
    else:
        MEDIA_URL = f"{OBS_ENDPOINT.rstrip('/')}/{OBS_BUCKET_NAME}/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


def _env_bool(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "mailpit")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "1025"))
EMAIL_USE_TLS = _env_bool("EMAIL_USE_TLS", default=False)
EMAIL_USE_SSL = _env_bool("EMAIL_USE_SSL", default=False)
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "claro-rf-check@localhost")

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/0")

CACHE_REDIS_URL = (os.getenv("CACHE_REDIS_URL", "redis://redis:6379/1") or "").strip()
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": CACHE_REDIS_URL,
    }
}

CELERY_TASK_ALWAYS_EAGER = os.getenv("CELERY_TASK_ALWAYS_EAGER", "false").lower() in (
    "1",
    "true",
    "yes",
    "on",
)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_WORKER_CONCURRENCY = int(os.getenv("CELERY_WORKER_CONCURRENCY", "2") or 2)

# Session cookies (SSO-friendly names; secure flags tightened in staging/production)
SESSION_COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "claro_rf_check_sessionid")
CSRF_COOKIE_NAME = os.environ.get("CSRF_COOKIE_NAME", "claro_rf_check_csrftoken")
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", default=False)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", default=False)
