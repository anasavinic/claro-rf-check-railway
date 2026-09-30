"""Parse Huawei MML Gerencia returns for Claro 4G Full Check."""

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
    decode_payload,
    normalize_value,
    parse_blocks,
    validate_block,
)

FULL_CHECK_COMMAND_CELL: Final[str] = "LST CELL"
FULL_CHECK_COMMAND_ENODEB: Final[str] = "LST ENODEBFUNCTION"
FULL_CHECK_COMMAND_CNOPERATORTA: Final[str] = "LST CNOPERATORTA"
ENODEB_ID_FIELD: Final[str] = "eNodeB ID"
CNOPERATORTA_TAC_FIELD: Final[str] = "Tracking area code"
LTE_CELL_NAME_FIELD: Final[str] = "Cell Name"
LTE_CELL_ID_FIELD: Final[str] = "Cell ID"
LTE_LOCAL_CELL_ID_FIELD: Final[str] = "Local Cell ID"
LTE_PCI_FIELD: Final[str] = "Physical cell ID"


@dataclass(frozen=True)
class LteCellRecord:
    cell_name: str
    cell_id: str
    local_cell_id: str = ""
    pci: str = ""

    def as_dict(self) -> dict:
        return {
            "cell_name": self.cell_name,
            "cell_id": self.cell_id,
            "local_cell_id": self.local_cell_id,
            "pci": self.pci,
        }


@dataclass(frozen=True)
class FullCheck4GExtraction:
    """Values extracted from a 4G full-check (pos-check) return."""

    cells: tuple[LteCellRecord, ...]
    enodeb_id: str
    tac: str
    ne_name: str
    cell_block: MmlCommandBlock
    commands: tuple[CommandExecutionStatus, ...]
    enodeb_function: MmlCommandBlock | None = None
    cn_operator_ta: MmlCommandBlock | None = None

    def as_dict(self) -> dict:
        return {
            "enodeb_id": self.enodeb_id,
            "tac": self.tac,
            "ne_name": self.ne_name,
            "cells": [cell.as_dict() for cell in self.cells],
            "commands": [item.as_dict() for item in self.commands],
        }


def parse_full_check_4g_return(text: str) -> FullCheck4GExtraction:
    """Parse a Claro 4G full-check (pos-check) Gerencia return."""
    content = (text or "").strip()
    if not content:
        raise PoscheckParseError("Execution failure", [empty_return()])

    blocks = parse_blocks(content)
    if not blocks:
        raise PoscheckParseError("Execution failure", [unrecognized_format()])

    enriched: list[MmlCommandBlock] = []
    for block in blocks:
        if block.command.upper() == FULL_CHECK_COMMAND_CELL:
            rows = _extract_lte_cell_rows(block.raw)
            result_count = block.result_count if block.result_count is not None else (len(rows) or None)
            block = MmlCommandBlock(
                command=block.command,
                ne_name=block.ne_name,
                retcode=block.retcode,
                retcode_message=block.retcode_message,
                fields=block.fields,
                rows=rows,
                result_count=result_count,
                raw=block.raw,
            )
        enriched.append(block)
    blocks = enriched

    by_command: dict[str, MmlCommandBlock] = {}
    cell_rows: list[dict[str, str]] = []
    for block in blocks:
        key = block.command.upper()
        if key == FULL_CHECK_COMMAND_CELL:
            cell_rows.extend(block.rows)
        existing = by_command.get(key)
        if existing is None:
            by_command[key] = block
        elif not existing.fields and block.fields:
            by_command[key] = block
        elif key == FULL_CHECK_COMMAND_CELL and block.rows and not existing.rows:
            by_command[key] = block

    cell_block = by_command.get(FULL_CHECK_COMMAND_CELL)
    if cell_block is None:
        raise PoscheckParseError(
            "Execution failure",
            explain_missing_commands("4G", by_command, [missing_command(FULL_CHECK_COMMAND_CELL)]),
        )

    issues = validate_block(cell_block, required_fields=())
    if not issues and not cell_rows:
        issues.append(missing_field(FULL_CHECK_COMMAND_CELL, LTE_CELL_NAME_FIELD))
    if issues:
        raise PoscheckParseError("Execution failure", issues)

    cells = tuple(
        LteCellRecord(
            cell_name=normalize_value(row[LTE_CELL_NAME_FIELD]),
            cell_id=normalize_value(row.get(LTE_CELL_ID_FIELD) or row.get(LTE_LOCAL_CELL_ID_FIELD) or ""),
            local_cell_id=normalize_value(row.get(LTE_LOCAL_CELL_ID_FIELD) or ""),
            pci=normalize_value(row.get(LTE_PCI_FIELD) or ""),
        )
        for row in cell_rows
        if row.get(LTE_CELL_NAME_FIELD)
    )
    if not cells:
        raise PoscheckParseError(
            "Execution failure",
            [missing_field(FULL_CHECK_COMMAND_CELL, LTE_CELL_NAME_FIELD)],
        )

    enodeb_function = by_command.get(FULL_CHECK_COMMAND_ENODEB)
    if enodeb_function is None:
        raise PoscheckParseError(
            "Execution failure",
            explain_missing_commands("4G", by_command, [missing_command(FULL_CHECK_COMMAND_ENODEB)]),
        )
    issues = validate_block(enodeb_function, required_fields=(ENODEB_ID_FIELD,))
    if issues:
        raise PoscheckParseError("Execution failure", issues)
    enodeb_id = normalize_value(enodeb_function.fields[ENODEB_ID_FIELD])

    cn_operator_ta = by_command.get(FULL_CHECK_COMMAND_CNOPERATORTA)
    tac = ""
    if cn_operator_ta is not None:
        issues = validate_block(cn_operator_ta, required_fields=(CNOPERATORTA_TAC_FIELD,))
        if issues:
            raise PoscheckParseError("Execution failure", issues)
        tac = normalize_value(cn_operator_ta.fields[CNOPERATORTA_TAC_FIELD])

    commands = tuple(
        CommandExecutionStatus(
            command=block.command,
            retcode=block.retcode,
            ok=block.retcode == 0,
        )
        for block in blocks
    )
    ne_name = cell_block.ne_name or enodeb_function.ne_name
    return FullCheck4GExtraction(
        cells=cells,
        enodeb_id=enodeb_id,
        tac=tac,
        ne_name=ne_name,
        cell_block=cell_block,
        commands=commands,
        enodeb_function=enodeb_function,
        cn_operator_ta=cn_operator_ta,
    )


