"""Local desktop settings for the Windows executable.

SQLite and uploads live under %LOCALAPPDATA%\\Claro RF Check. There is no
Postgres, Redis, object storage, or Core Connect SSO.
"""

import os
import sys
from pathlib import Path

os.environ["USE_OBS_MEDIA"] = "False"
os.environ.setdefault("SECRET_KEY", "claro-rf-check-desktop")

from django.db.backends.signals import connection_created

from claro_rf_check.railway_tasks import install_thread_tasks

from .base import *  # noqa: F401, F403
from .base import REST_FRAMEWORK, STORAGES

DESKTOP_MODE = True
DEBUG = False

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys._MEIPASS)

_appdata = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Claro RF Check"
_appdata.mkdir(parents=True, exist_ok=True)
(_appdata / "media").mkdir(exist_ok=True)
(_appdata / "logs").mkdir(exist_ok=True)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": _appdata / "db.sqlite3",
        "OPTIONS": {"timeout": 30},
    }
}

ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
CSRF_TRUSTED_ORIGINS = ["http://127.0.0.1", "http://localhost"]

MEDIA_URL = "/media/"
MEDIA_ROOT = _appdata / "media"
USE_OBS_MEDIA = False
STORAGES["default"] = {"BACKEND": "django.core.files.storage.FileSystemStorage"}
STORAGES["staticfiles"] = {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"}
# Star-import from base leaves STATICFILES_STORAGE set. Django then refuses to
# boot because that name and STORAGES cannot both be set, so the window's
# local server never opens.
STATICFILES_STORAGE = None
del STATICFILES_STORAGE
STATICFILES_DIRS = [BASE_DIR / "static"]
WHITENOISE_USE_FINDERS = True

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "claro-rf-desktop",
    }
}

CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_EAGER_PROPAGATES = False
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]
LOGIN_URL = "/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework.authentication.SessionAuthentication",),
}

_middleware = [item for item in MIDDLEWARE if item != "users.middleware.IdentityRefreshMiddleware"]
_auth_index = _middleware.index("django.contrib.auth.middleware.AuthenticationMiddleware")
_middleware.insert(_auth_index + 1, "claro_rf_check.desktop_auth.DesktopAutoLoginMiddleware")
MIDDLEWARE = _middleware

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "file": {
            "class": "logging.FileHandler",
            "filename": str(_appdata / "logs" / "django.log"),
            "encoding": "utf-8",
        }
    },
    "root": {"handlers": ["file"], "level": "INFO"},
}


def _enable_sqlite_wal(sender, connection, **kwargs):
    if connection.vendor != "sqlite":
        return
    cursor = connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL;")
    except Exception:
        # WAL is refused when AppData is redirected to a network folder.
        # The file still works with the default rollback journal.
        pass
    try:
        cursor.execute("PRAGMA busy_timeout=30000;")
    except Exception:
        return


connection_created.connect(_enable_sqlite_wal)
install_thread_tasks()
