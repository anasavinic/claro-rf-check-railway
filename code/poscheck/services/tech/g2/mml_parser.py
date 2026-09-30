"""Parse Huawei MML Gerencia returns for Claro 2G Full Check."""

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
    extract_cell_id,
    extract_cell_name,
    normalize_value,
    parse_aligned_table,
    parse_blocks,
    validate_block,
)

FULL_CHECK_COMMAND_GCELL: Final[str] = "LST GCELL"
GCELL_CELL_NAME_FIELD: Final[str] = "Cell Name"
GCELL_CELL_CI_FIELD: Final[str] = "Cell CI"
GCELL_BTS_NAME_FIELD: Final[str] = "BTS Name"
GCELL_LAC_FIELD: Final[str] = "Cell LAC"
GCELL_BCCH_FIELD: Final[str] = "BCCH Frequency"

_GCELL_TABLE_COLUMNS: Final[tuple[str, ...]] = (
    GCELL_CELL_NAME_FIELD,
    GCELL_CELL_CI_FIELD,
    GCELL_BTS_NAME_FIELD,
    GCELL_LAC_FIELD,
    GCELL_BCCH_FIELD,
)


@dataclass(frozen=True)
class GsmCellRecord:
    cell_name: str
    cell_id: str
    bts_name: str
    lac: str
    bcch_frequency: str

    def as_dict(self) -> dict:
        return {
            "cell_name": self.cell_name,
            "cell_id": self.cell_id,
            "bts_name": self.bts_name,
            "lac": self.lac,
            "bcch_frequency": self.bcch_frequency,
        }


@dataclass(frozen=True)
class FullCheck2GExtraction:
    """Values extracted from a 2G full-check (pos-check) return."""

    cells: tuple[GsmCellRecord, ...]
    bsc: str
    bts_name: str
    ne_name: str
    gcell: MmlCommandBlock
    commands: tuple[CommandExecutionStatus, ...]

    def as_dict(self) -> dict:
        return {
            "bsc": self.bsc,
            "bts_name": self.bts_name,
            "ne_name": self.ne_name,
            "cells": [cell.as_dict() for cell in self.cells],
            "commands": [item.as_dict() for item in self.commands],
        }


def parse_full_check_2g_return(text: str) -> FullCheck2GExtraction:
    """Parse a Claro 2G full-check (pos-check) Gerencia return."""
    content = (text or "").strip()
    if not content:
        raise PoscheckParseError("Execution failure", [empty_return()])

    blocks = parse_blocks(content)
    if not blocks:
        raise PoscheckParseError("Execution failure", [unrecognized_format()])

    enriched: list[MmlCommandBlock] = []
    for block in blocks:
        if block.command.upper() == FULL_CHECK_COMMAND_GCELL:
            rows = _extract_gcell_rows(block.raw)
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

    gcell = next((block for block in blocks if block.command.upper() == FULL_CHECK_COMMAND_GCELL), None)
    if gcell is None:
        raise PoscheckParseError(
            "Execution failure",
            explain_missing_commands(
                "2G",
                {block.command for block in blocks},
                [missing_command(FULL_CHECK_COMMAND_GCELL)],
            ),
        )

    issues = validate_block(gcell, required_fields=())
    if not issues and not gcell.rows:
        issues.append(missing_field(FULL_CHECK_COMMAND_GCELL, GCELL_CELL_NAME_FIELD))
    if issues:
        raise PoscheckParseError("Execution failure", issues)

    cells = tuple(
        GsmCellRecord(
            cell_name=normalize_value(row.get(GCELL_CELL_NAME_FIELD, "")),
            cell_id=normalize_value(row.get(GCELL_CELL_CI_FIELD, "")),
            bts_name=normalize_value(row.get(GCELL_BTS_NAME_FIELD, "")),
            lac=normalize_value(row.get(GCELL_LAC_FIELD, "")),
            bcch_frequency=normalize_value(row.get(GCELL_BCCH_FIELD, "")),
        )
        for row in gcell.rows
        if row.get(GCELL_CELL_NAME_FIELD)
    )
    if not cells:
        raise PoscheckParseError(
            "Execution failure",
            [missing_field(FULL_CHECK_COMMAND_GCELL, GCELL_CELL_NAME_FIELD)],
        )

    bts_names = {cell.bts_name for cell in cells if cell.bts_name}
    bts_name = next(iter(bts_names)) if bts_names else ""
    commands = tuple(
        CommandExecutionStatus(
            command=block.command,
            retcode=block.retcode,
            cell_id=extract_cell_id(block.raw),
            cell_name=extract_cell_name(block.raw),
            ok=block.retcode == 0,
        )
        for block in blocks
    )
    ne_name = gcell.ne_name
    return FullCheck2GExtraction(
        cells=cells,
        bsc=ne_name,
        bts_name=bts_name,
        ne_name=ne_name,
        gcell=gcell,
        commands=commands,
    )


def parse_full_check_2g_return_bytes(payload: bytes, *, encoding: str = "utf-8") -> FullCheck2GExtraction:
    return parse_full_check_2g_return(decode_payload(payload, encoding=encoding))


def _extract_gcell_rows(chunk: str) -> tuple[dict[str, str], ...]:
    return parse_aligned_table(chunk, required_columns=_GCELL_TABLE_COLUMNS)
