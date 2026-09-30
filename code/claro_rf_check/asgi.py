import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "claro_rf_check.settings.dev")

application = get_asgi_application()
