"""Staging settings — same hardening as production, explicit environment label.

Use ``DJANGO_SETTINGS_MODULE=claro_rf_check.settings.staging`` for staging
deploys (``.env.staging``, Compose staging).

``DEBUG`` stays False; ``ALLOWED_HOSTS`` / TLS cookie rules match production.
"""

from .production import *  # noqa: F401, F403
from .secure import apply_secure_settings

ENVIRONMENT = "staging"

apply_secure_settings(globals())
