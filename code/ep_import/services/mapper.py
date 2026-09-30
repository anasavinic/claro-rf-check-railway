"""Map raw EP rows onto canonical field names and site/cell keys."""

from __future__ import annotations

from typing import Any

from ep_import.schema import (
    CELL_KEY_COLUMNS,
    COLUMN_ALIASES,
    ON_AIR_COLUMNS,
    SITE_KEY_COLUMNS,
    Technology,
    resolve_column_name,
)


def build_header_map(raw_headers: list[str]) -> dict[str, str]:
    """Map canonical name → actual header present in the sheet."""
    available = {h for h in raw_headers if h}
    mapping: dict[str, str] = {}
    # Direct headers are canonical as-is.
    for header in available:
        mapping[header] = header
    # Aliases → canonical.
    for canonical, _aliases in COLUMN_ALIASES.items():
        actual = resolve_column_name(canonical, available)
        if actual:
            mapping[canonical] = actual
    return mapping


def canonicalize_row(row: dict[str, Any], header_map: dict[str, str]) -> dict[str, Any]:
    """Return row keyed by canonical names where aliases apply."""
    # Invert: actual → preferred canonical
    actual_to_canonical: dict[str, str] = {}
    for canonical, actual in header_map.items():
        # Prefer shorter canonical keys from COLUMN_ALIASES
        if canonical in COLUMN_ALIASES or canonical == actual:
            actual_to_canonical[actual] = canonical if canonical in COLUMN_ALIASES else actual

    result: dict[str, Any] = {}
    for key, value in row.items():
        canon = actual_to_canonical.get(key, key)
        # Don't overwrite a better canonical already set
        if canon not in result or result[canon] in (None, ""):
            result[canon] = value
    return result


def site_name(row: dict[str, Any], tech: Technology) -> str:
    for col in SITE_KEY_COLUMNS[tech]:
        value = row.get(col)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def cell_name(row: dict[str, Any], tech: Technology) -> str:
    col = CELL_KEY_COLUMNS[tech]
    value = row.get(col)
    return str(value).strip() if value not in (None, "") else ""


def on_air_status(row: dict[str, Any], tech: Technology) -> str | None:
    col = ON_AIR_COLUMNS[tech]
    if not col:
        return None
    value = row.get(col)
    if value in (None, ""):
        return None
    return str(value).strip()
