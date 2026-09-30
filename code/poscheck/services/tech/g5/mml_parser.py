"""Parse Huawei MML Gerencia returns for Claro 5G Full Check."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from poscheck.services.errors import (
    PoscheckParseError,
    empty_return,
    explain_missing_commands,
    missing_command,
    missing_field,
    unrecognized_format,
)
from poscheck.services.mml_common import (
    CommandExecutionStatus,
    MmlCommandBlock,
    command_base_name,
    decode_payload,
    normalize_value,
    parse_aligned_table,
    parse_blocks,
    validate_block,
)

COMMAND_GNODEB: Final[str] = "LST GNODEBFUNCTION"
COMMAND_TRACKING_AREA: Final[str] = "LST GNBTRACKINGAREA"
COMMAND_NRCELL: Final[str] = "LST NRCELL"
COMMAND_NRDUCELL: Final[str] = "LST NRDUCELL"
COMMAND_DSP_NRDUCELL: Final[str] = "DSP NRDUCELL"

GNODEB_ID_FIELD: Final[str] = "gNodeB ID"
TRACKING_AREA_CODE_FIELD: Final[str] = "Tracking Area Code"

NRCELL_COLUMNS: Final[tuple[str, ...]] = (
    "Cell Name",
    "Cell ID",
    "Frequency Band",
    "Cell Activate State",
)
NRDUCELL_COLUMNS: Final[tuple[str, ...]] = (
    "NR DU Cell Name",
    "Cell ID",
    "Physical Cell ID",
    "Frequency Band",
    "Downlink NARFCN",
)
DSP_NRDUCELL_COLUMNS: Final[tuple[str, ...]] = (
    "NR DU Cell Name",
    "Cell ID",
    "NR DU Cell State",
)


@dataclass(frozen=True)
class NrCellRecord:
    cell_name: str
    cell_id: str
    frequency_band: str
    physical_cell_id: str
    downlink_narfcn: str
    activate_state: str
    nr_du_cell_state: str

    def as_dict(self) -> dict:
        return {
            "cell_name": self.cell_name,
            "cell_id": self.cell_id,
            "frequency_band": self.frequency_band,
            "physical_cell_id": self.physical_cell_id,
            "downlink_narfcn": self.downlink_narfcn,
            "activate_state": self.activate_state,
            "nr_du_cell_state": self.nr_du_cell_state,
        }


@dataclass(frozen=True)
class FullCheck5GExtraction:
    gnodeb_id: str
    tracking_area_code: str
    ne_name: str
    cells: tuple[NrCellRecord, ...]
    commands: tuple[CommandExecutionStatus, ...]
    gnodeb_function: MmlCommandBlock
    tracking_area: MmlCommandBlock

    def as_dict(self) -> dict:
        return {
            "gnodeb_id": self.gnodeb_id,
            "tracking_area_code": self.tracking_area_code,
            "ne_name": self.ne_name,
            "cells": [cell.as_dict() for cell in self.cells],
            "commands": [item.as_dict() for item in self.commands],
        }


def parse_full_check_5g_return(text: str) -> FullCheck5GExtraction:
    content = (text or "").strip()
    if not content:
        raise PoscheckParseError("Execution failure", [empty_return()])

    blocks = parse_blocks(content)
    if not blocks:
        raise PoscheckParseError("Execution failure", [unrecognized_format()])

    by_command: dict[str, MmlCommandBlock] = {}
    for block in blocks:
        key = block.command.upper()
        existing = by_command.get(key)
        if existing is None:
            by_command[key] = block
        elif not existing.fields and block.fields:
            by_command[key] = block

    issues = []
    gnodeb = by_command.get(COMMAND_GNODEB)
    tracking = by_command.get(COMMAND_TRACKING_AREA)
    nrcell = by_command.get(COMMAND_NRCELL)
    nrducell = by_command.get(COMMAND_NRDUCELL)
    dsp_nrducell = by_command.get(COMMAND_DSP_NRDUCELL)

    if gnodeb is None:
        issues.append(missing_command(COMMAND_GNODEB))
    if tracking is None:
        issues.append(missing_command(COMMAND_TRACKING_AREA))
    if nrcell is None:
        issues.append(missing_command(COMMAND_NRCELL))
    if nrducell is None:
        issues.append(missing_command(COMMAND_NRDUCELL))
    if dsp_nrducell is None:
        issues.append(missing_command(COMMAND_DSP_NRDUCELL))
    if issues:
        raise PoscheckParseError(
            "Execution failure",
            explain_missing_commands("5G", by_command, issues),
        )

    assert gnodeb is not None and tracking is not None
    assert nrcell is not None and nrducell is not None and dsp_nrducell is not None

    issues.extend(validate_block(gnodeb, required_fields=(GNODEB_ID_FIELD,)))
    issues.extend(validate_block(tracking, required_fields=(TRACKING_AREA_CODE_FIELD,)))
    issues.extend(validate_block(nrcell, required_fields=()))
    issues.extend(validate_block(nrducell, required_fields=()))
    issues.extend(validate_block(dsp_nrducell, required_fields=()))
    if issues:
        raise PoscheckParseError("Execution failure", issues)

    nrcell_rows = parse_aligned_table(nrcell.raw, required_columns=NRCELL_COLUMNS)
    nrducell_rows = parse_aligned_table(nrducell.raw, required_columns=NRDUCELL_COLUMNS)
    dsp_rows = parse_aligned_table(dsp_nrducell.raw, required_columns=DSP_NRDUCELL_COLUMNS)
    if not nrcell_rows:
        raise PoscheckParseError(
            "Execution failure",
            [missing_field(COMMAND_NRCELL, "Cell Name")],
        )

    by_du_name = {
        normalize_value(row.get("NR DU Cell Name", "")): row for row in nrducell_rows if row.get("NR DU Cell Name")
    }
    by_dsp_name = {
        normalize_value(row.get("NR DU Cell Name", "")): row for row in dsp_rows if row.get("NR DU Cell Name")
    }

    cells: list[NrCellRecord] = []
    for row in nrcell_rows:
        cell_name = normalize_value(row.get("Cell Name", ""))
        if not cell_name:
            continue
        du = by_du_name.get(cell_name, {})
        dsp = by_dsp_name.get(cell_name, {})
        cells.append(
            NrCellRecord(
                cell_name=cell_name,
                cell_id=_first_token(row.get("Cell ID", "") or du.get("Cell ID", "")),
                frequency_band=_first_token(row.get("Frequency Band", "") or du.get("Frequency Band", "")),
                physical_cell_id=_first_token(du.get("Physical Cell ID", "")),
                downlink_narfcn=_first_token(du.get("Downlink NARFCN", "")),
                activate_state=_first_token(row.get("Cell Activate State", "")),
                nr_du_cell_state=_first_token(dsp.get("NR DU Cell State", "")),
            )
        )
    if not cells:
        raise PoscheckParseError(
            "Execution failure",
            [missing_field(COMMAND_NRCELL, "Cell Name")],
        )

    commands = tuple(
        CommandExecutionStatus(
            command=command_base_name(block.command),
            retcode=block.retcode,
            ok=block.retcode == 0,
        )
        for block in blocks
    )
    ne_name = gnodeb.ne_name or tracking.ne_name or nrcell.ne_name
    return FullCheck5GExtraction(
        gnodeb_id=normalize_value(gnodeb.fields[GNODEB_ID_FIELD]),
        tracking_area_code=normalize_value(tracking.fields[TRACKING_AREA_CODE_FIELD]),
        ne_name=ne_name,
        cells=tuple(cells),
        commands=commands,
        gnodeb_function=gnodeb,
        tracking_area=tracking,
    )


def parse_full_check_5g_return_bytes(payload: bytes, *, encoding: str = "utf-8") -> FullCheck5GExtraction:
    return parse_full_check_5g_return(decode_payload(payload, encoding=encoding))


def _first_token(value: str | None) -> str:
    text = normalize_value(value or "")
    if not text:
        return ""
    return text.split()[0]
