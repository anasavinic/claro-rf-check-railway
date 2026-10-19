"""Enqueue Combined RF check processing across child analyses."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from claro_rf_check.celery_dispatch import BROKER_UNAVAILABLE_CODE
from combined.services.combined import refresh_combined_status
from combined.services.results import has_comparable_results
from combined.services.returns import combined_return_ready
from precheck.models import (
    CheckAnalysisStatus,
    CheckExecution,
    CheckExecutionStatus,
    CombinedCheck,
)
from precheck.services.errors import PrecheckError, PrecheckIssue
from precheck.services.execution import (
    cancel_inflight_executions,
    dispatch_check_execution,
    enqueue_check_execution,
    mark_broker_dispatch_failed,
)


def _execution_is_orphan(execution: CheckExecution) -> bool:
    return not (execution.task_id or "").strip()


def _execution_is_timed_out(execution: CheckExecution) -> bool:
    seconds = int(getattr(settings, "CHECK_STUCK_AFTER_SECONDS", 12 * 60))
    anchor = execution.started_at or execution.created_at
    if anchor is None:
        return False
    return anchor <= timezone.now() - timedelta(seconds=seconds)


def _analysis_needs_recovery(analysis, inflight: list[CheckExecution]) -> bool:
    """Recover only orphan or timed-out work — never cancel a live Celery job."""
    if not inflight:
        return analysis.status == CheckAnalysisStatus.PROCESSING
    return any(_execution_is_orphan(item) or _execution_is_timed_out(item) for item in inflight)


def recover_stuck_analyses(combined: CombinedCheck) -> int:
    """Reset orphan or timed-out child analyses without aborting healthy in-flight jobs."""
    recovered = 0
    for analysis in combined.analyses.all():
        inflight = list(
            analysis.executions.filter(
                status__in=[
                    CheckExecutionStatus.PENDING,
                    CheckExecutionStatus.PROCESSING,
                ]
            )
        )
        if not _analysis_needs_recovery(analysis, inflight):
            continue
        cancel_inflight_executions(analysis, reason="STUCK_RECOVERED")
        if analysis.status != CheckAnalysisStatus.AWAITING_RETURNS:
            analysis.status = CheckAnalysisStatus.AWAITING_RETURNS
            analysis.save(update_fields=["status", "updated_at"])
        recovered += 1
    if recovered and combined.status == CheckAnalysisStatus.PROCESSING:
        still_busy = combined.analyses.filter(status=CheckAnalysisStatus.PROCESSING).exists()
        if not still_busy:
            combined.status = CheckAnalysisStatus.AWAITING_RETURNS
            combined.save(update_fields=["status", "updated_at"])
    return recovered


def enqueue_combined_execution(
    combined: CombinedCheck,
    *,
    user: AbstractBaseUser | None = None,
) -> list[CheckExecution]:
    if not combined_return_ready(combined):
        raise PrecheckError(
            "Could not process",
            [
                PrecheckIssue(
                    code="MISSING_RETURNS",
                    message="Import all required return files before processing.",
                )
            ],
        )

    recover_stuck_analyses(combined)
    combined.refresh_from_db()

    analyses = list(combined.analyses.select_related("ep_job").order_by("technology", "site_name"))
    if not analyses:
        raise PrecheckError(
            "Could not process",
            [
                PrecheckIssue(
                    code="NO_ANALYSES",
                    message="No analyses found for this combined check.",
                )
            ],
        )

    if any(a.status == CheckAnalysisStatus.PROCESSING for a in analyses):
        raise PrecheckError(
            "Could not process",
            [
                PrecheckIssue(
                    code="ANALYSIS_BUSY",
                    message="This analysis is already being updated. Try again in a moment.",
                )
            ],
        )

    # Enqueue each child outside a long outer transaction so Celery can claim rows
    # after each commit, avoiding stuck PROCESSING / ANALYSIS_BUSY races.
    executions: list[CheckExecution] = []
    to_delay: list[CheckExecution] = []
    for analysis in analyses:
        execution, created = enqueue_check_execution(analysis, user=user)
        executions.append(execution)
        if created or (execution.status == CheckExecutionStatus.PENDING and not execution.task_id):
            to_delay.append(execution)

    with transaction.atomic():
        locked = CombinedCheck.objects.select_for_update().get(pk=combined.pk)
        locked.status = CheckAnalysisStatus.PROCESSING
        locked.save(update_fields=["status", "updated_at"])

    for index, execution in enumerate(to_delay):
        try:
            dispatch_check_execution(execution)
        except PrecheckError as exc:
            if exc.code != BROKER_UNAVAILABLE_CODE:
                raise
            for remaining in to_delay[index + 1 :]:
                mark_broker_dispatch_failed(remaining)
            with transaction.atomic():
                locked = CombinedCheck.objects.select_for_update().get(pk=combined.pk)
                if locked.status == CheckAnalysisStatus.PROCESSING:
                    locked.status = CheckAnalysisStatus.FAILED
                    locked.save(update_fields=["status", "updated_at"])
            raise

    return executions


def combined_process_status(combined: CombinedCheck) -> dict:
    """Aggregate child execution state for polling."""
    refresh_combined_status(combined)
    analyses = list(combined.analyses.prefetch_related("executions"))
    total = len(analyses)
    done = 0
    failed = 0
    processing = 0
    for analysis in analyses:
        latest = analysis.executions.order_by("-created_at").first()
        if analysis.status == CheckAnalysisStatus.PROCESSING or (
            latest and latest.status in {CheckExecutionStatus.PENDING, CheckExecutionStatus.PROCESSING}
        ):
            processing += 1
        elif analysis.status in {
            CheckAnalysisStatus.COMPLETED,
            CheckAnalysisStatus.INCONSISTENT,
            CheckAnalysisStatus.FAILED,
        }:
            done += 1
            if analysis.status == CheckAnalysisStatus.FAILED:
                failed += 1
        elif latest and latest.status == CheckExecutionStatus.FAILED:
            done += 1
            failed += 1
        elif latest and latest.status == CheckExecutionStatus.SUCCESS:
            done += 1

    finished = processing == 0 and done == total and total > 0
    redirect_url = ""
    if finished:
        parse_failed = (combined.status == CheckAnalysisStatus.FAILED or failed) and not has_comparable_results(
            combined
        )
        redirect_url = reverse("combined:failure") if parse_failed else reverse("combined:result")

    return {
        "combined_id": str(combined.id),
        "status": combined.status,
        "total": total,
        "done": done,
        "failed": failed,
        "processing": processing,
        "finished": finished,
        "redirect_url": redirect_url,
    }
