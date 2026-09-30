from django.apps import AppConfig


class PrecheckConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "precheck"
    verbose_name = "5G Pre-check"

    def ready(self):
        from django.apps import apps
        from django.db.models.signals import post_migrate

        post_migrate.connect(
            _install_schedules_after_beat,
            sender=apps.get_app_config("django_celery_beat"),
        )
        from django.conf import settings

        from precheck import tasks

        tasks.process_check_execution.soft_time_limit = settings.CHECK_SOFT_TIME_LIMIT
        tasks.process_check_execution.time_limit = settings.CHECK_TIME_LIMIT


def _install_schedules_after_beat(sender, **kwargs):
    try:
        from precheck.tasks import ensure_check_execution_schedules

        ensure_check_execution_schedules()
    except Exception:
        # Beat tables may not exist yet on the first migrate.
        return
