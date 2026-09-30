from django.apps import AppConfig


class EpImportConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ep_import"
    verbose_name = "EP Import"

    def ready(self):
        from django.apps import apps
        from django.db.models.signals import post_migrate

        post_migrate.connect(
            _install_schedules_after_beat,
            sender=apps.get_app_config("django_celery_beat"),
        )
        from django.conf import settings

        from ep_import import tasks

        tasks.process_ep_import.soft_time_limit = settings.EP_IMPORT_SOFT_TIME_LIMIT
        tasks.process_ep_import.time_limit = settings.EP_IMPORT_TIME_LIMIT


def _install_schedules_after_beat(sender, **kwargs):
    try:
        from ep_import.tasks import ensure_ep_import_schedules

        ensure_ep_import_schedules()
    except Exception:
        # Beat tables may not exist yet on the first migrate.
        return
