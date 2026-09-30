"""Build a format-agnostic export payload from the same snapshots the UI uses."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from poscheck.services.orchestrator import get_poscheck_snapshot
from precheck.models import (
    CheckAnalysis,
    CheckAnalysisStatus,
    CheckType,
    CombinedCheck,
    PrecheckResultStatus,
)
from precheck.services.validator import get_precheck_snapshot
from reports.services.errors import (
    ExportError,
    analysis_not_exportable,
    no_consolidated_results,
)

EXPORTABLE_STATUSES: frozenset[str] = frozenset(
    {
        CheckAnalysisStatus.COMPLETED,
        CheckAnalysisStatus.INCONSISTENT,
    }
)

EXPORTABLE_RESULT_STATUSES: frozenset[str] = frozenset(
    {
        PrecheckResultStatus.COMPLETED,
        PrecheckResultStatus.INCONSISTENT,
    }
)

ANALYSIS_STATUS_LABELS: dict[str, str] = {
    "completed": "Completed",
    "inconsistent": "Inconsistent",
}

VALIDATION_STATUS_LABELS: dict[str, str] = {
    "consistent": "OK",
    "inconsistent": "NOK",
    "failed": "Warning",
}

CHECK_TYPE_PRECHECK = "Pre-check"
CHECK_TYPE_FULL_CHECK = "Full Check"


@dataclass(frozen=True)
class ValidationRow:
    technology: str
    site: str
    check_type: str
    code: str
    label: str
    expected: str
    found: str
    status: str
    status_label: str
    note: str

    def matches_ui(self) -> dict[str, str]:
        """Fields shown in the result table."""
        return {
            "label": self.label,
            "expected": self.expected,
            "found": self.found,
            "status": self.status_label,
            "note": self.note,
        }


@dataclass(frozen=True)
class CheckSection:
    check_type: str
    status: str
    status_label: str
    processed_at: str
    counts: dict[str, int]
    score: int | None
    validations: list[ValidationRow]


@dataclass(frozen=True)
class ExportPayload:
    analysis_id: str
    technology: str
    tech_label: str
    site: str
    cells: list[str]
    analysis_status: str
    analysis_status_label: str
    check_types_label: str
    processed_at: str
    ep_filename: str
    precheck_filename: str
    full_check_filename: str
    counts: dict[str, int]
    score: int | None
    sections: list[CheckSection] = field(default_factory=list)

    @property
    def validations(self) -> list[ValidationRow]:
        rows: list[ValidationRow] = []
        for section in self.sections:
            rows.extend(section.validations)
        return rows

    def rows_by_status(self, status: str) -> list[ValidationRow]:
        return [row for row in self.validations if row.status == status]


def build_export_payload(analysis: CheckAnalysis) -> ExportPayload:
    """Assemble consolidated results for any output format.

    Uses ``get_precheck_snapshot`` / ``get_poscheck_snapshot`` so export matches the UI.
    """
    if analysis.status not in EXPORTABLE_STATUSES:
        raise ExportError("Cannot export", [analysis_not_exportable()])

    sections: list[CheckSection] = []
    if analysis.pre_check:
        pre_snapshot = get_precheck_snapshot(analysis.id)
        section = _section_from_snapshot(analysis, CHECK_TYPE_PRECHECK, pre_snapshot)
        if section is not None:
            sections.append(section)
    if analysis.full_check:
        pos_snapshot = get_poscheck_snapshot(analysis.id)
        section = _section_from_snapshot(analysis, CHECK_TYPE_FULL_CHECK, pos_snapshot)
        if section is not None:
            sections.append(section)

    if not sections:
        raise ExportError("Cannot export", [no_consolidated_results()])

    counts = _aggregate_counts(sections)
    processed_at = next((item.processed_at for item in sections if item.processed_at != "—"), "—")
    return_files = {item.check_type: item for item in analysis.return_files.all()}
    pre_file = return_files.get(CheckType.PRECHECK)
    full_file = return_files.get(CheckType.FULL_CHECK)

    return ExportPayload(
        analysis_id=str(analysis.id),
        technology=analysis.technology,
        tech_label=_tech_label(analysis.technology),
        site=analysis.site_name,
        cells=list(analysis.selected_cells or []),
        analysis_status=analysis.status,
        analysis_status_label=ANALYSIS_STATUS_LABELS.get(analysis.status, analysis.status),
        check_types_label=_check_types_label(analysis),
        processed_at=processed_at,
        ep_filename=analysis.ep_job.original_filename if analysis.ep_job_id else "",
        precheck_filename=pre_file.original_filename if pre_file else "",
        full_check_filename=full_file.original_filename if full_file else "",
        counts=counts,
        score=_score(counts["consistent"], counts["total"]),
        sections=sections,
    )


def format_processed_at(value: str | None) -> str:
    """Match the result page timestamp (``mm/dd/YYYY HH:MM``)."""
    if not value:
        return "—"
    parsed = parse_datetime(value)
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    if timezone.is_aware(parsed):
        parsed = timezone.localtime(parsed)
    return parsed.strftime("%m/%d/%Y %H:%M")


def _section_from_snapshot(
    analysis: CheckAnalysis,
    check_type: str,
    snapshot: dict[str, Any] | None,
) -> CheckSection | None:
    if snapshot is None:
        return None
    if snapshot.get("status") not in EXPORTABLE_RESULT_STATUSES:
        return None
    counts = snapshot.get("counts") or {}
    total = int(counts.get("total") or 0)
    consistent = int(counts.get("consistent") or 0)
    inconsistent = int(counts.get("inconsistent") or 0)
    failed = int(counts.get("failed") or 0)
    status = str(snapshot.get("status") or "")
    return CheckSection(
        check_type=check_type,
        status=status,
        status_label=ANALYSIS_STATUS_LABELS.get(status, status or "—"),
        processed_at=format_processed_at(snapshot.get("processed_at")),
        counts={
            "total": total,
            "consistent": consistent,
            "inconsistent": inconsistent,
            "failed": failed,
        },
        score=_score(consistent, total),
        validations=[_validation_row(analysis, check_type, item) for item in (snapshot.get("validations") or [])],
    )


def _validation_row(analysis: CheckAnalysis, check_type: str, item: dict[str, Any]) -> ValidationRow:
    status = str(item.get("status") or "")
    note = item.get("note")
    expected = item.get("expected")
    found = item.get("found")
    return ValidationRow(
        technology=_tech_label(analysis.technology),
        site=analysis.site_name,
        check_type=check_type,
        code=str(item.get("code") or ""),
        label=str(item.get("label") or item.get("code") or ""),
        expected="" if expected is None else str(expected),
        found="" if found is None else str(found),
        status=status,
        status_label=VALIDATION_STATUS_LABELS.get(status, status or "—"),
        note="—" if note in (None, "") else str(note),
    )


def _aggregate_counts(sections: list[CheckSection]) -> dict[str, int]:
    total = sum(section.counts["total"] for section in sections)
    consistent = sum(section.counts["consistent"] for section in sections)
    inconsistent = sum(section.counts["inconsistent"] for section in sections)
    failed = sum(section.counts["failed"] for section in sections)
    return {
        "total": total,
        "consistent": consistent,
        "inconsistent": inconsistent,
        "failed": failed,
    }


def _score(consistent: int, total: int) -> int | None:
    if not total:
        return None
    return int((consistent / total) * 100 + 0.5)


def _tech_label(technology: str) -> str:
    return "5G NR" if technology == "5G" else technology


def _check_types_label(analysis: CheckAnalysis) -> str:
    return _flags_check_label(analysis.pre_check, analysis.full_check)


def _flags_check_label(pre_check: bool, full_check: bool) -> str:
    if pre_check and full_check:
        return "Pre-check + Full Check"
    if pre_check:
        return "Pre-check"
    if full_check:
        return "Full Check"
    return "—"


def build_combined_export_payload(combined: CombinedCheck) -> ExportPayload:
    """Assemble one payload from every exportable child analysis."""
    analyses = list(
        combined.analyses.select_related("ep_job").prefetch_related("return_files").order_by("technology", "site_name")
    )
    sections: list[CheckSection] = []
    sites: list[str] = []
    techs: list[str] = []
    cells: list[str] = []
    pre_names: list[str] = []
    full_names: list[str] = []
    ep_filename = combined.ep_job.original_filename if combined.ep_job_id else ""

    for analysis in analyses:
        if analysis.status not in EXPORTABLE_STATUSES:
            continue
        if analysis.site_name and analysis.site_name not in sites:
            sites.append(analysis.site_name)
        if analysis.technology and analysis.technology not in techs:
            techs.append(analysis.technology)
        for cell in analysis.selected_cells or []:
            if cell not in cells:
                cells.append(cell)
        if not ep_filename and analysis.ep_job_id:
            ep_filename = analysis.ep_job.original_filename
        return_files = {item.check_type: item for item in analysis.return_files.all()}
        if analysis.pre_check:
            section = _section_from_snapshot(
                analysis,
                CHECK_TYPE_PRECHECK,
                get_precheck_snapshot(analysis.id),
            )
            if section is not None:
                sections.append(section)
                pre_file = return_files.get(CheckType.PRECHECK)
                if pre_file and pre_file.original_filename not in pre_names:
                    pre_names.append(pre_file.original_filename)
        if analysis.full_check:
            section = _section_from_snapshot(
                analysis,
                CHECK_TYPE_FULL_CHECK,
                get_poscheck_snapshot(analysis.id),
            )
            if section is not None:
                sections.append(section)
                full_file = return_files.get(CheckType.FULL_CHECK)
                if full_file and full_file.original_filename not in full_names:
                    full_names.append(full_file.original_filename)

    if not sections:
        raise ExportError("Cannot export", [no_consolidated_results()])

    counts = _aggregate_counts(sections)
    processed_at = next(
        (item.processed_at for item in sections if item.processed_at != "—"),
        "—",
    )
    ordered = [tech for tech in ("2G", "3G", "4G", "5G") if tech in techs]
    techs = ordered or techs
    has_issues = any(section.status == CheckAnalysisStatus.INCONSISTENT for section in sections)
    status = CheckAnalysisStatus.INCONSISTENT if has_issues else CheckAnalysisStatus.COMPLETED
    if len(sites) == 1:
        site = sites[0]
    elif sites:
        site = ", ".join(sites)
    else:
        site = "—"

    return ExportPayload(
        analysis_id=str(combined.id),
        technology="+".join(techs) or "RF",
        tech_label=" + ".join(_tech_label(tech) for tech in techs) or "—",
        site=site,
        cells=cells,
        analysis_status=status,
        analysis_status_label=ANALYSIS_STATUS_LABELS.get(status, status),
        check_types_label=_flags_check_label(
            bool(combined.pre_check),
            bool(combined.full_check),
        ),
        processed_at=processed_at,
        ep_filename=ep_filename,
        precheck_filename=", ".join(pre_names),
        full_check_filename=", ".join(full_names),
        counts=counts,
        score=_score(counts["consistent"], counts["total"]),
        sections=sections,
    )
