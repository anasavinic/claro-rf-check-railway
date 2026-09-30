"""
Settings for automated tests (local pytest + GitLab CI).

Uses in-memory SQLite and locmem cache so pipelines do not need Postgres/Redis.
"""

import os

# Must be set before importing base (SECRET_KEY fail-fast, no MinIO).
os.environ["USE_OBS_MEDIA"] = "False"
os.environ.setdefault("SECRET_KEY", "ci-only-insecure-secret-key")  # pragma: allowlist secret
os.environ.setdefault("DEBUG", "True")

from .base import *  # noqa: E402, F401, F403

DEBUG = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "ci-tests",
    }
}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

USE_OBS_MEDIA = False
# Django 5.1 rejects STATICFILES_STORAGE together with STORAGES.
STATICFILES_STORAGE = None
del STATICFILES_STORAGE
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# Offline SSO for unit tests (no live IdP).
CORE_CONNECT_SSO_DEV = True
CORE_CONNECT_SSO_ENVIRONMENT = "development"
CORE_CONNECT_SSO_ISSUER = "http://localhost:8001"
CORE_CONNECT_SSO_CLIENT_ID = "claro-rf"
CORE_CONNECT_SSO_REDIRECT_URI = "http://localhost:8007/claro-rf/sso/callback/"
CORE_CONNECT_SSO_ALLOW_INSECURE_TRANSPORT = True
