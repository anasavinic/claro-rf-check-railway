"""Validate Claro 5G Full Check values against the imported EP."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Final

from ep_import.models import EpCell, ImportJobStatus
from ep_import.services.scripts import FULL_CHECK_5G_COMMANDS
from poscheck.services.errors import (
    PoscheckError,
    PoscheckIssue,
    ep_field_inconsistent,
    ep_field_missing,
    full_check_not_selected,
    selected_cells_missing,
    technology_not_supported,
)
from poscheck.services.mml_common import command_base_name, find_command_status
from poscheck.services.tech.g5.mml_parser import (
    FullCheck5GExtraction,
    parse_full_check_5g_return,
    parse_full_check_5g_return_bytes,
)
from precheck.models import CheckAnalysis, PrecheckResultStatus

EP_GNBID_KEY: Final[str] = "gNBId"
EP_TRACKING_AREA_KEY: Final[str] = "Tracking Area ID"
EP_CELL_ID_KEY: Final[str] = "CellId"
EP_FREQUENCY_BAND_KEY: Final[str] = "FrequencyBand"
EP_PHYSICAL_CELL_ID_KEY: Final[str] = "PhysicalCellId"
EP_DL_NARFCN_KEY: Final[str] = "DlNarfcn"

VALIDATION_GNODEB_ID: Final[str] = "GNODEB_ID"
VALIDATION_TRACKING_AREA: Final[str] = "TRACKING_AREA_CODE"
VALIDATION_CELL_ID: Final[str] = "CELL_ID"
VALIDATION_FREQUENCY_BAND: Final[str] = "FREQUENCY_BAND"
VALIDATION_PHYSICAL_CELL_ID: Final[str] = "PHYSICAL_CELL_ID"
VALIDATION_DL_NARFCN: Final[str] = "DL_NARFCN"
VALIDATION_ACTIVATE_STATE: Final[str] = "CELL_ACTIVATE_STATE"
VALIDATION_NR_DU_STATE: Final[str] = "NR_DU_CELL_STATE"
VALIDATION_COMMAND: Final[str] = "MML_COMMAND"

VALIDATION_STATUS_CONSISTENT: Final[str] = "consistent"
VALIDATION_STATUS_INCONSISTENT: Final[str] = "inconsistent"
VALIDATION_STATUS_FAILED: Final[str] = "failed"

EXPECTED_ACTIVATE_STATE: Final[str] = "Activated"
EXPECTED_NR_DU_STATE: Final[str] = "Normal"

_NUMERIC_RE = re.compile(r"^-?\d+(?:\.0+)?$")


@dataclass(frozen=True)
class EpExpected5GCell:
    cell_name: str
    cell_id: str
    frequency_band: str
    physical_cell_id: str
    downlink_narfcn: str


@dataclass(frozen=True)
class EpExpected5GValues:
    gnodeb_id: str
    tracking_area_code: str
    cells: tuple[EpExpected5GCell, ...]


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


class G5FullCheckEngine:
    technology = "5G"

    def supported(self, analysis: CheckAnalysis) -> bool:
        return analysis.technology == "5G" and analysis.full_check

    def parse_return(self, text: str) -> FullCheck5GExtraction:
        return parse_full_check_5g_return(text)

    def parse_return_bytes(self, payload: bytes) -> FullCheck5GExtraction:
        return parse_full_check_5g_return_bytes(payload)

    def resolve_expected(self, analysis: CheckAnalysis) -> EpExpected5GValues:
        return resolve_expected_5g(analysis)

    def compare(self, expected: EpExpected5GValues, extraction: FullCheck5GExtraction) -> PoscheckOutcome:
        return compare_full_check_5g(expected, extraction)


def resolve_expected_5g(analysis: CheckAnalysis) -> EpExpected5GValues:
    _assert_scope(analysis)
    cells = _selected_ep_cells(analysis)
    gnodeb_id = _unique_ep_field(cells, EP_GNBID_KEY)
    tracking_area = _unique_ep_field(cells, EP_TRACKING_AREA_KEY)
    expected_cells: list[EpExpected5GCell] = []
    for cell in cells:
        raw = cell.raw or {}
        expected_cells.append(
            EpExpected5GCell(
                cell_name=cell.cell_name,
                cell_id=_required_field(raw, EP_CELL_ID_KEY),
                frequency_band=_required_field(raw, EP_FREQUENCY_BAND_KEY),
                physical_cell_id=_required_field(raw, EP_PHYSICAL_CELL_ID_KEY),
                downlink_narfcn=_required_field(raw, EP_DL_NARFCN_KEY),
            )
        )
    return EpExpected5GValues(
        gnodeb_id=gnodeb_id,
        tracking_area_code=tracking_area,
        cells=tuple(expected_cells),
    )


def compare_full_check_5g(expected: EpExpected5GValues, extraction: FullCheck5GExtraction) -> PoscheckOutcome:
    by_name = {cell.cell_name: cell for cell in extraction.cells}
    validations = [
        _compare_item(
            code=VALIDATION_GNODEB_ID,
            label="gNodeB ID",
            expected=expected.gnodeb_id,
            found=extraction.gnodeb_id,
            ep_field=EP_GNBID_KEY,
        ),
        _compare_item(
            code=VALIDATION_TRACKING_AREA,
            label="Tracking Area Code",
            expected=expected.tracking_area_code,
            found=extraction.tracking_area_code,
            ep_field=EP_TRACKING_AREA_KEY,
        ),
    ]

    for expected_cell in expected.cells:
        found = by_name.get(expected_cell.cell_name)
        if found is None:
            validations.append(
                {
                    "code": VALIDATION_CELL_ID,
                    "label": f"Cell ({expected_cell.cell_name})",
                    "expected": expected_cell.cell_name,
                    "found": "",
                    "status": VALIDATION_STATUS_INCONSISTENT,
                    "note": "Cell was not found in LST NRCELL / LST NRDUCELL return.",
                    "cell_name": expected_cell.cell_name,
                }
            )
            continue
        validations.extend(
            [
                _compare_item(
                    code=VALIDATION_CELL_ID,
                    label=f"Cell ID ({expected_cell.cell_name})",
                    expected=expected_cell.cell_id,
                    found=found.cell_id,
                    ep_field=EP_CELL_ID_KEY,
                    cell_name=expected_cell.cell_name,
                ),
                _compare_item(
                    code=VALIDATION_FREQUENCY_BAND,
                    label=f"Frequency Band ({expected_cell.cell_name})",
                    expected=expected_cell.frequency_band,
                    found=found.frequency_band,
                    ep_field=EP_FREQUENCY_BAND_KEY,
                    cell_name=expected_cell.cell_name,
                ),
                _compare_item(
                    code=VALIDATION_PHYSICAL_CELL_ID,
                    label=f"Physical Cell ID ({expected_cell.cell_name})",
                    expected=expected_cell.physical_cell_id,
                    found=found.physical_cell_id,
                    ep_field=EP_PHYSICAL_CELL_ID_KEY,
                    cell_name=expected_cell.cell_name,
                ),
                _compare_item(
                    code=VALIDATION_DL_NARFCN,
                    label=f"Downlink NARFCN ({expected_cell.cell_name})",
                    expected=expected_cell.downlink_narfcn,
                    found=found.downlink_narfcn,
                    ep_field=EP_DL_NARFCN_KEY,
                    cell_name=expected_cell.cell_name,
                ),
                _state_item(
                    code=VALIDATION_ACTIVATE_STATE,
                    label=f"Cell Activate State ({expected_cell.cell_name})",
                    expected=EXPECTED_ACTIVATE_STATE,
                    found=found.activate_state,
                    cell_name=expected_cell.cell_name,
                ),
                _state_item(
                    code=VALIDATION_NR_DU_STATE,
                    label=f"NR DU Cell State ({expected_cell.cell_name})",
                    expected=EXPECTED_NR_DU_STATE,
                    found=found.nr_du_cell_state,
                    cell_name=expected_cell.cell_name,
                ),
            ]
        )

    validations.extend(_command_validations_5g(extraction))
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
    if analysis.technology != "5G":
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


def _command_validations_5g(extraction: FullCheck5GExtraction) -> list[dict[str, Any]]:
    validations: list[dict[str, Any]] = []
    for command_line in FULL_CHECK_5G_COMMANDS:
        command = command_base_name(command_line)
        match = find_command_status(extraction.commands, command)
        if match is None:
            validations.append(
                {
                    "code": VALIDATION_COMMAND,
                    "label": command,
                    "expected": "RETCODE=0",
                    "found": "missing",
                    "status": VALIDATION_STATUS_FAILED,
                    "note": f"Command '{command}' was not found in the return.",
                }
            )
        elif not match.ok:
            validations.append(
                {
                    "code": VALIDATION_COMMAND,
                    "label": command,
                    "expected": "RETCODE=0",
                    "found": f"RETCODE={match.retcode}",
                    "status": VALIDATION_STATUS_INCONSISTENT,
                    "note": f"Command '{command}' failed with RETCODE={match.retcode}.",
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


def _required_field(raw: dict, field: str) -> str:
    if field not in raw:
        raise PoscheckError("Execution failure", [ep_field_missing(field)])
    normalized = normalize_comparable(raw.get(field))
    if not normalized:
        raise PoscheckError("Execution failure", [ep_field_missing(field)])
    return normalized


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
    if code == VALIDATION_FREQUENCY_BAND:
        expected_norm = expected_norm.upper()
        found_norm = found_norm.upper()
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


def _state_item(
    *,
    code: str,
    label: str,
    expected: str,
    found: str,
    cell_name: str,
) -> dict[str, Any]:
    expected_norm = normalize_comparable(expected)
    found_norm = normalize_comparable(found)
    if expected_norm == found_norm:
        status = VALIDATION_STATUS_CONSISTENT
        note = f"{label} is {expected_norm}."
    else:
        status = VALIDATION_STATUS_INCONSISTENT
        note = f"{label} should be {expected_norm}."
    return {
        "code": code,
        "label": label,
        "expected": expected_norm,
        "found": found_norm,
        "status": status,
        "note": note,
        "cell_name": cell_name,
    }
