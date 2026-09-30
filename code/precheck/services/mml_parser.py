"""Parse Huawei MML Gerência returns for Claro 5G pre-check."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final

from precheck.services.errors import (
    PrecheckParseError,
    command_failed,
    empty_return,
    explain_missing_commands,
    missing_command,
    missing_field,
    no_records,
    unrecognized_format,
)

PRECHECK_COMMAND_GNODEB: Final[str] = "LST GNODEBFUNCTION"
PRECHECK_COMMAND_TRACKING_AREA: Final[str] = "LST GNBTRACKINGAREA"
PRECHECK_COMMANDS: Final[tuple[str, ...]] = (
    PRECHECK_COMMAND_GNODEB,
    PRECHECK_COMMAND_TRACKING_AREA,
)

GNODEB_ID_FIELD: Final[str] = "gNodeB ID"
TRACKING_AREA_CODE_FIELD: Final[str] = "Tracking Area Code"

_BLOCK_SPLIT_RE = re.compile(r"(?m)^---\s+END\s*$")
_COMMAND_MARKER_RE = re.compile(
    r"%%/\*\d+\*/\s*(?P<command>[A-Z0-9 ]+?)(?::;)?\s*%%",
    re.IGNORECASE,
)
_LEADING_COMMAND_RE = re.compile(
    r"^\s*(?P<command>LST\s+[A-Z0-9]+)\s*:?;?\s*$",
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
_NE_LINE_RE = re.compile(r"(?m)^\+\+\+\s+(?P<ne>\S+)")


@dataclass(frozen=True)
class MmlCommandBlock:
    command: str
    ne_name: str
    retcode: int
    retcode_message: str
    fields: dict[str, str] = field(default_factory=dict)
    result_count: int | None = None
    raw: str = ""


@dataclass(frozen=True)
class PrecheckExtraction:
    """Values extracted from a pre-check (or multi-command) return."""

    gnodeb_id: str
    tracking_area_code: str
    ne_name: str
    gnodeb_function: MmlCommandBlock
    tracking_area: MmlCommandBlock

    def as_dict(self) -> dict:
        return {
            "gnodeb_id": self.gnodeb_id,
            "tracking_area_code": self.tracking_area_code,
            "ne_name": self.ne_name,
            "commands": {
                self.gnodeb_function.command: {
                    "retcode": self.gnodeb_function.retcode,
                    "fields": self.gnodeb_function.fields,
                    "result_count": self.gnodeb_function.result_count,
                },
                self.tracking_area.command: {
                    "retcode": self.tracking_area.retcode,
                    "fields": self.tracking_area.fields,
                    "result_count": self.tracking_area.result_count,
                },
            },
        }


def parse_precheck_return(text: str) -> PrecheckExtraction:
    """Locate and validate the two Claro 5G pre-check commands in a return.

    Extra commands (for example a Full Check dump) are ignored.
    """
    content = (text or "").strip()
    if not content:
        raise PrecheckParseError("Execution failure", [empty_return()])

    blocks = _parse_blocks(content)
    if not blocks:
        raise PrecheckParseError("Execution failure", [unrecognized_format()])

    by_command = {block.command.upper(): block for block in blocks}
    issues = []
    gnodeb = by_command.get(PRECHECK_COMMAND_GNODEB)
    tracking = by_command.get(PRECHECK_COMMAND_TRACKING_AREA)

    if gnodeb is None:
        issues.append(missing_command(PRECHECK_COMMAND_GNODEB))
    if tracking is None:
        issues.append(missing_command(PRECHECK_COMMAND_TRACKING_AREA))
    if issues:
        raise PrecheckParseError(
            "Execution failure",
            explain_missing_commands("5G", by_command, issues),
        )

    assert gnodeb is not None and tracking is not None
    issues.extend(_validate_block(gnodeb, required_fields=(GNODEB_ID_FIELD,)))
    issues.extend(_validate_block(tracking, required_fields=(TRACKING_AREA_CODE_FIELD,)))
    if issues:
        raise PrecheckParseError("Execution failure", issues)

    ne_name = gnodeb.ne_name or tracking.ne_name
    return PrecheckExtraction(
        gnodeb_id=_normalize_value(gnodeb.fields[GNODEB_ID_FIELD]),
        tracking_area_code=_normalize_value(tracking.fields[TRACKING_AREA_CODE_FIELD]),
        ne_name=ne_name,
        gnodeb_function=gnodeb,
        tracking_area=tracking,
    )


def parse_precheck_return_bytes(payload: bytes, *, encoding: str = "utf-8") -> PrecheckExtraction:
    """Decode bytes then parse. Tries utf-8 then latin-1 fallback."""
    if not payload:
        raise PrecheckParseError("Execution failure", [empty_return()])
    try:
        text = payload.decode(encoding)
    except UnicodeDecodeError:
        try:
            text = payload.decode("latin-1")
        except UnicodeDecodeError as exc:
            raise PrecheckParseError("Execution failure", [unrecognized_format()]) from exc
    return parse_precheck_return(text)


def _parse_blocks(content: str) -> list[MmlCommandBlock]:
    chunks = [chunk.strip() for chunk in _BLOCK_SPLIT_RE.split(content) if chunk.strip()]
    blocks: list[MmlCommandBlock] = []
    for chunk in chunks:
        block = _parse_block(chunk)
        if block is not None:
            blocks.append(block)
    return blocks


def _parse_block(chunk: str) -> MmlCommandBlock | None:
    command = _extract_command(chunk)
    if not command:
        return None

    retcode_match = _RETCODE_RE.search(chunk)
    if retcode_match is None:
        # Not a recognizable command result block.
        return None

    retcode = int(retcode_match.group("code"))
    retcode_message = retcode_match.group("message").strip()
    ne_match = _NE_LINE_RE.search(chunk)
    ne_name = ne_match.group("ne") if ne_match else ""
    if not ne_name:
        # Fallback: second line is often the NE name.
        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        if len(lines) >= 2 and not lines[1].startswith(("+++", "O&M", "%%", "RETCODE")):
            ne_name = lines[1]

    fields = _extract_fields(chunk)
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


def _extract_command(chunk: str) -> str | None:
    marker = _COMMAND_MARKER_RE.search(chunk)
    if marker:
        return _normalize_command(marker.group("command"))
    leading = _LEADING_COMMAND_RE.search(chunk)
    if leading:
        return _normalize_command(leading.group("command"))
    return None


def _normalize_command(command: str) -> str:
    return re.sub(r"\s+", " ", command.strip()).upper()


def _extract_fields(chunk: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for match in _KV_RE.finditer(chunk):
        key = match.group("key").strip()
        value = match.group("value").strip()
        # Skip RETCODE which uses the same pattern.
        if key.upper() == "RETCODE":
            continue
        fields[key] = value
    return fields


def _validate_block(block: MmlCommandBlock, *, required_fields: tuple[str, ...]) -> list:
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


def _normalize_value(value: str) -> str:
    return value.strip()
