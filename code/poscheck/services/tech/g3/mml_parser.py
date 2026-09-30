"""Parse Huawei MML Gerencia returns for Claro 3G Full Check."""

from __future__ import annotations

import re
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
    extract_cell_id,
    normalize_value,
    parse_blocks,
    validate_block,
)

PRECHECK_COMMAND_UCELL: Final[str] = "LST UCELL"
PRECHECK_COMMAND_CNOPERATOR: Final[str] = "LST UCNOPERATOR"

UCELL_RNC_FIELD: Final[str] = "Logical RNC ID"
UCELL_CELL_ID_FIELD: Final[str] = "Cell ID"
UCELL_CELL_NAME_FIELD: Final[str] = "Cell Name"
CNOPERATOR_RNC_FIELD: Final[str] = "Logical RNC ID"

_UCELL_ROW_RE = re.compile(
    r"^\s*(?P<rnc>\d+)\s+(?P<cell_id>\d+)\s+(?P<cell_name>\S+)\b",
    re.MULTILINE,
)


@dataclass(frozen=True)
class UmtsCellRecord:
    rnc_id: str
    cell_id: str
    cell_name: str

    def as_dict(self) -> dict:
        return {
            "rnc_id": self.rnc_id,
            "cell_id": self.cell_id,
            "cell_name": self.cell_name,
        }


@dataclass(frozen=True)
class FullCheck3GExtraction:
    """Values extracted from a 3G full-check (pos-check) return."""

    cells: tuple[UmtsCellRecord, ...]
    rnc_id: str
    ne_name: str
    ucell: MmlCommandBlock
    commands: tuple[CommandExecutionStatus, ...]
    cn_operator: MmlCommandBlock | None = None

    def as_dict(self) -> dict:
        return {
            "rnc_id": self.rnc_id,
            "ne_name": self.ne_name,
            "cells": [cell.as_dict() for cell in self.cells],
            "commands": [item.as_dict() for item in self.commands],
        }


def parse_full_check_3g_return(text: str) -> FullCheck3GExtraction:
    """Parse a Claro 3G full-check (pos-check) Gerencia return."""
    content = (text or "").strip()
    if not content:
        raise PoscheckParseError("Execution failure", [empty_return()])

    blocks = parse_blocks(content)
    if not blocks:
        raise PoscheckParseError("Execution failure", [unrecognized_format()])

    # Re-parse UCELL rows onto blocks (common parser leaves rows empty).
    enriched: list[MmlCommandBlock] = []
    for block in blocks:
        if block.command.upper() == PRECHECK_COMMAND_UCELL:
            rows = _extract_ucell_rows(block.raw)
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
    for block in blocks:
        key = block.command.upper()
        existing = by_command.get(key)
        if existing is None:
            by_command[key] = block
        elif not existing.fields and block.fields:
            by_command[key] = block
        elif not existing.rows and block.rows:
            by_command[key] = block

    ucell = by_command.get(PRECHECK_COMMAND_UCELL)
    if ucell is None:
        raise PoscheckParseError(
            "Execution failure",
            explain_missing_commands("3G", by_command, [missing_command(PRECHECK_COMMAND_UCELL)]),
        )

    issues = validate_block(ucell, required_fields=())
    if not issues and not ucell.rows:
        issues.append(missing_field(PRECHECK_COMMAND_UCELL, UCELL_CELL_NAME_FIELD))
    if issues:
        raise PoscheckParseError("Execution failure", issues)

    cells = tuple(
        UmtsCellRecord(
            rnc_id=normalize_value(row[UCELL_RNC_FIELD]),
            cell_id=normalize_value(row[UCELL_CELL_ID_FIELD]),
            cell_name=normalize_value(row[UCELL_CELL_NAME_FIELD]),
        )
        for row in ucell.rows
        if row.get(UCELL_CELL_NAME_FIELD)
    )
    if not cells:
        raise PoscheckParseError(
            "Execution failure",
            [missing_field(PRECHECK_COMMAND_UCELL, UCELL_CELL_NAME_FIELD)],
        )

    cn_operator = by_command.get(PRECHECK_COMMAND_CNOPERATOR)
    if cn_operator is not None and CNOPERATOR_RNC_FIELD not in cn_operator.fields:
        for block in blocks:
            if block.command.upper() == PRECHECK_COMMAND_CNOPERATOR and CNOPERATOR_RNC_FIELD in block.fields:
                cn_operator = block
                break
        else:
            cn_operator = None
    if cn_operator is not None:
        issues = validate_block(cn_operator, required_fields=(CNOPERATOR_RNC_FIELD,))
        if issues:
            raise PoscheckParseError("Execution failure", issues)
        rnc_id = normalize_value(cn_operator.fields[CNOPERATOR_RNC_FIELD])
    else:
        rnc_ids = {cell.rnc_id for cell in cells}
        rnc_id = next(iter(rnc_ids)) if len(rnc_ids) == 1 else cells[0].rnc_id

    commands = tuple(
        CommandExecutionStatus(
            command=block.command,
            retcode=block.retcode,
            cell_id=extract_cell_id(block.raw),
            ok=block.retcode == 0,
        )
        for block in blocks
    )
    ne_name = ucell.ne_name or (cn_operator.ne_name if cn_operator else "")
    return FullCheck3GExtraction(
        cells=cells,
        rnc_id=rnc_id,
        ne_name=ne_name,
        ucell=ucell,
        commands=commands,
        cn_operator=cn_operator,
    )


def parse_full_check_3g_return_bytes(payload: bytes, *, encoding: str = "utf-8") -> FullCheck3GExtraction:
    return parse_full_check_3g_return(decode_payload(payload, encoding=encoding))


def _extract_ucell_rows(chunk: str) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    for match in _UCELL_ROW_RE.finditer(chunk):
        rows.append(
            {
                UCELL_RNC_FIELD: match.group("rnc"),
                UCELL_CELL_ID_FIELD: match.group("cell_id"),
                UCELL_CELL_NAME_FIELD: match.group("cell_name"),
            }
        )
    return tuple(rows)
