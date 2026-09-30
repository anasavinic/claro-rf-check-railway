"""Validate Claro 5G pre-check values against the imported EP."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from ep_import.models import EpCell, ImportJobStatus
from precheck.models import (
    CheckAnalysis,
    CheckAnalysisStatus,
    CheckReturnFile,
    CheckType,
    PrecheckResult,
    PrecheckResultStatus,
)
from precheck.services.errors import (
    PrecheckError,
    PrecheckIssue,
    PrecheckParseError,
    analysis_busy,
    ep_field_inconsistent,
    ep_field_missing,
    missing_return_file,
    precheck_not_selected,
    selected_cells_missing,
    technology_not_supported,
)
from precheck.services.mml_parser import PrecheckExtraction, parse_precheck_return, parse_precheck_return_bytes

EP_GNBID_KEY: Final[str] = "gNBId"
EP_TRACKING_AREA_KEY: Final[str] = "Tracking Area ID"

VALIDATION_GNODEB_ID: Final[str] = "GNODEB_ID"
VALIDATION_TRACKING_AREA: Final[str] = "TRACKING_AREA_CODE"

VALIDATION_STATUS_CONSISTENT: Final[str] = "consistent"
VALIDATION_STATUS_INCONSISTENT: Final[str] = "inconsistent"
VALIDATION_STATUS_FAILED: Final[str] = "failed"

_NUMERIC_RE = re.compile(r"^-?\d+(?:\.0+)?$")


@dataclass(frozen=True)
class EpExpectedValues:
    gnodeb_id: str
    tracking_area_code: str


@dataclass(frozen=True)
class PrecheckOutcome:
    overall_status: str
    validations: list[dict[str, Any]]
    extracted: dict[str, Any]
    error_code: str = ""
    error_title: str = ""
    error_detail: str = ""

    @property
    def blocks_next_step(self) -> bool:
        return self.overall_status != PrecheckResultStatus.COMPLETED


def resolve_expected_from_ep(analysis: CheckAnalysis) -> EpExpectedValues:
    """Resolve site-level expected values from the selected EP cells."""
    _assert_precheck_scope(analysis)

    cell_names = [str(name).strip() for name in (analysis.selected_cells or []) if str(name).strip()]
    if not cell_names:
        raise PrecheckError("Execution failure", [selected_cells_missing([])])

    cells = list(
        EpCell.objects.filter(
            job_id=analysis.ep_job_id,
            technology=analysis.technology,
            site_name=analysis.site_name,
            cell_name__in=cell_names,
        )
    )
    found_names = {cell.cell_name for cell in cells}
    missing = [name for name in cell_names if name not in found_names]
    if missing:
        raise PrecheckError("Execution failure", [selected_cells_missing(missing)])

    gnodeb_id = _unique_ep_field(cells, EP_GNBID_KEY)
    tracking_area = _unique_ep_field(cells, EP_TRACKING_AREA_KEY)
    return EpExpectedValues(gnodeb_id=gnodeb_id, tracking_area_code=tracking_area)


def compare_precheck(expected: EpExpectedValues, extraction: PrecheckExtraction) -> PrecheckOutcome:
    """Compare EP expectations with values extracted from the Gerência return."""
    validations = [
        _compare_item(
            code=VALIDATION_GNODEB_ID,
            label="gNodeB ID",
            expected=expected.gnodeb_id,
            found=extraction.gnodeb_id,
            ep_field=EP_GNBID_KEY,
        ),
        _compare_item(
            code=VALIDATION_TRACKING_AREA,
            label="Tracking Area Code",
            expected=expected.tracking_area_code,
            found=extraction.tracking_area_code,
            ep_field=EP_TRACKING_AREA_KEY,
        ),
    ]
    if all(item["status"] == VALIDATION_STATUS_CONSISTENT for item in validations):
        overall = PrecheckResultStatus.COMPLETED
    else:
        overall = PrecheckResultStatus.INCONSISTENT

    return PrecheckOutcome(
        overall_status=overall,
        validations=validations,
        extracted=extraction.as_dict(),
    )


def evaluate_precheck(analysis: CheckAnalysis, return_text: str) -> PrecheckOutcome:
    """Parse a return payload and compare it with the analysis EP selection."""
    _assert_precheck_scope(analysis)
    extraction = parse_precheck_return(return_text)
    expected = resolve_expected_from_ep(analysis)
    return compare_precheck(expected, extraction)


def process_precheck(
    analysis: CheckAnalysis,
    *,
    return_text: str | None = None,
    return_bytes: bytes | None = None,
    execution=None,
    claim_analysis: bool = True,
    manage_analysis_status: bool = True,
) -> PrecheckResult:
    """Run pre-check, persist ``PrecheckResult``, and optionally sync analysis status.

    Heavy I/O and CPU run outside the DB lock. Only claim and persist use short transactions.
    """
    if claim_analysis:
        with transaction.atomic():
            locked = CheckAnalysis.objects.select_for_update().get(pk=analysis.pk)
            if locked.status == CheckAnalysisStatus.PROCESSING:
                raise PrecheckError("Could not process", [analysis_busy()])
            if manage_analysis_status:
                locked.status = CheckAnalysisStatus.PROCESSING
                locked.save(update_fields=["status", "updated_at"])
            analysis = locked

    try:
        outcome = _evaluate_from_inputs(analysis, return_text=return_text, return_bytes=return_bytes)
    except (PrecheckParseError, PrecheckError) as exc:
        outcome = _failure_outcome(exc)

    with transaction.atomic():
        locked = CheckAnalysis.objects.select_for_update().get(pk=analysis.pk)
        result = _persist_outcome(locked, outcome, execution=execution)
        if manage_analysis_status:
            locked.status = _analysis_status_for(outcome.overall_status)
            locked.save(update_fields=["status", "updated_at"])
    return result


def get_precheck_snapshot(analysis_id: UUID | str) -> dict[str, Any] | None:
    """Return a stable payload for later modules, or ``None`` when absent."""
    try:
        result = PrecheckResult.objects.select_related("analysis").get(analysis_id=analysis_id)
    except PrecheckResult.DoesNotExist:
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
        "gnodeb_id": extracted.get("gnodeb_id"),
        "tracking_area_code": extracted.get("tracking_area_code"),
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


def normalize_comparable(value: Any) -> str:
    """Normalize EP/network values so numeric equivalents compare equal."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value).strip()

    text = str(value).strip()
    if not text or text.upper() == "NULL":
        return ""
    if _NUMERIC_RE.fullmatch(text):
        return str(int(float(text)))
    return text


