from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from celery.signals import beat_init
from django.conf import settings
from django.utils import timezone

from ep_import.models import ImportJob, ImportJobStatus, ImportStage
from ep_import.services.errors import SAFE_STUCK_MESSAGE, import_stuck
from ep_import.services.persist import process_job
from ep_import.services.retention import purge_expired_imports as purge_expired_jobs

logger = logging.getLogger("ep_import")


@shared_task(
    bind=True,
    name="ep_import.process_ep_import",
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=3,
    soft_time_limit=20 * 60,
    time_limit=25 * 60,
)
def process_ep_import(self, job_id: str) -> str:
    from ep_import.services.errors import TransientImportError

    job = ImportJob.objects.get(pk=job_id)
    if job.status == ImportJobStatus.SUCCESS:
        return str(job.id)
    try:
        process_job(job, task_id=self.request.id or "")
    except TransientImportError as exc:
        raise self.retry(exc=exc, countdown=min(300, 2**self.request.retries)) from exc
    return str(job.id)


@shared_task(name="ep_import.purge_expired_imports")
def purge_expired_imports() -> int:
    return purge_expired_jobs()


@shared_task(name="ep_import.reconcile_stuck_imports")
def reconcile_stuck_imports() -> int:
    seconds = int(getattr(settings, "EP_IMPORT_STUCK_AFTER_SECONDS", 25 * 60))
    cutoff = timezone.now() - timedelta(seconds=seconds)
    stuck = ImportJob.objects.filter(
        status__in=[ImportJobStatus.PENDING, ImportJobStatus.PROCESSING],
        created_at__lt=cutoff,
    )
    updated = 0
    for job in stuck:
        if job.status == ImportJobStatus.PROCESSING and job.started_at and job.started_at >= cutoff:
            continue
        job.status = ImportJobStatus.FAILED
        job.stage = ImportStage.FAILED
        job.error_title = "Import stopped"
        job.issues = [import_stuck().as_dict()]
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "stage", "error_title", "issues", "finished_at"])
        logger.info(
            "ep_import.reconciled",
            extra={"job_id": str(job.id), "stage": job.stage, "error_code": "IMPORT_STUCK", "user_id": None},
        )
        updated += 1
    if updated:
        logger.info("ep_import.reconciled_total", extra={"rows": updated, "message": SAFE_STUCK_MESSAGE})
    return updated


@beat_init.connect
def install_schedules_on_beat(**kwargs):
    try:
        ensure_ep_import_schedules()
    except Exception:
        logger.exception("ep_import.schedule_install_failed")


def ensure_ep_import_schedules() -> None:
    from django_celery_beat.models import IntervalSchedule, PeriodicTask

    hourly, _created = IntervalSchedule.objects.get_or_create(every=1, period=IntervalSchedule.HOURS)
    quarter, _created = IntervalSchedule.objects.get_or_create(every=15, period=IntervalSchedule.MINUTES)
    PeriodicTask.objects.update_or_create(
        name="ep_import.purge_expired_imports",
        defaults={"task": "ep_import.purge_expired_imports", "interval": hourly, "enabled": True},
    )
    PeriodicTask.objects.update_or_create(
        name="ep_import.reconcile_stuck_imports",
        defaults={"task": "ep_import.reconcile_stuck_imports", "interval": quarter, "enabled": True},
    )
