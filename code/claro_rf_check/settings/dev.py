import os
import socket

from .base import *  # noqa: F401, F403

DEBUG = True

# Serve JS/CSS from STATICFILES_DIRS without hashed collectstatic.
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"
STORAGES = {
    **STORAGES,
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True
WHITENOISE_MAX_AGE = 0

_allowed = [host.strip() for host in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if host.strip()]
ALLOWED_HOSTS = _allowed or ["localhost", "127.0.0.1"]

INSTALLED_APPS = [
    *INSTALLED_APPS,
    "debug_toolbar",
    "django_browser_reload",
]
MIDDLEWARE = [
    "debug_toolbar.middleware.DebugToolbarMiddleware",
    *MIDDLEWARE,
    "django_browser_reload.middleware.BrowserReloadMiddleware",
]

INTERNAL_IPS = ["127.0.0.1", "10.0.2.2"]
try:
    _, _, _ips = socket.gethostbyname_ex(socket.gethostname())
    INTERNAL_IPS += [ip[: ip.rfind(".")] + ".1" for ip in _ips if "." in ip]
except OSError:
    pass

DEBUG_TOOLBAR_CONFIG = {
    "SHOW_TOOLBAR_CALLBACK": lambda request: True,
}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

if os.getenv("OS") == "docker":
    if os.getenv("DEBUG_CELERY", "").lower() == "true":
        CELERY_TASK_ALWAYS_EAGER = False
        CELERY_TASK_EAGER_PROPAGATES = False

    if os.getenv("DEBUG_PYCHARM", "").lower() == "true":
        try:
            import pydevd_pycharm

            pydevd_pycharm.settrace(
                "host.docker.internal",
                port=5678,
                suspend=False,
                patch_multiprocessing=True,
            )
            print("PyCharm Debugger connected.")
        except ConnectionRefusedError:
            print("---------- PyCharm: Please, enable remote python debug!")

    if os.getenv("DEBUG_VSCODE", "").lower() == "true":
        try:
            import debugpy

            if not os.getenv("RUN_MAIN"):
                debugpy.listen(("0.0.0.0", 5679))
                print("Waiting for debugger attach...")
                debugpy.wait_for_client()
        except OSError as e:
            print(f"VSCode debug error: {e} (port might be in use?)")
        except Exception:
            print("VSCODE Debugger not connected!")
