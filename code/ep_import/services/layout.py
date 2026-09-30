"""Layout validation for Claro EP workbooks."""

from __future__ import annotations

from ep_import.schema import (
    REQUIRED_COLUMNS,
    REQUIRED_SHEETS,
    SHEET_BY_TECH,
    Technology,
    resolve_column_name,
)
from ep_import.services.content import validate_file_meta
from ep_import.services.errors import (
    EpImportError,
    EpImportIssue,
    missing_column,
    missing_sheet,
)


def validate_sheets_present(sheet_names: list[str]) -> list[EpImportIssue]:
    present = set(sheet_names)
    return [missing_sheet(sheet) for sheet in sorted(REQUIRED_SHEETS) if sheet not in present]


def validate_headers(
    sheet_name: str,
    headers: list[str],
    technology: Technology | None = None,
) -> list[EpImportIssue]:
    tech = technology or _tech_for_sheet(sheet_name)
    if tech is None:
        return []
    available = {h for h in headers if h}
    issues: list[EpImportIssue] = []
    for required in REQUIRED_COLUMNS[tech]:
        if resolve_column_name(required, available) is None:
            issues.append(missing_column(sheet_name, required))
    return issues


def assert_layout_or_raise(
    filename: str,
    sheet_headers: dict[str, list[str]],
    size_bytes: int | None = None,
) -> list[EpImportIssue]:
    """Validate file meta + required sheets + headers. Raises EpImportError on hard failures."""
    issues = validate_file_meta(filename, size_bytes)
    issues.extend(validate_sheets_present(list(sheet_headers.keys())))

    hard = [i for i in issues if i.severity == "error"]
    if hard:
        raise EpImportError(
            title="Layout is incompatible with Claro SRAN EP",
            issues=issues,
        )

    for tech, sheet in SHEET_BY_TECH.items():
        if sheet in sheet_headers:
            issues.extend(validate_headers(sheet, sheet_headers[sheet], tech))

    hard = [i for i in issues if i.severity == "error"]
    if hard:
        raise EpImportError(
            title="Layout is incompatible with Claro SRAN EP",
            issues=issues,
        )
    return issues


def _tech_for_sheet(sheet_name: str) -> Technology | None:
    for tech, name in SHEET_BY_TECH.items():
        if name == sheet_name:
            return tech
    return None
