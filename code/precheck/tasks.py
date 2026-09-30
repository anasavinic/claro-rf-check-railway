from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from celery.signals import beat_init
from django.conf import settings
from django.utils import timezone

from precheck.models import (
    CheckAnalysis,
    CheckAnalysisStatus,
    CheckExecution,
    CheckExecutionStage,
    CheckExecutionStatus,
)
from precheck.services.execution import SAFE_STUCK_MESSAGE, run_check_execution

logger = logging.getLogger("precheck.pipeline")


@shared_task(
    bind=True,
    name="precheck.process_check_execution",
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=3,
    soft_time_limit=10 * 60,
    time_limit=12 * 60,
)
def process_check_execution(self, execution_id: str) -> str:
    execution = CheckExecution.objects.select_related("analysis").get(pk=execution_id)
    if execution.status == CheckExecutionStatus.SUCCESS:
        return str(execution.id)
    run_check_execution(execution, task_id=self.request.id or "")
    return str(execution.id)


@shared_task(name="precheck.reconcile_stuck_check_executions")
def reconcile_stuck_check_executions() -> int:
    seconds = int(getattr(settings, "CHECK_STUCK_AFTER_SECONDS", 12 * 60))
    cutoff = timezone.now() - timedelta(seconds=seconds)
    stuck = CheckExecution.objects.filter(
        status__in=[CheckExecutionStatus.PENDING, CheckExecutionStatus.PROCESSING],
        created_at__lt=cutoff,
    ).select_related("analysis")
    updated = 0
    for execution in stuck:
        if (
            execution.status == CheckExecutionStatus.PROCESSING
            and execution.started_at
            and execution.started_at >= cutoff
        ):
            continue
        execution.status = CheckExecutionStatus.FAILED
        execution.stage = CheckExecutionStage.FAILED
        execution.error_code = "CHECK_STUCK"
        execution.error_title = "Processing stopped"
        execution.finished_at = timezone.now()
        execution.save(update_fields=["status", "stage", "error_code", "error_title", "finished_at"])
        analysis = execution.analysis
        if analysis.status == CheckAnalysisStatus.PROCESSING:
            analysis.status = CheckAnalysisStatus.FAILED
            analysis.save(update_fields=["status", "updated_at"])
        logger.info(
            "check.reconciled",
            extra={
                "execution_id": str(execution.id),
                "analysis_id": str(execution.analysis_id),
                "correlation_id": str(execution.id),
                "stage": execution.stage,
                "error_code": "CHECK_STUCK",
                "user_id": None,
            },
        )
        updated += 1
    if updated:
        logger.info(
            "check.reconciled_total",
            extra={"rows": updated, "message": SAFE_STUCK_MESSAGE},
        )
    return updated


@beat_init.connect
def install_schedules_on_beat(**kwargs):
    try:
        ensure_check_execution_schedules()
    except Exception:
        logger.exception("check.schedule_install_failed")


def ensure_check_execution_schedules() -> None:
    from django_celery_beat.models import IntervalSchedule, PeriodicTask

    quarter, _created = IntervalSchedule.objects.get_or_create(every=15, period=IntervalSchedule.MINUTES)
    PeriodicTask.objects.update_or_create(
        name="precheck.reconcile_stuck_check_executions",
        defaults={
            "task": "precheck.reconcile_stuck_check_executions",
            "interval": quarter,
            "enabled": True,
        },
    )
