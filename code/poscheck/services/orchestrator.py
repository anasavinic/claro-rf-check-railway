"""Orchestrate Full Check processing across technologies."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from poscheck.models import PoscheckResult
from poscheck.services.errors import (
    PoscheckError,
    PoscheckParseError,
    analysis_busy,
    full_check_not_selected,
    missing_full_check_return_file,
)
from poscheck.services.registry import get_engine
from poscheck.services.tech.g2.validator import PoscheckOutcome as G2Outcome
from poscheck.services.tech.g3.validator import (
    VALIDATION_STATUS_CONSISTENT,
    VALIDATION_STATUS_FAILED,
    VALIDATION_STATUS_INCONSISTENT,
)
from poscheck.services.tech.g3.validator import PoscheckOutcome as G3Outcome
from poscheck.services.tech.g5.validator import PoscheckOutcome as G5Outcome
from precheck.models import CheckAnalysis, CheckAnalysisStatus, CheckReturnFile, CheckType, PrecheckResultStatus

PoscheckOutcome = G2Outcome | G3Outcome | G5Outcome


def process_poscheck(
    analysis: CheckAnalysis,
    *,
    return_text: str | None = None,
    return_bytes: bytes | None = None,
    manage_analysis_status: bool = True,
    execution=None,
    claim_analysis: bool = True,
) -> PoscheckResult:
    """Run Full Check, persist ``PoscheckResult``, and optionally sync analysis status.

    Heavy I/O and CPU run outside the DB lock. Only claim and persist use short transactions.
    """
    if claim_analysis:
        with transaction.atomic():
            locked = CheckAnalysis.objects.select_for_update().get(pk=analysis.pk)
            if locked.status == CheckAnalysisStatus.PROCESSING and manage_analysis_status:
                raise PoscheckError("Could not process", [analysis_busy()])
            if manage_analysis_status:
                locked.status = CheckAnalysisStatus.PROCESSING
                locked.save(update_fields=["status", "updated_at"])
            analysis = locked

    try:
        outcome = _evaluate_from_inputs(analysis, return_text=return_text, return_bytes=return_bytes)
    except (PoscheckParseError, PoscheckError) as exc:
        outcome = _failure_outcome(exc)

    with transaction.atomic():
        locked = CheckAnalysis.objects.select_for_update().get(pk=analysis.pk)
        result = _persist_outcome(locked, outcome, execution=execution)
        if manage_analysis_status:
            locked.status = _analysis_status_for(outcome.overall_status)
            locked.save(update_fields=["status", "updated_at"])
    return result


def evaluate_poscheck(analysis: CheckAnalysis, return_text: str) -> PoscheckOutcome:
    engine = get_engine(analysis.technology)
    if not engine.supported(analysis):
        raise PoscheckError("Execution failure", [full_check_not_selected()])
    extraction = engine.parse_return(return_text)
    expected = engine.resolve_expected(analysis)
    return engine.compare(expected, extraction)


def get_poscheck_snapshot(analysis_id: UUID | str) -> dict[str, Any] | None:
    try:
        result = PoscheckResult.objects.select_related("analysis").get(analysis_id=analysis_id)
    except PoscheckResult.DoesNotExist:
        return None

    validations = list(result.validations or [])
    consistent = sum(1 for item in validations if item.get("status") == VALIDATION_STATUS_CONSISTENT)
    inconsistent = sum(1 for item in validations if item.get("status") == VALIDATION_STATUS_INCONSISTENT)
    failed = sum(1 for item in validations if item.get("status") == VALIDATION_STATUS_FAILED)
    extracted = result.extracted or {}

    return {
        "analysis_id": str(result.analysis_id),
        "status": result.overall_status,
        "blocks_next_step": result.overall_status != PrecheckResultStatus.COMPLETED,
        "technology": result.analysis.technology,
        "gnodeb_id": extracted.get("gnodeb_id"),
        "tracking_area_code": extracted.get("tracking_area_code"),
        "rnc_id": extracted.get("rnc_id"),
        "enodeb_id": extracted.get("enodeb_id"),
        "tac": extracted.get("tac"),
        "bsc": extracted.get("bsc"),
        "bts_name": extracted.get("bts_name"),
        "cells": extracted.get("cells"),
        "ne_name": extracted.get("ne_name"),
        "validations": validations,
        "counts": {
            "total": len(validations),
            "consistent": consistent,
            "inconsistent": inconsistent,
            "failed": failed,
        },
        "error_code": result.error_code,
        "error_title": result.error_title,
        "error_detail": result.error_detail,
        "processed_at": result.processed_at.isoformat() if result.processed_at else None,
    }


def worst_analysis_status(*statuses: str) -> str:
    """Return the worst CheckAnalysisStatus among completed outcomes."""
    rank = {
        CheckAnalysisStatus.COMPLETED: 0,
        CheckAnalysisStatus.INCONSISTENT: 1,
        CheckAnalysisStatus.FAILED: 2,
    }
    worst = CheckAnalysisStatus.COMPLETED
    for status in statuses:
        if rank.get(status, -1) > rank.get(worst, -1):
            worst = status
    return worst


def analysis_status_for_result(overall_status: str) -> str:
    return _analysis_status_for(overall_status)


def _evaluate_from_inputs(
    analysis: CheckAnalysis,
    *,
    return_text: str | None,
    return_bytes: bytes | None,
) -> PoscheckOutcome:
    if not analysis.full_check:
        raise PoscheckError("Execution failure", [full_check_not_selected()])
    engine = get_engine(analysis.technology)
    if not engine.supported(analysis):
        raise PoscheckError("Execution failure", [full_check_not_selected()])

    if return_text is not None:
        extraction = engine.parse_return(return_text)
    elif return_bytes is not None:
        extraction = engine.parse_return_bytes(return_bytes)
    else:
        extraction = engine.parse_return_bytes(_read_return_payload(analysis))
    expected = engine.resolve_expected(analysis)
    return engine.compare(expected, extraction)


def _read_return_payload(analysis: CheckAnalysis) -> bytes:
    try:
        return_file = analysis.return_files.get(check_type=CheckType.FULL_CHECK)
    except CheckReturnFile.DoesNotExist as exc:
        raise PoscheckError("Execution failure", [missing_full_check_return_file()]) from exc

    with return_file.stored_file.open("rb") as handle:
        return handle.read()


def _failure_outcome(exc: PoscheckParseError | PoscheckError) -> G5Outcome:
    issues = [issue.as_dict() for issue in exc.issues]
    detail = "; ".join(issue["message"] for issue in issues) if issues else str(exc)
    return G5Outcome(
        overall_status=PrecheckResultStatus.EXECUTION_FAILURE,
        validations=[],
        extracted={},
        error_code=exc.code,
        error_title=exc.title,
        error_detail=detail,
    )


def _persist_outcome(analysis: CheckAnalysis, outcome: PoscheckOutcome, *, execution=None) -> PoscheckResult:
    defaults = {
        "overall_status": outcome.overall_status,
        "validations": outcome.validations,
        "extracted": outcome.extracted,
        "error_code": outcome.error_code,
        "error_title": outcome.error_title,
        "error_detail": outcome.error_detail,
        "processed_at": timezone.now(),
    }
    if execution is not None:
        defaults["execution"] = execution
    result, _created = PoscheckResult.objects.update_or_create(
        analysis=analysis,
        defaults=defaults,
    )
    return result


def _analysis_status_for(overall_status: str) -> str:
    if overall_status == PrecheckResultStatus.COMPLETED:
        return CheckAnalysisStatus.COMPLETED
    if overall_status == PrecheckResultStatus.INCONSISTENT:
        return CheckAnalysisStatus.INCONSISTENT
    return CheckAnalysisStatus.FAILED
