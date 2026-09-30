"""Validate Claro 2G Full Check values against the imported EP."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Final

from ep_import.models import EpCell, ImportJobStatus
from ep_import.services.scripts import FULL_CHECK_2G_PER_CELL_COMMANDS, FULL_CHECK_2G_SITE_COMMANDS
from poscheck.services.errors import (
    PoscheckError,
    PoscheckIssue,
    ep_field_inconsistent,
    ep_field_missing,
    full_check_not_selected,
    selected_cells_missing,
    technology_not_supported,
)
from poscheck.services.tech.g2.mml_parser import (
    FullCheck2GExtraction,
    parse_full_check_2g_return,
    parse_full_check_2g_return_bytes,
)
from precheck.models import CheckAnalysis, PrecheckResultStatus

EP_2G_CELL_NAME_KEY: Final[str] = "*GSM CELL NAME"
EP_2G_CELL_ID_KEY: Final[str] = "*CI"
EP_2G_BTS_KEY: Final[str] = "*BTS NAME"
EP_2G_BSC_KEY: Final[str] = "BSC"
EP_2G_LAC_KEY: Final[str] = "*LAC"
EP_2G_BCCH_KEY: Final[str] = "*FREQUENCY OF BCCH"

VALIDATION_BSC: Final[str] = "BSC"
VALIDATION_BTS: Final[str] = "BTS"
VALIDATION_CELL_ID: Final[str] = "CELL_ID"
VALIDATION_CELL_NAME: Final[str] = "CELL_NAME"
VALIDATION_LAC: Final[str] = "LAC"
VALIDATION_BCCH: Final[str] = "BCCH_FREQUENCY"
VALIDATION_COMMAND: Final[str] = "MML_COMMAND"

VALIDATION_STATUS_CONSISTENT: Final[str] = "consistent"
VALIDATION_STATUS_INCONSISTENT: Final[str] = "inconsistent"
VALIDATION_STATUS_FAILED: Final[str] = "failed"

_NUMERIC_RE = re.compile(r"^-?\d+(?:\.0+)?$")
_HEX_DEC_RE = re.compile(r"^H'[0-9A-Fa-f]+\((\d+)\)$", re.IGNORECASE)


@dataclass(frozen=True)
class EpExpected2GCell:
    cell_name: str
    cell_id: str
    bts_name: str
    lac: str
    bcch_frequency: str


@dataclass(frozen=True)
class EpExpected2GValues:
    bsc: str
    bts_name: str
    cells: tuple[EpExpected2GCell, ...]


@dataclass(frozen=True)
class PoscheckOutcome:
    overall_status: str
    validations: list[dict[str, Any]]
    extracted: dict[str, Any]
    error_code: str = ""
    error_title: str = ""
    error_detail: str = ""

    @property
    def blocks_next_step(self) -> bool:
        return self.overall_status != PrecheckResultStatus.COMPLETED


class G2FullCheckEngine:
    technology = "2G"

    def supported(self, analysis: CheckAnalysis) -> bool:
        return analysis.technology == "2G" and analysis.full_check

    def parse_return(self, text: str) -> FullCheck2GExtraction:
        return parse_full_check_2g_return(text)

    def parse_return_bytes(self, payload: bytes) -> FullCheck2GExtraction:
        return parse_full_check_2g_return_bytes(payload)

    def resolve_expected(self, analysis: CheckAnalysis) -> EpExpected2GValues:
        return resolve_expected_2g(analysis)

    def compare(self, expected: EpExpected2GValues, extraction: FullCheck2GExtraction) -> PoscheckOutcome:
        return compare_full_check_2g(expected, extraction)


def resolve_expected_2g(analysis: CheckAnalysis) -> EpExpected2GValues:
    _assert_scope(analysis)
    cells = _selected_ep_cells(analysis)
    bsc = _unique_ep_field(cells, EP_2G_BSC_KEY)
    bts_name = _unique_ep_field(cells, EP_2G_BTS_KEY)
    expected_cells: list[EpExpected2GCell] = []
    for cell in cells:
        raw = cell.raw or {}
        cell_id = normalize_comparable(raw.get(EP_2G_CELL_ID_KEY))
        if not cell_id:
            raise PoscheckError("Execution failure", [ep_field_missing(EP_2G_CELL_ID_KEY)])
        cell_name = normalize_comparable(raw.get(EP_2G_CELL_NAME_KEY) or cell.cell_name)
        if not cell_name:
            raise PoscheckError("Execution failure", [ep_field_missing(EP_2G_CELL_NAME_KEY)])
        lac = normalize_comparable(raw.get(EP_2G_LAC_KEY))
        if not lac:
            raise PoscheckError("Execution failure", [ep_field_missing(EP_2G_LAC_KEY)])
        bcch = normalize_comparable(raw.get(EP_2G_BCCH_KEY))
        if not bcch:
            raise PoscheckError("Execution failure", [ep_field_missing(EP_2G_BCCH_KEY)])
        expected_cells.append(
            EpExpected2GCell(
                cell_name=cell_name,
                cell_id=cell_id,
                bts_name=bts_name,
                lac=lac,
                bcch_frequency=bcch,
            )
        )
    return EpExpected2GValues(bsc=bsc, bts_name=bts_name, cells=tuple(expected_cells))


def compare_full_check_2g(expected: EpExpected2GValues, extraction: FullCheck2GExtraction) -> PoscheckOutcome:
    by_name = {cell.cell_name: cell for cell in extraction.cells}
    validations = [
        _compare_item(
            code=VALIDATION_BSC,
            label="BSC",
            expected=expected.bsc,
            found=extraction.bsc,
            ep_field=EP_2G_BSC_KEY,
        ),
        _compare_item(
            code=VALIDATION_BTS,
            label="BTS",
            expected=expected.bts_name,
            found=extraction.bts_name,
            ep_field=EP_2G_BTS_KEY,
        ),
    ]
    for expected_cell in expected.cells:
        found = by_name.get(expected_cell.cell_name)
        if found is None:
            validations.append(
                {
                    "code": VALIDATION_CELL_NAME,
                    "label": f"Cell Name ({expected_cell.cell_name})",
                    "expected": expected_cell.cell_name,
                    "found": "",
                    "status": VALIDATION_STATUS_FAILED,
                    "note": "Cell was not found in LST GCELL return.",
                    "cell_name": expected_cell.cell_name,
                }
            )
            continue
        validations.extend(
            [
                _compare_item(
                    code=VALIDATION_CELL_NAME,
                    label=f"Cell Name ({expected_cell.cell_name})",
                    expected=expected_cell.cell_name,
                    found=found.cell_name,
                    ep_field=EP_2G_CELL_NAME_KEY,
                    cell_name=expected_cell.cell_name,
                ),
                _compare_item(
                    code=VALIDATION_CELL_ID,
                    label=f"CellId ({expected_cell.cell_name})",
                    expected=expected_cell.cell_id,
                    found=found.cell_id,
                    ep_field=EP_2G_CELL_ID_KEY,
                    cell_name=expected_cell.cell_name,
                ),
                _compare_item(
                    code=VALIDATION_BTS,
                    label=f"BTS ({expected_cell.cell_name})",
                    expected=expected_cell.bts_name,
                    found=found.bts_name,
                    ep_field=EP_2G_BTS_KEY,
                    cell_name=expected_cell.cell_name,
                ),
                _compare_item(
                    code=VALIDATION_LAC,
                    label=f"LAC ({expected_cell.cell_name})",
                    expected=expected_cell.lac,
                    found=found.lac,
                    ep_field=EP_2G_LAC_KEY,
                    cell_name=expected_cell.cell_name,
                ),
                _compare_item(
                    code=VALIDATION_BCCH,
                    label=f"BCCH Frequency ({expected_cell.cell_name})",
                    expected=expected_cell.bcch_frequency,
                    found=found.bcch_frequency,
                    ep_field=EP_2G_BCCH_KEY,
                    cell_name=expected_cell.cell_name,
                ),
            ]
        )
    validations.extend(_command_validations_2g(expected, extraction))
    return _outcome_from_validations(validations, extraction.as_dict())


def normalize_comparable(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value).strip()

    text = str(value).strip()
    if not text or text.upper() == "NULL":
        return ""
    hex_match = _HEX_DEC_RE.fullmatch(text)
    if hex_match:
        return hex_match.group(1)
    if _NUMERIC_RE.fullmatch(text):
        return str(int(float(text)))
    return text


def _assert_scope(analysis: CheckAnalysis) -> None:
    if analysis.technology != "2G":
        raise PoscheckError("Execution failure", [technology_not_supported(analysis.technology)])
    if not analysis.full_check:
        raise PoscheckError("Execution failure", [full_check_not_selected()])
    if analysis.ep_job.status != ImportJobStatus.SUCCESS:
        raise PoscheckError(
            "Execution failure",
            [
                PoscheckIssue(
                    code="EP_NOT_READY",
                    message="The EP import must succeed before running the check.",
                )
            ],
        )


def _selected_ep_cells(analysis: CheckAnalysis) -> list[EpCell]:
    cell_names = [str(name).strip() for name in (analysis.selected_cells or []) if str(name).strip()]
    if not cell_names:
        raise PoscheckError("Execution failure", [selected_cells_missing([])])
    cells = list(
        EpCell.objects.filter(
            job_id=analysis.ep_job_id,
            technology=analysis.technology,
            site_name=analysis.site_name,
            cell_name__in=cell_names,
        )
    )
    found = {cell.cell_name for cell in cells}
    missing = [name for name in cell_names if name not in found]
    if missing:
        raise PoscheckError("Execution failure", [selected_cells_missing(missing)])
    by_name = {cell.cell_name: cell for cell in cells}
    return [by_name[name] for name in cell_names]


def _command_validations_2g(
    expected: EpExpected2GValues,
    extraction: FullCheck2GExtraction,
) -> list[dict[str, Any]]:
    validations: list[dict[str, Any]] = []
    for command in FULL_CHECK_2G_SITE_COMMANDS:
        match = next(
            (item for item in extraction.commands if item.command == command and item.ok),
            None,
        )
        if match is None:
            failed = next((item for item in extraction.commands if item.command == command), None)
            validations.append(
                {
                    "code": VALIDATION_COMMAND,
                    "label": command,
                    "expected": "RETCODE=0",
                    "found": f"RETCODE={failed.retcode}" if failed else "missing",
                    "status": VALIDATION_STATUS_FAILED if failed is None else VALIDATION_STATUS_INCONSISTENT,
                    "note": (
                        f"Command '{command}' was not found in the return."
                        if failed is None
                        else f"Command '{command}' failed with RETCODE={failed.retcode}."
                    ),
                }
            )
        else:
            validations.append(
                {
                    "code": VALIDATION_COMMAND,
                    "label": command,
                    "expected": "RETCODE=0",
                    "found": "RETCODE=0",
                    "status": VALIDATION_STATUS_CONSISTENT,
                    "note": f"Command '{command}' executed successfully.",
                }
            )

    for cell in expected.cells:
        for command in FULL_CHECK_2G_PER_CELL_COMMANDS:
            match = next(
                (
                    item
                    for item in extraction.commands
                    if item.command == command and item.cell_name == cell.cell_name and item.ok
                ),
                None,
            )
            label = f"{command} (CELL={cell.cell_name})"
            if match is None:
                failed = next(
                    (
                        item
                        for item in extraction.commands
                        if item.command == command and item.cell_name == cell.cell_name
                    ),
                    None,
                )
                validations.append(
                    {
                        "code": VALIDATION_COMMAND,
                        "label": label,
                        "expected": "RETCODE=0",
                        "found": f"RETCODE={failed.retcode}" if failed else "missing",
                        "status": VALIDATION_STATUS_FAILED if failed is None else VALIDATION_STATUS_INCONSISTENT,
                        "note": (
                            f"Command '{command}' for Cell {cell.cell_name} was not found."
                            if failed is None
                            else f"Command '{command}' for Cell {cell.cell_name} failed."
                        ),
                        "cell_name": cell.cell_name,
                    }
                )
            else:
                validations.append(
                    {
                        "code": VALIDATION_COMMAND,
                        "label": label,
                        "expected": "RETCODE=0",
                        "found": "RETCODE=0",
                        "status": VALIDATION_STATUS_CONSISTENT,
                        "note": f"Command '{command}' for Cell {cell.cell_name} executed successfully.",
                        "cell_name": cell.cell_name,
                    }
                )
    return validations


def _outcome_from_validations(validations: list[dict[str, Any]], extracted: dict[str, Any]) -> PoscheckOutcome:
    # Match mr-6: FAILED items remain visible as inconsistent when parsing succeeded.
    if not validations:
        overall = PrecheckResultStatus.EXECUTION_FAILURE
    elif all(item["status"] == VALIDATION_STATUS_CONSISTENT for item in validations):
        overall = PrecheckResultStatus.COMPLETED
    else:
        overall = PrecheckResultStatus.INCONSISTENT
    return PoscheckOutcome(
        overall_status=overall,
        validations=validations,
        extracted=extracted,
    )


def _unique_ep_field(cells: list[EpCell], field: str) -> str:
    values: list[str] = []
    for cell in cells:
        raw = cell.raw or {}
        if field not in raw:
            raise PoscheckError("Execution failure", [ep_field_missing(field)])
        normalized = normalize_comparable(raw.get(field))
        if not normalized:
            raise PoscheckError("Execution failure", [ep_field_missing(field)])
        values.append(normalized)
    unique = set(values)
    if len(unique) != 1:
        raise PoscheckError("Execution failure", [ep_field_inconsistent(field)])
    return values[0]


def _compare_item(
    *,
    code: str,
    label: str,
    expected: str,
    found: str,
    ep_field: str,
    cell_name: str | None = None,
) -> dict[str, Any]:
    expected_norm = normalize_comparable(expected)
    found_norm = normalize_comparable(found)
    if expected_norm == found_norm:
        status = VALIDATION_STATUS_CONSISTENT
        note = f"Matches EP {ep_field}."
    else:
        status = VALIDATION_STATUS_INCONSISTENT
        note = f"Network {label} differs from EP {ep_field}."
    item = {
        "code": code,
        "label": label,
        "expected": expected_norm,
        "found": found_norm,
        "status": status,
        "note": note,
    }
    if cell_name is not None:
        item["cell_name"] = cell_name
    return item
