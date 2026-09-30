"""Typed export/share errors with user-facing English messages."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExportIssue:
    code: str
    message: str
    severity: str = "error"

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "severity": self.severity}


@dataclass
class ExportError(Exception):
    """Raised when consolidated results cannot be exported or shared."""

    title: str
    issues: list[ExportIssue] = field(default_factory=list)

    def __str__(self) -> str:
        if self.issues:
            return f"{self.title}: {self.issues[0].message}"
        return self.title

    @property
    def message(self) -> str:
        return str(self)

    @property
    def code(self) -> str:
        return self.issues[0].code if self.issues else "EXPORT_ERROR"


def analysis_not_exportable() -> ExportIssue:
    return ExportIssue(
        code="ANALYSIS_NOT_EXPORTABLE",
        message="Only completed analyses can be exported or shared.",
    )


def no_consolidated_results() -> ExportIssue:
    return ExportIssue(
        code="NO_CONSOLIDATED_RESULTS",
        message="No consolidated results are available to export.",
    )


def render_failed() -> ExportIssue:
    return ExportIssue(
        code="EXPORT_RENDER_FAILED",
        message="Could not generate the report. Try again.",
    )
