"""Aggregate Combined RF check result snapshots."""

from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist

from combined.services.combined import tech_label
from poscheck.services.orchestrator import get_poscheck_snapshot
from precheck.models import CheckAnalysisStatus, CombinedCheck, PrecheckResultStatus
from precheck.services.validator import (
    VALIDATION_STATUS_CONSISTENT,
    VALIDATION_STATUS_INCONSISTENT,
    get_precheck_snapshot,
)


def build_combined_result(combined: CombinedCheck) -> dict:
    analyses = list(combined.analyses.select_related("ep_job").order_by("technology", "site_name"))
    pre_validations: list[dict] = []
    full_validations: list[dict] = []
    counts = {
        "total": 0,
        "consistent": 0,
        "inconsistent": 0,
        "failed": 0,
        "pre_total": 0,
        "full_total": 0,
    }
    tech_set: set[str] = set()
    sites = sorted({a.site_name for a in analyses})
    cell_count = sum(len(a.selected_cells or []) for a in analyses)

    for analysis in analyses:
        tech_set.add(analysis.technology)
        if analysis.pre_check:
            snap = get_precheck_snapshot(analysis.id)
            if snap:
                counts["pre_total"] += snap["counts"]["total"]
                for item in snap.get("validations") or []:
                    row = dict(item)
                    row["technology"] = analysis.technology
                    row["tech_label"] = tech_label(analysis.technology)
                    row["site_name"] = analysis.site_name
                    pre_validations.append(row)
                    _accumulate(counts, row.get("status", ""))
        if analysis.full_check:
            snap = get_poscheck_snapshot(analysis.id)
            if snap:
                counts["full_total"] += snap["counts"]["total"]
                for item in snap.get("validations") or []:
                    row = dict(item)
                    row["technology"] = analysis.technology
                    row["tech_label"] = tech_label(analysis.technology)
                    row["site_name"] = analysis.site_name
                    full_validations.append(row)
                    _accumulate(counts, row.get("status", ""))

    order = ["2G", "3G", "4G", "5G"]
    techs = [t for t in order if t in tech_set]

    status_label = {
        CheckAnalysisStatus.COMPLETED: "Completed",
        CheckAnalysisStatus.INCONSISTENT: "Inconsistent",
        CheckAnalysisStatus.FAILED: "Failed",
        CheckAnalysisStatus.PROCESSING: "Processing",
        CheckAnalysisStatus.AWAITING_RETURNS: "Awaiting returns",
    }.get(combined.status, combined.status)

    return {
        "combined": combined,
        "technologies": techs,
        "tech_labels": [tech_label(t) for t in techs],
        "tech_summary": " + ".join(tech_label(t) for t in techs),
        "sites": sites,
        "site_count": len(sites),
        "cell_count": cell_count,
        "status": combined.status,
        "status_label": status_label,
        "is_inconsistent": combined.status == CheckAnalysisStatus.INCONSISTENT,
        "is_failed": combined.status == CheckAnalysisStatus.FAILED,
        "pre_check": bool(combined.pre_check),
        "full_check": bool(combined.full_check),
        "pre_validations": pre_validations,
        "full_validations": full_validations,
        "counts": counts,
        "has_pre_results": bool(pre_validations),
        "has_full_results": bool(full_validations),
    }


def failure_reasons(combined: CombinedCheck) -> list[dict]:
    """User-facing reasons for each child analysis that failed to parse the MML."""
    reasons: list[dict] = []
    analyses = combined.analyses.order_by("technology", "site_name")
    for analysis in analyses:
        detail = ""
        title = ""
        for attr in ("poscheck_result", "precheck_result"):
            try:
                result = getattr(analysis, attr)
            except ObjectDoesNotExist:
                continue
            if result.overall_status != PrecheckResultStatus.EXECUTION_FAILURE or not result.error_detail:
                continue
            detail = result.error_detail
            title = result.error_title
            break
        if not detail and analysis.status != CheckAnalysisStatus.FAILED:
            continue
        if not detail:
            detail = "The MML return could not be processed for this technology."
        reasons.append(
            {
                "technology": tech_label(analysis.technology),
                "site_name": analysis.site_name,
                "title": title or "Execution failure",
                "detail": detail,
            }
        )
    return reasons


def _accumulate(counts: dict, status: str) -> None:
    counts["total"] += 1
    if status == VALIDATION_STATUS_CONSISTENT:
        counts["consistent"] += 1
    elif status == VALIDATION_STATUS_INCONSISTENT:
        counts["inconsistent"] += 1
    else:
        counts["failed"] += 1
