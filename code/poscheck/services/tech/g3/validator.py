"""Validate Claro 3G Full Check values against the imported EP."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Final

from ep_import.models import EpCell, ImportJobStatus
from ep_import.services.scripts import FULL_CHECK_3G_PER_CELL_COMMANDS, FULL_CHECK_3G_SITE_COMMANDS
from poscheck.services.errors import (
    PoscheckError,
    PoscheckIssue,
    ep_field_inconsistent,
    ep_field_missing,
    full_check_not_selected,
    selected_cells_missing,
    technology_not_supported,
)
from poscheck.services.tech.g3.mml_parser import (
    FullCheck3GExtraction,
    parse_full_check_3g_return,
    parse_full_check_3g_return_bytes,
)
from precheck.models import CheckAnalysis, PrecheckResultStatus

EP_CELL_ID_KEY: Final[str] = "CELL ID"
EP_CELL_NAME_KEY: Final[str] = "CELLNAME"
EP_RNC_ID_KEY: Final[str] = "RNC ID"

VALIDATION_RNC_ID: Final[str] = "RNC_ID"
VALIDATION_CELL_ID: Final[str] = "CELL_ID"
VALIDATION_CELL_NAME: Final[str] = "CELL_NAME"
VALIDATION_COMMAND: Final[str] = "MML_COMMAND"

VALIDATION_STATUS_CONSISTENT: Final[str] = "consistent"
VALIDATION_STATUS_INCONSISTENT: Final[str] = "inconsistent"
VALIDATION_STATUS_FAILED: Final[str] = "failed"

_NUMERIC_RE = re.compile(r"^-?\d+(?:\.0+)?$")


@dataclass(frozen=True)
class EpExpected3GCell:
    cell_name: str
    cell_id: str
    rnc_id: str


@dataclass(frozen=True)
class EpExpected3GValues:
    rnc_id: str
    cells: tuple[EpExpected3GCell, ...]


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


class G3FullCheckEngine:
    technology = "3G"

    def supported(self, analysis: CheckAnalysis) -> bool:
        return analysis.technology == "3G" and analysis.full_check

    def parse_return(self, text: str) -> FullCheck3GExtraction:
        return parse_full_check_3g_return(text)

    def parse_return_bytes(self, payload: bytes) -> FullCheck3GExtraction:
        return parse_full_check_3g_return_bytes(payload)

    def resolve_expected(self, analysis: CheckAnalysis) -> EpExpected3GValues:
        return resolve_expected_3g(analysis)

    def compare(self, expected: EpExpected3GValues, extraction: FullCheck3GExtraction) -> PoscheckOutcome:
        return compare_full_check_3g(expected, extraction)


def resolve_expected_3g(analysis: CheckAnalysis) -> EpExpected3GValues:
    _assert_scope(analysis)
    cells = _selected_ep_cells(analysis)
    rnc_id = _unique_ep_field(cells, EP_RNC_ID_KEY)
    expected_cells: list[EpExpected3GCell] = []
    for cell in cells:
        raw = cell.raw or {}
        cell_id = normalize_comparable(raw.get(EP_CELL_ID_KEY))
        if not cell_id:
            raise PoscheckError("Execution failure", [ep_field_missing(EP_CELL_ID_KEY)])
        cell_name = normalize_comparable(raw.get(EP_CELL_NAME_KEY) or cell.cell_name)
        if not cell_name:
            raise PoscheckError("Execution failure", [ep_field_missing(EP_CELL_NAME_KEY)])
        expected_cells.append(
            EpExpected3GCell(
                cell_name=cell_name,
                cell_id=cell_id,
                rnc_id=rnc_id,
            )
        )
    return EpExpected3GValues(rnc_id=rnc_id, cells=tuple(expected_cells))


def compare_full_check_3g(expected: EpExpected3GValues, extraction: FullCheck3GExtraction) -> PoscheckOutcome:
    by_name = {cell.cell_name: cell for cell in extraction.cells}
    validations = [
        _compare_item(
            code=VALIDATION_RNC_ID,
            label="RNC ID",
            expected=expected.rnc_id,
            found=extraction.rnc_id,
            ep_field=EP_RNC_ID_KEY,
        )
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
                    "note": "Cell was not found in LST UCELL return.",
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
                    ep_field=EP_CELL_NAME_KEY,
                    cell_name=expected_cell.cell_name,
                ),
                _compare_item(
                    code=VALIDATION_CELL_ID,
                    label=f"Cell ID ({expected_cell.cell_name})",
                    expected=expected_cell.cell_id,
                    found=found.cell_id,
                    ep_field=EP_CELL_ID_KEY,
                    cell_name=expected_cell.cell_name,
                ),
                _compare_item(
                    code=VALIDATION_RNC_ID,
                    label=f"RNC ID ({expected_cell.cell_name})",
                    expected=expected_cell.rnc_id,
                    found=found.rnc_id,
                    ep_field=EP_RNC_ID_KEY,
                    cell_name=expected_cell.cell_name,
                ),
            ]
        )

    validations.extend(_command_validations_3g(expected, extraction))
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
    if _NUMERIC_RE.fullmatch(text):
        return str(int(float(text)))
    return text


def _assert_scope(analysis: CheckAnalysis) -> None:
    if analysis.technology != "3G":
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
    found_names = {cell.cell_name for cell in cells}
    missing = [name for name in cell_names if name not in found_names]
    if missing:
        raise PoscheckError("Execution failure", [selected_cells_missing(missing)])
    return cells


def _command_validations_3g(
    expected: EpExpected3GValues,
    extraction: FullCheck3GExtraction,
) -> list[dict[str, Any]]:
    validations: list[dict[str, Any]] = []
    for command in FULL_CHECK_3G_SITE_COMMANDS:
        match = next((item for item in extraction.commands if item.command == command and item.ok), None)
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
        for command in FULL_CHECK_3G_PER_CELL_COMMANDS:
            match = next(
                (
                    item
                    for item in extraction.commands
                    if item.command == command and item.cell_id == cell.cell_id and item.ok
                ),
                None,
            )
            label = f"{command} (CELLID={cell.cell_id})"
            if match is None:
                failed = next(
                    (item for item in extraction.commands if item.command == command and item.cell_id == cell.cell_id),
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
                            f"Command '{command}' for CellId {cell.cell_id} was not found."
                            if failed is None
                            else f"Command '{command}' for CellId {cell.cell_id} failed."
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
                        "note": f"Command '{command}' for CellId {cell.cell_id} executed successfully.",
                        "cell_name": cell.cell_name,
                    }
                )
    return validations


def _outcome_from_validations(validations: list[dict[str, Any]], extracted: dict[str, Any]) -> PoscheckOutcome:
    if any(item["status"] == VALIDATION_STATUS_FAILED for item in validations):
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
    if cell_name:
        item["cell_name"] = cell_name
    return item
