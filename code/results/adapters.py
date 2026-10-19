"""Adapt ConsolidatedAnalysis to dict shapes expected by existing result templates."""

from __future__ import annotations

from typing import Any

from precheck.models import CheckAnalysisStatus
from results.models import CheckSection, ConsolidatedAnalysis, ValidationItem
from results.status import CHECK_KIND_FULL_CHECK, CHECK_KIND_PRECHECK, tech_label


def precheck_source_snapshot(
    consolidated: ConsolidatedAnalysis,
) -> dict[str, Any] | None:
    """Raw Pre-check snapshot for single-tech result/failure pages."""
    section = _first_section(consolidated, CHECK_KIND_PRECHECK)
    if section is None:
        return None
    return dict(section.source_snapshot)


def poscheck_source_snapshot(
    consolidated: ConsolidatedAnalysis,
) -> dict[str, Any] | None:
    """Raw Full Check snapshot for single-tech result/failure pages."""
    section = _first_section(consolidated, CHECK_KIND_FULL_CHECK)
    if section is None:
        return None
    return dict(section.source_snapshot)


def to_combined_ui_snapshot(consolidated: ConsolidatedAnalysis) -> dict[str, Any]:
    """Match the dict previously built by ``combined.services.results.build_combined_result``."""
    from results.groupings import by_category, by_site, by_technology

    pre_validations = [
        _combined_row(item) for item in consolidated.validations if item.check_kind == CHECK_KIND_PRECHECK
    ]
    full_validations = [
        _combined_row(item) for item in consolidated.validations if item.check_kind == CHECK_KIND_FULL_CHECK
    ]

    pre_total = sum(s.counts["total"] for s in consolidated.sections if s.check_kind == CHECK_KIND_PRECHECK)
    full_total = sum(s.counts["total"] for s in consolidated.sections if s.check_kind == CHECK_KIND_FULL_CHECK)

    counts = {
        "total": consolidated.counts["total"],
        "consistent": consolidated.counts["consistent"],
        "inconsistent": consolidated.counts["inconsistent"],
        "failed": consolidated.counts["failed"],
        "pre_total": pre_total,
        "full_total": full_total,
    }

    categories = [group.key for group in by_category(consolidated)]

    return {
        "technologies": list(consolidated.technologies),
        "tech_labels": [tech_label(t) for t in consolidated.technologies],
        "tech_summary": consolidated.tech_summary,
        "sites": list(consolidated.sites),
        "site_count": consolidated.site_count,
        "cell_count": consolidated.cell_count,
        "categories": categories,
        "by_technology": [{"key": g.key, "label": g.label, "counts": g.counts} for g in by_technology(consolidated)],
        "by_site": [{"key": g.key, "label": g.label, "counts": g.counts} for g in by_site(consolidated)],
        "by_category": [{"key": g.key, "label": g.label, "counts": g.counts} for g in by_category(consolidated)],
        "status": consolidated.status,
        "status_label": consolidated.status_label,
        "is_inconsistent": consolidated.status == CheckAnalysisStatus.INCONSISTENT,
        "is_failed": consolidated.status == CheckAnalysisStatus.FAILED,
        "pre_check": consolidated.pre_check,
        "full_check": consolidated.full_check,
        "pre_validations": pre_validations,
        "full_validations": full_validations,
        "counts": counts,
        "has_pre_results": bool(pre_validations),
        "has_full_results": bool(full_validations),
    }


def _combined_row(item: ValidationItem) -> dict[str, Any]:
    row = dict(item.raw)
    row["technology"] = item.technology
    row["tech_label"] = item.tech_label
    row["site_name"] = item.site_name
    return row


def _first_section(consolidated: ConsolidatedAnalysis, check_kind: str) -> CheckSection | None:
    for section in consolidated.sections:
        if section.check_kind == check_kind:
            return section
    return None
