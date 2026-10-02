"""Shared Huawei MML block parsing for Full Check returns."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final

from poscheck.services.errors import (
    PoscheckParseError,
    command_failed,
    empty_return,
    missing_field,
    no_records,
    unrecognized_format,
)

_BLOCK_SPLIT_RE = re.compile(r"(?m)^---\s+END\s*$")
_COMMAND_MARKER_RE = re.compile(
    r"%%/\*\d+(?:\s+[^*]*?)?\*/\s*(?P<command>[A-Z0-9 ]+?)(?::|;|%%)",
    re.IGNORECASE,
)
_TASK_COMMAND_RE = re.compile(
    r"(?m)^MML Command-+(?P<command>(?:LST|DSP|CHK)\s+[A-Z0-9]+)",
    re.IGNORECASE,
)
_LEADING_COMMAND_RE = re.compile(
    r"^\s*(?P<command>(?:LST|DSP|CHK)\s+[A-Z0-9]+)(?:\s*:|\s*;|\s*$)",
    re.IGNORECASE | re.MULTILINE,
)
_RETCODE_RE = re.compile(
    r"(?m)^RETCODE\s*=\s*(?P<code>-?\d+)\s*(?P<message>.*)$",
)
_KV_RE = re.compile(r"(?m)^\s*(?P<key>.+?)\s+=\s+(?P<value>.*\S)\s*$")
_RESULT_COUNT_RE = re.compile(
    r"\(Number of results\s*=\s*(?P<count>\d+)\)",
    re.IGNORECASE,
)
_NE_LINE_RE = re.compile(r"(?m)^(?:Report\s*:\s*)?\+\+\+\s+(?P<ne>\S+)")
_NE_LABEL_RE = re.compile(r"(?m)^NE\s*:\s*(?P<ne>\S+)\s*$")
_CELLID_IN_COMMAND_RE = re.compile(r"CELLID\s*=\s*(?P<cell_id>\d+)", re.IGNORECASE)
_CELLNAME_IN_COMMAND_RE = re.compile(
    r"(?:SRC2GNCELLNAME|SRC3GNCELLNAME|SRCLTENCELLNAME|CELLNAME)\s*=\s*\"(?P<cell_name>[^\"]+)\"",
    re.IGNORECASE,
)

PREFIX_MATCH_COMMANDS: Final[frozenset[str]] = frozenset({"DSP BRDMFRINFO", "CHK DATA2LIC"})


@dataclass(frozen=True)
class MmlCommandBlock:
    command: str
    ne_name: str
    retcode: int
    retcode_message: str
    fields: dict[str, str] = field(default_factory=dict)
    rows: tuple[dict[str, str], ...] = ()
    result_count: int | None = None
    raw: str = ""


@dataclass(frozen=True)
class CommandExecutionStatus:
    command: str
    retcode: int
    cell_id: str = ""
    cell_name: str = ""
    ok: bool = False

    def as_dict(self) -> dict:
        return {
            "command": self.command,
            "retcode": self.retcode,
            "cell_id": self.cell_id,
            "cell_name": self.cell_name,
            "ok": self.ok,
        }


def decode_payload(payload: bytes, *, encoding: str = "utf-8") -> str:
    if not payload:
        raise PoscheckParseError("Execution failure", [empty_return()])
    try:
        return payload.decode(encoding)
    except UnicodeDecodeError:
        try:
            return payload.decode("latin-1")
        except UnicodeDecodeError as exc:
            raise PoscheckParseError("Execution failure", [unrecognized_format()]) from exc


def parse_blocks(content: str) -> list[MmlCommandBlock]:
    chunks = [chunk.strip() for chunk in _BLOCK_SPLIT_RE.split(content) if chunk.strip()]
    blocks: list[MmlCommandBlock] = []
    for chunk in chunks:
        block = parse_block(chunk)
        if block is not None:
            blocks.append(block)
    return blocks


def parse_block(chunk: str) -> MmlCommandBlock | None:
    command = extract_command(chunk)
    if not command:
        return None

    retcode_match = _RETCODE_RE.search(chunk)
    if retcode_match is None:
        return None

    retcode = int(retcode_match.group("code"))
    retcode_message = retcode_match.group("message").strip()
    ne_name = _extract_ne_name(chunk)

    fields = extract_fields(chunk)
    count_match = _RESULT_COUNT_RE.search(chunk)
    result_count = int(count_match.group("count")) if count_match else None

    return MmlCommandBlock(
        command=command.upper(),
        ne_name=ne_name,
        retcode=retcode,
        retcode_message=retcode_message,
        fields=fields,
        result_count=result_count,
        raw=chunk,
    )


def _extract_ne_name(chunk: str) -> str:
    label = _NE_LABEL_RE.search(chunk)
    if label:
        return label.group("ne")
    ne_match = _NE_LINE_RE.search(chunk)
    if ne_match:
        return ne_match.group("ne")
    lines = [line.strip() for line in chunk.splitlines() if line.strip()]
    if len(lines) >= 2 and not lines[1].startswith(("+++", "O&M", "%%", "RETCODE", "NE", "Report")):
        return lines[1]
    return ""


def extract_command(chunk: str) -> str | None:
    marker = _COMMAND_MARKER_RE.search(chunk)
    if marker:
        return normalize_command(marker.group("command"))
    task = _TASK_COMMAND_RE.search(chunk)
    if task:
        return normalize_command(task.group("command"))
    leading = _LEADING_COMMAND_RE.search(chunk)
    if leading:
        return normalize_command(leading.group("command"))
    return None


def normalize_command(command: str) -> str:
    return re.sub(r"\s+", " ", command.strip()).upper()


def command_base_name(command_line: str) -> str:
    """Strip parameters from an MML command line (e.g. 'LST NRCELL:;' -> 'LST NRCELL')."""
    text = (command_line or "").strip()
    if ":" in text:
        text = text.split(":", 1)[0]
    text = text.rstrip(";").strip()
    return normalize_command(text)


def extract_fields(chunk: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for match in _KV_RE.finditer(chunk):
        key = match.group("key").strip()
        value = match.group("value").strip()
        if key.upper() == "RETCODE":
            continue
        fields[key] = value
    return fields


def extract_cell_id(raw: str) -> str:
    match = _CELLID_IN_COMMAND_RE.search(raw or "")
    return match.group("cell_id") if match else ""


def extract_cell_name(raw: str) -> str:
    match = _CELLNAME_IN_COMMAND_RE.search(raw or "")
    return match.group("cell_name") if match else ""


def validate_block(block: MmlCommandBlock, *, required_fields: tuple[str, ...]) -> list:
    issues = []
    if block.retcode != 0:
        issues.append(command_failed(block.command, block.retcode, block.retcode_message))
        return issues
    if block.result_count == 0:
        issues.append(no_records(block.command))
        return issues
    for field_name in required_fields:
        value = block.fields.get(field_name)
        if value is None or value == "" or value.upper() == "NULL":
            issues.append(missing_field(block.command, field_name))
    return issues


def normalize_value(value: str) -> str:
    return value.strip()


def parse_aligned_table(chunk: str, *, required_columns: tuple[str, ...]) -> tuple[dict[str, str], ...]:
    """Parse a space-aligned MML result table using header column offsets.

    All header columns define slice boundaries so intermediate columns do not
    bleed into the requested fields.
    """
    lines = chunk.splitlines()
    header_idx = -1
    header_line = ""
    for idx, line in enumerate(lines):
        stripped = line.rstrip()
        if all(col in stripped for col in required_columns):
            header_idx = idx
            header_line = stripped
            break
    if header_idx < 0:
        return ()

    # Split on 2+ spaces so "NR Cell ID" and "Cell ID" stay distinct.
    header_parts = [part for part in re.split(r"\s{2,}", header_line.strip()) if part]
    if not all(col in header_parts for col in required_columns):
        # Fallback: locate only required columns left-to-right.
        positions: list[tuple[str, int]] = []
        cursor = 0
        for col in required_columns:
            pos = header_line.find(col, cursor)
            if pos < 0:
                return ()
            positions.append((col, pos))
            cursor = pos + len(col)
    else:
        positions = []
        cursor = 0
        for part in header_parts:
            pos = header_line.find(part, cursor)
            if pos < 0:
                return ()
            positions.append((part, pos))
            cursor = pos + len(part)

    if not positions:
        return ()
    positions.sort(key=lambda item: item[1])
    required = set(required_columns)

    rows: list[dict[str, str]] = []
    for line in lines[header_idx + 1 :]:
        raw = line.rstrip()
        if not raw.strip():
            continue
        if raw.strip().startswith("(") and "Number of results" in raw:
            break
        if raw.strip().startswith("---"):
            break
        if not any(ch.isalnum() for ch in raw):
            continue
        if all(col in raw for col in required_columns):
            continue

        row: dict[str, str] = {}
        for index, (col, start) in enumerate(positions):
            if col not in required:
                continue
            end = positions[index + 1][1] if index + 1 < len(positions) else len(raw)
            value = raw[start:end].strip() if start < len(raw) else ""
            row[col] = value
        if any(row.get(col) for col in required_columns):
            rows.append(row)
    return tuple(rows)


def find_command_status(
    commands: tuple[CommandExecutionStatus, ...],
    expected_command: str,
) -> CommandExecutionStatus | None:
    """Find a command execution by exact name or approved prefix match."""
    expected = normalize_command(expected_command)
    for item in commands:
        if item.command == expected:
            return item
    if expected in PREFIX_MATCH_COMMANDS:
        for item in commands:
            if item.command.startswith(expected):
                return item
    return None
