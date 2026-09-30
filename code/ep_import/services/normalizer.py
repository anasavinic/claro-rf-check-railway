"""Normalize EP values and assemble import payload."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from ep_import.schema import CELL_KEY_COLUMNS, SHEET_BY_TECH, SITE_KEY_COLUMNS, Technology, region_from_filename
from ep_import.services.errors import EpImportError, EpImportIssue, empty_sheet, missing_row_key
from ep_import.services.mapper import build_header_map, canonicalize_row, cell_name, on_air_status, site_name


@dataclass
class NormalizedCell:
    technology: Technology
    region: str | None
    state: str | None
    site_name: str
    cell_name: str
    on_air: str | None
    raw: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "technology": self.technology.value,
            "region": self.region,
            "state": self.state,
            "site_name": self.site_name,
            "cell_name": self.cell_name,
            "on_air": self.on_air,
            "raw": self.raw,
        }


@dataclass
class ImportPayload:
    filename: str
    region: str | None
    cells: list[NormalizedCell] = field(default_factory=list)
    warnings: list[EpImportIssue] = field(default_factory=list)
    ignored_sheets: list[str] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        counts = {t.value: 0 for t in Technology}
        for cell in self.cells:
            counts[cell.technology.value] += 1
        return counts

    def sites_for(self, tech: Technology) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for cell in self.cells:
            if cell.technology != tech or not cell.site_name:
                continue
            if cell.site_name not in seen:
                seen.add(cell.site_name)
                ordered.append(cell.site_name)
        return ordered

    def cells_by_site(self, tech: Technology) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for cell in self.cells:
            if cell.technology != tech or not cell.site_name:
                continue
            grouped[cell.site_name].append(
                {
                    "cell_name": cell.cell_name,
                    "on_air": cell.on_air,
                    "raw": cell.raw,
                    "checked": False,
                }
            )
        return dict(grouped)

    def as_dict(self, technology: Technology | None = None) -> dict[str, Any]:
        tech = technology
        payload: dict[str, Any] = {
            "filename": self.filename,
            "region": self.region,
            "counts": self.counts,
            "ignored_sheets": self.ignored_sheets,
            "warnings": [w.as_dict() for w in self.warnings],
        }
        if tech:
            payload["technology"] = tech.value
            payload["sites"] = self.sites_for(tech)
            payload["cells_by_site"] = self.cells_by_site(tech)
        return payload


def inspect_row(
    canon: dict[str, Any],
    tech: Technology,
    sheet_name: str,
    excel_row: int,
    file_region: str | None,
) -> tuple[NormalizedCell | None, list[EpImportIssue]]:
    """Return a cell, or row errors. A fully empty row should not be passed here."""
    site = site_name(canon, tech)
    cell = cell_name(canon, tech)
    issues: list[EpImportIssue] = []
    if not site:
        issues.append(missing_row_key(sheet_name, excel_row, SITE_KEY_COLUMNS[tech][0], "site"))
    if not cell:
        issues.append(missing_row_key(sheet_name, excel_row, CELL_KEY_COLUMNS[tech], "cell"))
    if issues:
        return None, issues

    region_val = canon.get("REGION")
    region_str = str(region_val).strip().upper() if region_val not in (None, "") else file_region
    state_val = canon.get("STATE")
    state_str = str(state_val).strip().upper() if state_val not in (None, "") else None
    return (
        NormalizedCell(
            technology=tech,
            region=region_str,
            state=state_str,
            site_name=site,
            cell_name=cell,
            on_air=on_air_status(canon, tech),
            raw=canon,
        ),
        [],
    )


def normalize_sheets(
    filename: str,
    sheets_data: dict[str, list[dict[str, Any]]],
    ignored_sheets: list[str] | None = None,
) -> ImportPayload:
    file_region = region_from_filename(filename)
    payload = ImportPayload(
        filename=filename,
        region=file_region.value if file_region else None,
        ignored_sheets=list(ignored_sheets or []),
    )

    for tech, sheet_name in SHEET_BY_TECH.items():
        rows = sheets_data.get(sheet_name, [])
        if not rows:
            payload.warnings.append(empty_sheet(sheet_name))
            continue

        headers = list(rows[0].keys()) if rows else []
        header_map = build_header_map(headers)

        row_issues: list[EpImportIssue] = []
        for excel_row, row in enumerate(rows, start=2):
            canon = canonicalize_row(row, header_map)
            cell, issues = inspect_row(canon, tech, sheet_name, excel_row, payload.region)
            if issues:
                row_issues.extend(issues)
                continue
            if cell is not None:
                payload.cells.append(cell)
        if row_issues:
            raise EpImportError(title="EP file has invalid rows", issues=row_issues)

    if not payload.region:
        for cell in payload.cells:
            if cell.region:
                payload.region = cell.region
                break

    return payload
