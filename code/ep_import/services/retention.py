"""Delete expired EP files, jobs, and cells. Idempotent."""

from __future__ import annotations

import logging

from django.utils import timezone

from ep_import.models import ImportJob

logger = logging.getLogger("ep_import")


def purge_expired_imports() -> int:
    now = timezone.now()
    removed = 0
    for job in ImportJob.objects.filter(expires_at__lt=now).iterator():
        job_id = str(job.id)
        # Analyses PROTECT the job FK — remove them (and cascaded returns/results) first.
        job.check_analyses.all().delete()
        _delete_stored_file(job)
        job.delete()
        removed += 1
        logger.info(
            "ep_import.purged",
            extra={"job_id": job_id, "correlation_id": job_id, "stage": "cleanup", "user_id": None},
        )
    return removed


def _delete_stored_file(job: ImportJob) -> None:
    name = job.stored_file.name
    if not name:
        return
    try:
        job.stored_file.delete(save=False)
    except Exception:
        logger.exception(
            "ep_import.cleanup_file_failed",
            extra={
                "job_id": str(job.id),
                "correlation_id": str(job.id),
                "stage": "cleanup",
                "error_code": "CLEANUP_FAILED",
            },
        )
