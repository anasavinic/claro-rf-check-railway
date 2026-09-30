"""Enqueue Combined RF check processing across child analyses."""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.urls import reverse

from combined.services.combined import refresh_combined_status
from combined.services.returns import combined_return_ready
from precheck.models import (
    CheckAnalysisStatus,
    CheckExecution,
    CheckExecutionStatus,
    CombinedCheck,
)
from precheck.services.errors import PrecheckError, PrecheckIssue
from precheck.services.execution import cancel_inflight_executions, enqueue_check_execution
from precheck.tasks import process_check_execution


def recover_stuck_analyses(combined: CombinedCheck) -> int:
    """Reset child analyses stuck in PROCESSING, including orphan inflight executions."""
    recovered = 0
    for analysis in combined.analyses.all():
        inflight = list(
            analysis.executions.filter(status__in=[CheckExecutionStatus.PENDING, CheckExecutionStatus.PROCESSING])
        )
        stuck = analysis.status == CheckAnalysisStatus.PROCESSING
        orphan = any(not (execution.task_id or "").strip() for execution in inflight)
        if not stuck and not orphan and not inflight:
            continue
        if stuck or orphan:
            cancel_inflight_executions(analysis, reason="STUCK_RECOVERED")
            if analysis.status != CheckAnalysisStatus.AWAITING_RETURNS:
                analysis.status = CheckAnalysisStatus.AWAITING_RETURNS
                analysis.save(update_fields=["status", "updated_at"])
            recovered += 1
    if recovered and combined.status == CheckAnalysisStatus.PROCESSING:
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
            [PrecheckIssue(code="NO_ANALYSES", message="No analyses found for this combined check.")],
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

    for execution in to_delay:
        process_check_execution.delay(str(execution.id))

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
        if combined.status == CheckAnalysisStatus.FAILED or failed:
            redirect_url = reverse("combined:failure")
        else:
            redirect_url = reverse("combined:result")

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
