"""Build ConsolidatedAnalysis from CheckAnalysis / CombinedCheck."""

from __future__ import annotations

from typing import Any

from poscheck.services.orchestrator import get_poscheck_snapshot
from precheck.models import CheckAnalysis, CombinedCheck
from precheck.services.validator import (
    VALIDATION_STATUS_CONSISTENT,
    VALIDATION_STATUS_FAILED,
    VALIDATION_STATUS_INCONSISTENT,
    get_precheck_snapshot,
)
from results.models import CheckSection, ConsolidatedAnalysis, ValidationItem
from results.status import (
    CHECK_KIND_FULL_CHECK,
    CHECK_KIND_PRECHECK,
    SCOPE_COMBINED,
    SCOPE_SINGLE,
    analysis_status_label,
    outcome_for_validation_status,
    tech_label,
)


def build_from_analysis(analysis: CheckAnalysis) -> ConsolidatedAnalysis:
    """Consolidate Pre-check and Full Check outcomes for one analysis."""
    sections: list[CheckSection] = []
    if analysis.pre_check:
        snap = get_precheck_snapshot(analysis.id)
        section = _section_from_snapshot(analysis, CHECK_KIND_PRECHECK, snap)
        if section is not None:
            sections.append(section)
    if analysis.full_check:
        snap = get_poscheck_snapshot(analysis.id)
        section = _section_from_snapshot(analysis, CHECK_KIND_FULL_CHECK, snap)
        if section is not None:
            sections.append(section)

    validations = tuple(item for section in sections for item in section.validations)
    return ConsolidatedAnalysis(
        scope=SCOPE_SINGLE,
        id=str(analysis.id),
        status=analysis.status,
        status_label=analysis_status_label(analysis.status),
        technologies=(analysis.technology,),
        sites=(analysis.site_name,),
        cell_count=len(analysis.selected_cells or []),
        pre_check=bool(analysis.pre_check),
        full_check=bool(analysis.full_check),
        counts=_counts_from_validations(validations),
        sections=tuple(sections),
        validations=validations,
    )


def build_from_combined(combined: CombinedCheck) -> ConsolidatedAnalysis:
    """Consolidate all child analyses for a Combined RF check."""
    analyses = list(combined.analyses.select_related("ep_job").order_by("technology", "site_name"))
    sections: list[CheckSection] = []
    tech_set: set[str] = set()
    sites = sorted({a.site_name for a in analyses})
    cell_count = sum(len(a.selected_cells or []) for a in analyses)

    for analysis in analyses:
        tech_set.add(analysis.technology)
        child = build_from_analysis(analysis)
        sections.extend(child.sections)

    order = ["2G", "3G", "4G", "5G"]
    techs = tuple(t for t in order if t in tech_set)
    validations = tuple(item for section in sections for item in section.validations)

    return ConsolidatedAnalysis(
        scope=SCOPE_COMBINED,
        id=str(combined.id),
        status=combined.status,
        status_label=analysis_status_label(combined.status),
        technologies=techs,
        sites=tuple(sites),
        cell_count=cell_count,
        pre_check=bool(combined.pre_check),
        full_check=bool(combined.full_check),
        counts=_counts_from_validations(validations),
        sections=tuple(sections),
        validations=validations,
    )


def _section_from_snapshot(
    analysis: CheckAnalysis,
    check_kind: str,
    snapshot: dict[str, Any] | None,
) -> CheckSection | None:
    if snapshot is None:
        return None

    items: list[ValidationItem] = []
    for raw in snapshot.get("validations") or []:
        status = str(raw.get("status") or "")
        expected = raw.get("expected")
        found = raw.get("found")
        note = raw.get("note")
        items.append(
            ValidationItem(
                technology=analysis.technology,
                tech_label=tech_label(analysis.technology),
                site_name=analysis.site_name,
                check_kind=check_kind,
                code=str(raw.get("code") or ""),
                label=str(raw.get("label") or raw.get("code") or ""),
                expected="" if expected is None else str(expected),
                found="" if found is None else str(found),
                status=status,
                outcome=outcome_for_validation_status(status),
                note="—" if note in (None, "") else str(note),
                raw=dict(raw),
            )
        )

    counts = snapshot.get("counts") or {}
    return CheckSection(
        check_kind=check_kind,
        technology=analysis.technology,
        tech_label=tech_label(analysis.technology),
        site_name=analysis.site_name,
        status=str(snapshot.get("status") or ""),
        counts={
            "total": int(counts.get("total") or len(items)),
            "consistent": int(counts.get("consistent") or 0),
            "inconsistent": int(counts.get("inconsistent") or 0),
            "failed": int(counts.get("failed") or 0),
        },
        validations=tuple(items),
        source_snapshot=dict(snapshot),
    )


def _counts_from_validations(
    validations: tuple[ValidationItem, ...] | list[ValidationItem],
) -> dict[str, int]:
    total = len(validations)
    consistent = sum(1 for item in validations if item.status == VALIDATION_STATUS_CONSISTENT)
    inconsistent = sum(1 for item in validations if item.status == VALIDATION_STATUS_INCONSISTENT)
    failed = sum(1 for item in validations if item.status == VALIDATION_STATUS_FAILED)
    return {
        "total": total,
        "consistent": consistent,
        "inconsistent": inconsistent,
        "failed": failed,
        "success": consistent,
        "alert": failed,
        "failure": inconsistent,
    }