def _evaluate_from_inputs(
    analysis: CheckAnalysis,
    *,
    return_text: str | None,
    return_bytes: bytes | None,
) -> PrecheckOutcome:
    _assert_precheck_scope(analysis)
    if return_text is not None:
        extraction = parse_precheck_return(return_text)
    elif return_bytes is not None:
        extraction = parse_precheck_return_bytes(return_bytes)
    else:
        extraction = _extract_from_stored_return(analysis)
    expected = resolve_expected_from_ep(analysis)
    return compare_precheck(expected, extraction)


def _extract_from_stored_return(analysis: CheckAnalysis) -> PrecheckExtraction:
    try:
        return_file = analysis.return_files.get(check_type=CheckType.PRECHECK)
    except CheckReturnFile.DoesNotExist as exc:
        raise PrecheckError("Execution failure", [missing_return_file()]) from exc

    with return_file.stored_file.open("rb") as handle:
        payload = handle.read()
    return parse_precheck_return_bytes(payload)


def _assert_precheck_scope(analysis: CheckAnalysis) -> None:
    if analysis.technology != "5G":
        raise PrecheckError("Execution failure", [technology_not_supported(analysis.technology)])
    if not analysis.pre_check:
        raise PrecheckError("Execution failure", [precheck_not_selected()])
    if analysis.ep_job.status != ImportJobStatus.SUCCESS:
        raise PrecheckError(
            "Execution failure",
            [
                PrecheckIssue(
                    code="EP_NOT_READY",
                    message="The EP import must succeed before running pre-check.",
                )
            ],
        )


def _unique_ep_field(cells: list[EpCell], field: str) -> str:
    values: list[str] = []
    for cell in cells:
        raw = cell.raw or {}
        if field not in raw:
            raise PrecheckError("Execution failure", [ep_field_missing(field)])
        normalized = normalize_comparable(raw.get(field))
        if not normalized:
            raise PrecheckError("Execution failure", [ep_field_missing(field)])
        values.append(normalized)

    unique = set(values)
    if len(unique) != 1:
        raise PrecheckError("Execution failure", [ep_field_inconsistent(field)])
    return values[0]


def _compare_item(
    *,
    code: str,
    label: str,
    expected: str,
    found: str,
    ep_field: str,
) -> dict[str, Any]:
    expected_norm = normalize_comparable(expected)
    found_norm = normalize_comparable(found)
    if expected_norm == found_norm:
        status = VALIDATION_STATUS_CONSISTENT
        note = f"Matches EP {ep_field}."
    else:
        status = VALIDATION_STATUS_INCONSISTENT
        note = f"Network {label} differs from EP {ep_field}."
    return {
        "code": code,
        "label": label,
        "expected": expected_norm,
        "found": found_norm,
        "status": status,
        "note": note,
    }


def _failure_outcome(exc: PrecheckParseError | PrecheckError) -> PrecheckOutcome:
    issues = [issue.as_dict() for issue in exc.issues]
    detail = "; ".join(issue["message"] for issue in issues) if issues else str(exc)
    return PrecheckOutcome(
        overall_status=PrecheckResultStatus.EXECUTION_FAILURE,
        validations=[],
        extracted={},
        error_code=exc.code,
        error_title=exc.title,
        error_detail=detail,
    )


def _persist_outcome(analysis: CheckAnalysis, outcome: PrecheckOutcome, *, execution=None) -> PrecheckResult:
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
    result, _created = PrecheckResult.objects.update_or_create(
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
