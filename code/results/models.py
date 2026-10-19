"""Canonical DTOs for consolidated RF Check results (not Django models)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from precheck.models import CheckAnalysisStatus
from results.status import tech_label


@dataclass(frozen=True)
class ValidationItem:
    """One comparison row shown in result tables."""

    technology: str
    tech_label: str
    site_name: str
    check_kind: str
    code: str
    label: str
    expected: str
    found: str
    status: str
    outcome: str
    note: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CheckSection:
    """Pre-check, Full Check, or (future) Monitoring slice for one analysis."""

    check_kind: str
    technology: str
    tech_label: str
    site_name: str
    status: str
    counts: dict[str, int]
    validations: tuple[ValidationItem, ...]
    source_snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConsolidatedAnalysis:
    """Single source of truth for result UI, reports, and future history."""

    scope: str
    id: str
    status: str
    status_label: str
    technologies: tuple[str, ...]
    sites: tuple[str, ...]
    cell_count: int
    pre_check: bool
    full_check: bool
    counts: dict[str, int]
    sections: tuple[CheckSection, ...]
    validations: tuple[ValidationItem, ...]

    @property
    def is_inconsistent(self) -> bool:
        return self.status == CheckAnalysisStatus.INCONSISTENT

    @property
    def is_failed(self) -> bool:
        return self.status == CheckAnalysisStatus.FAILED

    @property
    def tech_summary(self) -> str:
        return " + ".join(tech_label(t) for t in self.technologies)

    @property
    def site_count(self) -> int:
        return len(self.sites)