def parse_full_check_4g_return_bytes(payload: bytes, *, encoding: str = "utf-8") -> FullCheck4GExtraction:
    return parse_full_check_4g_return(decode_payload(payload, encoding=encoding))


def _extract_lte_cell_rows(chunk: str) -> tuple[dict[str, str], ...]:
    """Extract LTE LST CELL table rows using header column positions."""
    lines = chunk.splitlines()
    header_idx = None
    header = ""
    for index, line in enumerate(lines):
        if "Local Cell ID" in line and "Cell Name" in line:
            header_idx = index
            header = line
            break
    if header_idx is None:
        return ()

    local_pos = header.find("Local Cell ID")
    name_pos = header.find("Cell Name")
    cell_id_pos = header.find("Cell ID", local_pos + len("Local Cell ID"))
    pci_pos = header.find("Physical cell ID")

    def _slice(line: str, start: int, end: int | None) -> str:
        if start < 0 or start >= len(line):
            return ""
        segment = line[start : end if end is not None else len(line)]
        return segment.strip().split()[0] if segment.strip() else ""

    ends = {
        "local": name_pos if name_pos >= 0 else None,
        "name": (cell_id_pos if cell_id_pos >= 0 else (pci_pos if pci_pos >= 0 else None)),
        "cell_id": pci_pos if pci_pos >= 0 else None,
        "pci": None,
    }

    rows: list[dict[str, str]] = []
    for line in lines[header_idx + 1 :]:
        stripped = line.strip()
        if not stripped or stripped.startswith("-"):
            continue
        if stripped.startswith("(") or stripped.startswith("To be"):
            break
        if not stripped[0].isdigit():
            continue
        local_id = _slice(line, local_pos, ends["local"])
        cell_name = _slice(line, name_pos, ends["name"])
        cell_id = _slice(line, cell_id_pos, ends["cell_id"]) if cell_id_pos >= 0 else ""
        pci = _slice(line, pci_pos, ends["pci"]) if pci_pos >= 0 else ""
        if not cell_name:
            continue
        rows.append(
            {
                LTE_LOCAL_CELL_ID_FIELD: local_id,
                LTE_CELL_NAME_FIELD: cell_name,
                LTE_CELL_ID_FIELD: cell_id or local_id,
                LTE_PCI_FIELD: pci,
            }
        )
    return tuple(rows)
