"""Typed import errors with user-facing English messages."""

from __future__ import annotations

from dataclasses import dataclass, field

SAFE_UNEXPECTED_MESSAGE = "The file could not be imported. Try again or contact support if it persists."
SAFE_TIMEOUT_MESSAGE = "Import timed out before it finished. Try again with the same file."
SAFE_STUCK_MESSAGE = "Import stopped before it finished. Upload the file again."


@dataclass(frozen=True)
class EpImportIssue:
    code: str
    message: str
    sheet: str | None = None
    column: str | None = None
    row: int | None = None
    severity: str = "error"  # error | warning

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "sheet": self.sheet,
            "column": self.column,
            "row": self.row,
            "severity": self.severity,
        }


@dataclass
class EpImportError(Exception):
    """Raised when EP import cannot proceed. Messages are safe to show users."""

    title: str
    issues: list[EpImportIssue] = field(default_factory=list)

    def __str__(self) -> str:
        if self.issues:
            return f"{self.title}: {self.issues[0].message}"
        return self.title

    @property
    def message(self) -> str:
        return str(self)


class TransientImportError(Exception):
    """Retryable failure (storage, broker, or database). Do not show the cause to users."""


def missing_sheet(sheet: str) -> EpImportIssue:
    return EpImportIssue(
        code="LAYOUT_MISSING_SHEET",
        message=(f"Sheet '{sheet}' was not found. Expected: RNP GSM (2G), RNP UMTS (3G), RNP LTE (4G), RNP NR (5G)."),
        sheet=sheet,
    )


def missing_column(sheet: str, column: str) -> EpImportIssue:
    return EpImportIssue(
        code="LAYOUT_MISSING_COLUMN",
        message=f"Required column missing: '{column}' (sheet {sheet}).",
        sheet=sheet,
        column=column,
    )


def invalid_extension(filename: str) -> EpImportIssue:
    return EpImportIssue(
        code="INVALID_EXTENSION",
        message=f"Invalid format for '{filename}'. Accepted format: .xlsx.",
    )


def unsupported_legacy_xls(filename: str) -> EpImportIssue:
    return EpImportIssue(
        code="UNSUPPORTED_XLS",
        message=f"'{filename}' is a legacy Excel file. Save it as .xlsx and upload again.",
    )


def invalid_xlsx_content(filename: str) -> EpImportIssue:
    return EpImportIssue(
        code="INVALID_XLSX",
        message=f"'{filename}' is not a valid .xlsx workbook.",
    )


def uncompressed_too_large(max_bytes: int) -> EpImportIssue:
    max_mb = max_bytes // (1024 * 1024)
    return EpImportIssue(
        code="UNCOMPRESSED_TOO_LARGE",
        message=f"Uncompressed workbook exceeds the {max_mb} MB limit.",
    )


def compression_ratio_exceeded() -> EpImportIssue:
    return EpImportIssue(
        code="COMPRESSION_RATIO",
        message="The workbook compression ratio is not allowed.",
    )


def file_too_large(size_bytes: int, max_bytes: int) -> EpImportIssue:
    size_mb = round(size_bytes / (1024 * 1024), 1)
    max_mb = max_bytes // (1024 * 1024)
    return EpImportIssue(
        code="FILE_TOO_LARGE",
        message=f"File size {size_mb} MB exceeds the {max_mb} MB limit.",
    )


def invalid_workbook() -> EpImportIssue:
    return EpImportIssue(
        code="INVALID_WORKBOOK",
        message="Could not read the Excel file. Check that it is an intact .xlsx workbook.",
    )


def empty_sheet(sheet: str) -> EpImportIssue:
    return EpImportIssue(
        code="EMPTY_SHEET",
        message=f"Sheet '{sheet}' is empty or has no data rows.",
        sheet=sheet,
        severity="warning",
    )


def missing_row_key(sheet: str, row: int, column: str, kind: str) -> EpImportIssue:
    return EpImportIssue(
        code="ROW_MISSING_KEY",
        message=f"Row {row} on sheet '{sheet}' is missing {kind} ('{column}').",
        sheet=sheet,
        column=column,
        row=row,
    )


def duplicate_cell(
    *,
    sheet: str,
    row: int,
    column: str,
    technology: str,
    site: str,
    cell: str,
    first_sheet: str,
    first_row: int,
) -> EpImportIssue:
    return EpImportIssue(
        code="DUPLICATE_CELL",
        message=(
            f"Duplicate cell '{cell}' for site '{site}' ({technology}) "
            f"on sheet '{sheet}', row {row} was ignored. "
            f"First seen on '{first_sheet}', row {first_row}."
        ),
        sheet=sheet,
        column=column,
        row=row,
        severity="warning",
    )


def issues_truncated(omitted: int, *, severity: str = "error") -> EpImportIssue:
    return EpImportIssue(
        code="ROW_ISSUES_TRUNCATED",
        message=f"{omitted} additional row issues were omitted.",
        severity=severity,
    )


def unexpected_failure() -> EpImportIssue:
    return EpImportIssue(code="UNEXPECTED_ERROR", message=SAFE_UNEXPECTED_MESSAGE)


def import_timed_out() -> EpImportIssue:
    return EpImportIssue(code="IMPORT_TIMEOUT", message=SAFE_TIMEOUT_MESSAGE)


def import_stuck() -> EpImportIssue:
    return EpImportIssue(code="IMPORT_STUCK", message=SAFE_STUCK_MESSAGE)


def cap_issues(issues: list[EpImportIssue], limit: int) -> list[EpImportIssue]:
    errors = [issue for issue in issues if issue.severity == "error"]
    warnings = [issue for issue in issues if issue.severity != "error"]
    kept: list[EpImportIssue] = []
    if len(errors) > limit:
        kept.extend(errors[:limit])
        kept.append(issues_truncated(len(errors) - limit))
    else:
        kept.extend(errors)
    if len(warnings) > limit:
        kept.extend(warnings[:limit])
        kept.append(issues_truncated(len(warnings) - limit, severity="warning"))
    else:
        kept.extend(warnings)
    return kept
