from __future__ import absolute_import, unicode_literals

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "claro_rf_check.settings.dev")

app = Celery("claro_rf_check")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.conf.beat_scheduler = "django_celery_beat.schedulers:DatabaseScheduler"
app.conf.broker_connection_retry_on_startup = True
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
