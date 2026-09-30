from django.apps import AppConfig


class CombinedConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "combined"
    verbose_name = "Combined RF Check"
