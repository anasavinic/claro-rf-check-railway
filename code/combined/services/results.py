from django.core.exceptions import ObjectDoesNotExist
from results.adapters import to_combined_ui_snapshot
from results.builders import build_from_combined

from combined.services.combined import tech_label
from precheck.models import CheckAnalysisStatus, CombinedCheck, PrecheckResultStatus


def build_combined_result(combined: CombinedCheck) -> dict:
    """Return the Combined result page snapshot (stable UI contract)."""
    consolidated = build_from_combined(combined)
    snapshot = to_combined_ui_snapshot(consolidated)
    snapshot["combined"] = combined
    return snapshot


def has_comparable_results(combined: CombinedCheck) -> bool:
    """True when a child analysis produced validation rows, even if some failed."""
    analyses = combined.analyses.all()
    for analysis in analyses:
        for attr in ("poscheck_result", "precheck_result"):
            try:
                result = getattr(analysis, attr)
            except ObjectDoesNotExist:
                continue
            if result.validations:
                return True
    return False


_FAILED_RETURN_ATTRS = (
    ("precheck_result", "Pre-check"),
    ("poscheck_result", "Full Check"),
)


def failure_reasons(combined: CombinedCheck) -> list[dict]:
    """One user-facing reason per return that failed, including the exact cause."""
    reasons: list[dict] = []
    analyses = combined.analyses.order_by("technology", "site_name")
    for analysis in analyses:
        found = False
        for attr, check_type in _FAILED_RETURN_ATTRS:
            try:
                result = getattr(analysis, attr)
            except ObjectDoesNotExist:
                continue
            if result.overall_status != PrecheckResultStatus.EXECUTION_FAILURE:
                continue
            detail = (result.error_detail or "").strip() or (
                "The MML return could not be processed for this technology."
            )
            reasons.append(
                {
                    "technology": tech_label(analysis.technology),
                    "site_name": analysis.site_name,
                    "check_type": check_type,
                    "title": result.error_title or "Execution failure",
                    "code": result.error_code or "",
                    "detail": detail,
                }
            )
            found = True
        if found or analysis.status != CheckAnalysisStatus.FAILED:
            continue
        reasons.append(
            {
                "technology": tech_label(analysis.technology),
                "site_name": analysis.site_name,
                "check_type": "",
                "title": "Execution failure",
                "code": "",
                "detail": "The MML return could not be processed for this technology.",
            }
        )
    return reasons
