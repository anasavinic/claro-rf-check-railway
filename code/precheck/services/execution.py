"""Enqueue and run async Pre-check / Full Check executions."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from poscheck.services.errors import PoscheckError
from poscheck.services.orchestrator import (
    analysis_status_for_result,
    process_poscheck,
    worst_analysis_status,
)
from precheck.models import (
    CheckAnalysis,
    CheckAnalysisStatus,
    CheckExecution,
    CheckExecutionScope,
    CheckExecutionStage,
    CheckExecutionStatus,
    CheckType,
    PrecheckResultStatus,
)
from precheck.services.errors import PrecheckError, analysis_busy
from precheck.services.validator import process_precheck

logger = logging.getLogger("precheck.pipeline")

SAFE_STUCK_MESSAGE = "Processing stopped because it took too long. Try again."
SAFE_UNEXPECTED_MESSAGE = "Unexpected error while processing the check. Try again."


def selection_version_for(analysis: CheckAnalysis) -> str:
    payload = {
        "technology": analysis.technology,
        "site_name": analysis.site_name,
        "selected_cells": list(analysis.selected_cells or []),
        "pre_check": bool(analysis.pre_check),
        "full_check": bool(analysis.full_check),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def scope_for(analysis: CheckAnalysis) -> str:
    if analysis.pre_check and analysis.full_check:
        return CheckExecutionScope.BOTH
    if analysis.full_check:
        return CheckExecutionScope.FULL_CHECK
    return CheckExecutionScope.PRECHECK


def return_hashes_for(analysis: CheckAnalysis) -> tuple[str, str]:
    pre_hash = ""
    full_hash = ""
    for item in analysis.return_files.all():
        if item.check_type == CheckType.PRECHECK:
            pre_hash = item.content_sha256 or ""
        elif item.check_type == CheckType.FULL_CHECK:
            full_hash = item.content_sha256 or ""
    return pre_hash, full_hash


def _active_results_present(analysis: CheckAnalysis, scope: str) -> bool:
    from poscheck.models import PoscheckResult
    from precheck.models import PrecheckResult

    if scope in {CheckExecutionScope.PRECHECK, CheckExecutionScope.BOTH}:
        if not PrecheckResult.objects.filter(analysis=analysis).exists():
            return False
    if scope in {CheckExecutionScope.FULL_CHECK, CheckExecutionScope.BOTH}:
        # BOTH may stop after pre-check inconsistency without a pos result.
        if scope == CheckExecutionScope.FULL_CHECK and not PoscheckResult.objects.filter(analysis=analysis).exists():
            return False
        if scope == CheckExecutionScope.BOTH:
            pre = PrecheckResult.objects.filter(analysis=analysis).first()
            if pre is None:
                return False
            if pre.overall_status == PrecheckResultStatus.COMPLETED:
                return PoscheckResult.objects.filter(analysis=analysis).exists()
    return True


def build_process_response(execution: CheckExecution, *, created: bool) -> tuple[dict[str, Any], int]:
    """JSON payload + HTTP status for process endpoints (200 terminal / 202 queued)."""
    status_url = reverse("precheck:execution_status", kwargs={"execution_id": execution.id})
    if execution.status == CheckExecutionStatus.SUCCESS:
        title, message = "Analysis processed", "Check processing finished."
    elif execution.status == CheckExecutionStatus.FAILED:
        title = execution.error_title or "Could not process"
        message = "Check processing failed."
        payload = {
            "type": "Success" if execution.redirect_url else "Error",
            "title": title,
            "message": message,
            "status": execution.result_status or execution.status,
            "execution": execution_status_payload(execution),
            "status_url": status_url,
            "redirect_url": execution.redirect_url or "",
        }
        return payload, 200 if execution.redirect_url else 400
    elif created:
        title, message = "Analysis started", "Processing check…"
    else:
        title, message = "Analysis already started", "This check is already being processed."

    payload = {
        "type": "Success",
        "title": title,
        "message": message,
        "status": execution.result_status or execution.status,
        "execution": execution_status_payload(execution),
        "status_url": status_url,
        "redirect_url": execution.redirect_url or "",
    }
    status_code = 200 if execution.status in {CheckExecutionStatus.SUCCESS, CheckExecutionStatus.FAILED} else 202
    return payload, status_code


def execution_status_payload(execution: CheckExecution) -> dict[str, Any]:
    duration_ms = None
    if execution.started_at and execution.finished_at:
        duration_ms = int((execution.finished_at - execution.started_at).total_seconds() * 1000)
    return {
        "id": str(execution.id),
        "analysis_id": str(execution.analysis_id),
        "scope": execution.scope,
        "status": execution.status,
        "stage": execution.stage,
        "result_status": execution.result_status,
        "error_code": execution.error_code,
        "error_title": execution.error_title,
        "redirect_url": execution.redirect_url,
        "created_at": execution.created_at.isoformat() if execution.created_at else None,
        "started_at": execution.started_at.isoformat() if execution.started_at else None,
        "finished_at": execution.finished_at.isoformat() if execution.finished_at else None,
        "duration_ms": duration_ms,
    }


def enqueue_check_execution(analysis: CheckAnalysis, *, user=None) -> tuple[CheckExecution, bool]:
    """
    Create or reuse a CheckExecution for the current analysis inputs.

    Returns ``(execution, created)``.
    """
    scope = scope_for(analysis)
    selection = selection_version_for(analysis)
    pre_hash, full_hash = return_hashes_for(analysis)

    with transaction.atomic():
        locked = CheckAnalysis.objects.select_for_update().get(pk=analysis.pk)
        if locked.status == CheckAnalysisStatus.PROCESSING:
            active = (
                CheckExecution.objects.select_for_update()
                .filter(
                    analysis=locked,
                    status__in=[CheckExecutionStatus.PENDING, CheckExecutionStatus.PROCESSING],
                    scope=scope,
                    selection_version=selection,
                    pre_return_sha256=pre_hash,
                    full_return_sha256=full_hash,
                )
                .order_by("-created_at")
                .first()
            )
            if active is None:
                raise PrecheckError("Could not process", [analysis_busy()])
            return active, False

        existing_success = (
            CheckExecution.objects.filter(
                analysis=locked,
                status=CheckExecutionStatus.SUCCESS,
                scope=scope,
                selection_version=selection,
                pre_return_sha256=pre_hash,
                full_return_sha256=full_hash,
            )
            .order_by("-created_at")
            .first()
        )
        if existing_success is not None and _active_results_present(locked, scope):
            return existing_success, False

        existing_inflight = (
            CheckExecution.objects.select_for_update()
            .filter(
                analysis=locked,
                status__in=[CheckExecutionStatus.PENDING, CheckExecutionStatus.PROCESSING],
                scope=scope,
                selection_version=selection,
                pre_return_sha256=pre_hash,
                full_return_sha256=full_hash,
            )
            .order_by("-created_at")
            .first()
        )
        if existing_inflight is not None:
            return existing_inflight, False

        execution = CheckExecution.objects.create(
            analysis=locked,
            created_by=user if getattr(user, "is_authenticated", False) else None,
            scope=scope,
            status=CheckExecutionStatus.PENDING,
            stage=CheckExecutionStage.QUEUED,
            selection_version=selection,
            pre_return_sha256=pre_hash,
            full_return_sha256=full_hash,
        )
        locked.status = CheckAnalysisStatus.PROCESSING
        locked.save(update_fields=["status", "updated_at"])

    _log(
        execution,
        "check.enqueued",
        technology=analysis.technology,
        scope=scope,
        pre_return_sha256=pre_hash or None,
        full_return_sha256=full_hash or None,
    )
    return execution, True


def cancel_inflight_executions(analysis: CheckAnalysis, *, reason: str = "SUPERSEDED") -> int:
    """Mark pending/processing executions as failed when inputs change."""
    now = timezone.now()
    qs = CheckExecution.objects.filter(
        analysis=analysis,
        status__in=[CheckExecutionStatus.PENDING, CheckExecutionStatus.PROCESSING],
    )
    updated = 0
    for execution in qs:
        execution.status = CheckExecutionStatus.FAILED
        execution.stage = CheckExecutionStage.FAILED
        execution.error_code = reason
        execution.error_title = "Execution superseded"
        execution.finished_at = now
        execution.save(update_fields=["status", "stage", "error_code", "error_title", "finished_at"])
        _log(execution, "check.superseded", error_code=reason)
        updated += 1
    return updated


def run_check_execution(execution: CheckExecution, *, task_id: str = "") -> CheckExecution:
    started = time.monotonic()
    claimed = _claim(execution, task_id)
    if claimed is None:
        return execution
    if claimed.status == CheckExecutionStatus.SUCCESS:
        return claimed
    if claimed.status == CheckExecutionStatus.PROCESSING and claimed.task_id and task_id and claimed.task_id != task_id:
        return claimed

    execution = claimed
    analysis = execution.analysis
    _log(execution, "check.claimed", technology=analysis.technology)

    try:
        if not _inputs_still_match(execution):
            return _fail_execution(
                execution,
                title="Execution superseded",
                error_code="SUPERSEDED",
                analysis_status=CheckAnalysisStatus.AWAITING_RETURNS,
                started=started,
            )

        redirect_url, result_status = _orchestrate(execution, analysis)
        if not _inputs_still_match(execution):
            return _fail_execution(
                execution,
                title="Execution superseded",
                error_code="SUPERSEDED",
                analysis_status=CheckAnalysisStatus.AWAITING_RETURNS,
                started=started,
            )

        with transaction.atomic():
            locked = CheckExecution.objects.select_for_update().get(pk=execution.pk)
            if locked.status == CheckExecutionStatus.SUCCESS:
                return locked
            locked.status = CheckExecutionStatus.SUCCESS
            locked.stage = CheckExecutionStage.DONE
            locked.result_status = result_status
            locked.redirect_url = redirect_url
            locked.error_code = ""
            locked.error_title = ""
            locked.finished_at = timezone.now()
            locked.save(
                update_fields=[
                    "status",
                    "stage",
                    "result_status",
                    "redirect_url",
                    "error_code",
                    "error_title",
                    "finished_at",
                ]
            )
            execution = locked

        _log(
            execution,
            "check.succeeded",
            technology=analysis.technology,
            result_status=result_status,
            duration_ms=_elapsed(started),
        )
        return execution
    except (PrecheckError, PoscheckError) as exc:
        code = getattr(exc, "code", "CHECK_ERROR")
        if code == "ANALYSIS_BUSY":
            raise
        return _fail_execution(
            execution,
            title=exc.title,
            error_code=code,
            analysis_status=CheckAnalysisStatus.FAILED,
            started=started,
        )
    except Exception:
        logger.exception(
            "check.unexpected_failure",
            extra={
                "execution_id": str(execution.id),
                "analysis_id": str(execution.analysis_id),
                "correlation_id": str(execution.id),
            },
        )
        return _fail_execution(
            execution,
            title="Processing error",
            error_code="UNEXPECTED",
            analysis_status=CheckAnalysisStatus.FAILED,
            started=started,
            detail=SAFE_UNEXPECTED_MESSAGE,
        )


def _claim(execution: CheckExecution, task_id: str) -> CheckExecution | None:
    with transaction.atomic():
        locked = CheckExecution.objects.select_for_update().select_related("analysis").get(pk=execution.pk)
        if locked.status == CheckExecutionStatus.SUCCESS:
            return locked
        if locked.status == CheckExecutionStatus.FAILED and locked.stage == CheckExecutionStage.FAILED:
            return locked
        if (
            locked.status == CheckExecutionStatus.PROCESSING
            and locked.task_id
            and task_id
            and locked.task_id != task_id
        ):
            return locked
        locked.status = CheckExecutionStatus.PROCESSING
        locked.stage = CheckExecutionStage.READING
        locked.started_at = locked.started_at or timezone.now()
        locked.task_id = task_id or locked.task_id
        locked.error_code = ""
        locked.error_title = ""
        locked.save(update_fields=["status", "stage", "started_at", "task_id", "error_code", "error_title"])

        analysis = CheckAnalysis.objects.select_for_update().get(pk=locked.analysis_id)
        if analysis.status != CheckAnalysisStatus.PROCESSING:
            analysis.status = CheckAnalysisStatus.PROCESSING
            analysis.save(update_fields=["status", "updated_at"])
        return locked


def _inputs_still_match(execution: CheckExecution) -> bool:
    analysis = CheckAnalysis.objects.prefetch_related("return_files").get(pk=execution.analysis_id)
    if selection_version_for(analysis) != execution.selection_version:
        return False
    pre_hash, full_hash = return_hashes_for(analysis)
    return pre_hash == execution.pre_return_sha256 and full_hash == execution.full_return_sha256


def _set_stage(execution: CheckExecution, stage: str) -> None:
    CheckExecution.objects.filter(pk=execution.pk).update(stage=stage)
    execution.stage = stage


def _orchestrate(execution: CheckExecution, analysis: CheckAnalysis) -> tuple[str, str]:
    only_pre = execution.scope == CheckExecutionScope.PRECHECK
    only_full = execution.scope == CheckExecutionScope.FULL_CHECK
    both = execution.scope == CheckExecutionScope.BOTH

    _set_stage(execution, CheckExecutionStage.VALIDATING)

    if only_full:
        result = process_poscheck(
            analysis,
            manage_analysis_status=True,
            execution=execution,
            claim_analysis=False,
        )
        redirect_url = (
            reverse("poscheck:failure")
            if result.overall_status == PrecheckResultStatus.EXECUTION_FAILURE
            else reverse("poscheck:result")
        )
        return redirect_url, result.overall_status

    if only_pre:
        result = process_precheck(
            analysis,
            execution=execution,
            claim_analysis=False,
            manage_analysis_status=True,
        )
        tech = analysis.technology
        redirect_url = (
            reverse("precheck:failure", kwargs={"technology": tech})
            if result.overall_status == PrecheckResultStatus.EXECUTION_FAILURE
            else reverse("precheck:result", kwargs={"technology": tech})
        )
        return redirect_url, result.overall_status

    assert both
    pre_result = process_precheck(
        analysis,
        execution=execution,
        claim_analysis=False,
        manage_analysis_status=False,
    )
    tech = analysis.technology
    if pre_result.overall_status == PrecheckResultStatus.EXECUTION_FAILURE:
        analysis.refresh_from_db()
        analysis.status = CheckAnalysisStatus.FAILED
        analysis.save(update_fields=["status", "updated_at"])
        return reverse("precheck:failure", kwargs={"technology": tech}), pre_result.overall_status

    if pre_result.overall_status != PrecheckResultStatus.COMPLETED:
        analysis.refresh_from_db()
        analysis.status = analysis_status_for_result(pre_result.overall_status)
        analysis.save(update_fields=["status", "updated_at"])
        return reverse("precheck:result", kwargs={"technology": tech}), pre_result.overall_status

    pos_result = process_poscheck(
        analysis,
        manage_analysis_status=False,
        execution=execution,
        claim_analysis=False,
    )
    combined = worst_analysis_status(
        analysis_status_for_result(pre_result.overall_status),
        analysis_status_for_result(pos_result.overall_status),
    )
    analysis.refresh_from_db()
    if analysis.status != combined:
        analysis.status = combined
        analysis.save(update_fields=["status", "updated_at"])

    if pos_result.overall_status == PrecheckResultStatus.EXECUTION_FAILURE:
        return reverse("poscheck:failure"), pos_result.overall_status
    return reverse("poscheck:result"), pos_result.overall_status


def _fail_execution(
    execution: CheckExecution,
    *,
    title: str,
    error_code: str,
    analysis_status: str,
    started: float,
    detail: str = "",
) -> CheckExecution:
    with transaction.atomic():
        locked = CheckExecution.objects.select_for_update().get(pk=execution.pk)
        analysis = CheckAnalysis.objects.select_for_update().get(pk=locked.analysis_id)
        locked.status = CheckExecutionStatus.FAILED
        locked.stage = CheckExecutionStage.FAILED
        locked.error_code = error_code
        locked.error_title = title
        locked.result_status = PrecheckResultStatus.EXECUTION_FAILURE
        if error_code == "SUPERSEDED":
            locked.redirect_url = reverse("precheck:import_returns", kwargs={"technology": analysis.technology})
        elif locked.scope == CheckExecutionScope.FULL_CHECK:
            locked.redirect_url = reverse("poscheck:failure")
        else:
            locked.redirect_url = reverse("precheck:failure", kwargs={"technology": analysis.technology})
        locked.finished_at = timezone.now()
        locked.save(
            update_fields=[
                "status",
                "stage",
                "error_code",
                "error_title",
                "result_status",
                "redirect_url",
                "finished_at",
            ]
        )
        if analysis.status == CheckAnalysisStatus.PROCESSING:
            analysis.status = analysis_status
            analysis.save(update_fields=["status", "updated_at"])
        execution = locked

    _log(
        execution,
        "check.failed",
        error_code=error_code,
        duration_ms=_elapsed(started),
        detail=detail or None,
    )
    return execution


def _log(execution: CheckExecution, event: str, **fields) -> None:
    logger.info(
        event,
        extra={
            "execution_id": str(execution.id),
            "analysis_id": str(execution.analysis_id),
            "correlation_id": str(execution.id),
            "stage": execution.stage,
            "user_id": getattr(execution, "created_by_id", None),
            "status": execution.status,
            **{key: value for key, value in fields.items() if value is not None},
        },
    )


def _elapsed(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
