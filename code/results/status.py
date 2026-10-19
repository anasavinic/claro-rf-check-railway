"""Status labels and technology naming for consolidated results."""

from __future__ import annotations

from typing import Final

from precheck.models import CheckAnalysisStatus
from precheck.services.validator import (
    VALIDATION_STATUS_CONSISTENT,
    VALIDATION_STATUS_FAILED,
    VALIDATION_STATUS_INCONSISTENT,
)

CHECK_KIND_PRECHECK: Final[str] = "precheck"
CHECK_KIND_FULL_CHECK: Final[str] = "full_check"
CHECK_KIND_MONITORING: Final[str] = "monitoring"

SCOPE_SINGLE: Final[str] = "single"
SCOPE_COMBINED: Final[str] = "combined"

# Card vocabulary (Sucesso / Alerta / Falha) mapped onto existing validation statuses.
OUTCOME_SUCCESS: Final[str] = "success"
OUTCOME_ALERT: Final[str] = "alert"
OUTCOME_FAILURE: Final[str] = "failure"

VALIDATION_TO_OUTCOME: dict[str, str] = {
    VALIDATION_STATUS_CONSISTENT: OUTCOME_SUCCESS,
    VALIDATION_STATUS_FAILED: OUTCOME_ALERT,
    VALIDATION_STATUS_INCONSISTENT: OUTCOME_FAILURE,
}

OUTCOME_LABELS: dict[str, str] = {
    OUTCOME_SUCCESS: "Success",
    OUTCOME_ALERT: "Alert",
    OUTCOME_FAILURE: "Failure",
}

TECH_LABELS: dict[str, str] = {
    "2G": "2G",
    "3G": "3G",
    "4G": "4G LTE",
    "5G": "5G NR",
}

ANALYSIS_STATUS_LABELS: dict[str, str] = {
    CheckAnalysisStatus.COMPLETED: "Completed",
    CheckAnalysisStatus.INCONSISTENT: "Inconsistent",
    CheckAnalysisStatus.FAILED: "Failed",
    CheckAnalysisStatus.PROCESSING: "Processing",
    CheckAnalysisStatus.AWAITING_RETURNS: "Awaiting returns",
    CheckAnalysisStatus.DRAFT: "Draft",
}


def tech_label(technology: str) -> str:
    return TECH_LABELS.get(technology, technology)


def outcome_for_validation_status(status: str) -> str:
    return VALIDATION_TO_OUTCOME.get(status, OUTCOME_ALERT)


def analysis_status_label(status: str) -> str:
    return ANALYSIS_STATUS_LABELS.get(status, status)
