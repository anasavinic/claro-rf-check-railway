"""Canonical EP Claro SRAN schema — layout contract for CARD-04.

Inventoried from RNP_SRAN_{REGION}_*.xlsx (CO/ES/MG/NE/PRSC/BASE).
See docs/ep-schema.md.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Final


class Technology(StrEnum):
    G2 = "2G"
    G3 = "3G"
    G4 = "4G"
    G5 = "5G"


class RegionCode(StrEnum):
    CO = "CO"
    ES = "ES"
    MG = "MG"
    NE = "NE"
    PRSC = "PRSC"
    BASE = "BASE"


# Exact sheet names present in all regional + BASE workbooks.
SHEET_BY_TECH: Final[dict[Technology, str]] = {
    Technology.G2: "RNP GSM (2G)",
    Technology.G3: "RNP UMTS (3G)",
    Technology.G4: "RNP LTE (4G)",
    Technology.G5: "RNP NR (5G)",
}

REQUIRED_SHEETS: Final[frozenset[str]] = frozenset(SHEET_BY_TECH.values())

TECH_BY_SHEET: Final[dict[str, Technology]] = {sheet: tech for tech, sheet in SHEET_BY_TECH.items()}

# Column aliases observed across regions (canonical ← alternatives).
COLUMN_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "REGION": ("Region",),
    "RESPONSIBLE": ("Responsible",),
    "OBS": ("Obs", "Obs.:", "obs", "Comentário", "COMENTÁRIOS"),
    "CGI": ("CONFIRMAÇÃO DE CGI",),
}

# Minimum headers per sheet (layout gate). Names are canonical.
REQUIRED_COLUMNS: Final[dict[Technology, tuple[str, ...]]] = {
    Technology.G2: (
        "STATE",
        "SINGLE RAN NAME",
        "*BTS NAME",
        "*GSM CELL NAME",
        "*LAC",
        "*CI",
        "*FREQUENCY OF BCCH",
        "BSC",
    ),
    Technology.G3: (
        "REGION",
        "STATE",
        "SINGLE RAN NAME",
        "NODEB NAME",
        "CELLNAME",
        "CELL ID",
        "LAC",
        "SAC",
        "RNC ID",
        "RNC NAME",
        "PSCRAMBCODE",
        "UARFCN DOWNLINK",
    ),
    Technology.G4: (
        "REGION",
        "STATE",
        "SINGLE RAN NAME",
        "ENODEBNAME",
        "CELL NAME",
        "CELL ID",
        "ENODEB ID",
        "TAC",
        "EARFCN_DL",
        "PCI",
    ),
    Technology.G5: (
        "REGION",
        "STATE",
        "SINGLE RAN NAME",
        "ENODEB NAME",
        "CELL NAME",
        "gNBId",
        "CellId",
        "FrequencyBand",
        "PhysicalCellId",
        "DlNarfcn",
        "Tracking Area ID",
    ),
}

# Keys used by UI (Figma site / cell tables) and check selection.
SITE_KEY_COLUMNS: Final[dict[Technology, tuple[str, ...]]] = {
    Technology.G2: ("*BTS NAME", "SINGLE RAN NAME"),
    Technology.G3: ("NODEB NAME", "SINGLE RAN NAME"),
    Technology.G4: ("ENODEBNAME", "SINGLE RAN NAME"),
    Technology.G5: ("ENODEB NAME", "SINGLE RAN NAME"),
}

CELL_KEY_COLUMNS: Final[dict[Technology, str]] = {
    Technology.G2: "*GSM CELL NAME",
    Technology.G3: "CELLNAME",
    Technology.G4: "CELL NAME",
    Technology.G5: "CELL NAME",
}

ON_AIR_COLUMNS: Final[dict[Technology, str | None]] = {
    Technology.G2: "ON AIR (U2000)",
    Technology.G3: "ON AIR (U2000)",
    Technology.G4: "ON AIR",
    Technology.G5: None,
}

FILENAME_REGION_RE: Final[re.Pattern[str]] = re.compile(
    r"RNP_SRAN_(CO|ES|MG|NE|PRSC|BASE)[_\-.]",
    re.IGNORECASE,
)

# v1 reads Office Open XML only. Legacy binary .xls is not supported.
ALLOWED_EXTENSIONS: Final[frozenset[str]] = frozenset({".xlsx"})

# Figma copy cites 10MB; real regionals exceed that — keep UI honest at 50MB.
MAX_UPLOAD_BYTES: Final[int] = 50 * 1024 * 1024

# Zip-bomb limits applied before openpyxl opens the package.
MAX_UNCOMPRESSED_BYTES: Final[int] = 256 * 1024 * 1024
MAX_COMPRESSION_RATIO: Final[int] = 100
MAX_ZIP_ENTRIES: Final[int] = 2000

# Files and cells are purged after this many days.
EP_IMPORT_RETENTION_DAYS: Final[int] = 15

# Persist and progress flush sizes. Validation stores issues, not raw rows.
PERSIST_BATCH_SIZE: Final[int] = 1000
PROGRESS_FLUSH_ROWS: Final[int] = 500
MAX_ROW_ISSUES: Final[int] = 50

DEFAULT_PAGE_SIZE: Final[int] = 50
MAX_PAGE_SIZE: Final[int] = 100


def resolve_column_name(header: str, available: set[str]) -> str | None:
    """Return the actual workbook column matching a canonical name, or None."""
    if header in available:
        return header
    for alias in COLUMN_ALIASES.get(header, ()):
        if alias in available:
            return alias
    # Also accept if canonical is an alias of something present (reverse).
    for canonical, aliases in COLUMN_ALIASES.items():
        if header in aliases and canonical in available:
            return canonical
    return None


def region_from_filename(filename: str) -> RegionCode | None:
    match = FILENAME_REGION_RE.search(filename or "")
    if not match:
        return None
    return RegionCode(match.group(1).upper())
