"""Typed pre-check errors with user-facing English messages."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PrecheckIssue:
    code: str
    message: str
    command: str | None = None
    field: str | None = None
    severity: str = "error"

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "command": self.command,
            "field": self.field,
            "severity": self.severity,
        }


@dataclass
class PrecheckParseError(Exception):
    """Raised when a Gerência return cannot be interpreted for pre-check."""

    title: str
    issues: list[PrecheckIssue] = field(default_factory=list)

    def __str__(self) -> str:
        if self.issues:
            return f"{self.title}: {self.issues[0].message}"
        return self.title

    @property
    def message(self) -> str:
        return str(self)

    @property
    def code(self) -> str:
        return self.issues[0].code if self.issues else "PRECHECK_PARSE_ERROR"


def empty_return() -> PrecheckIssue:
    return PrecheckIssue(
        code="EMPTY_RETURN",
        message="The return file is empty.",
    )


def unrecognized_format() -> PrecheckIssue:
    return PrecheckIssue(
        code="UNRECOGNIZED_FORMAT",
        message="The return format was not recognized. Use the original Gerência output.",
    )


_TECH_COMMANDS: dict[str, tuple[str, ...]] = {
    "2G": ("LST GCELL",),
    "3G": ("LST UCELL", "LST UCNOPERATOR"),
    "4G": ("LST CELL", "LST ENODEBFUNCTION", "LST CNOPERATORTA"),
    "5G": (
        "LST GNODEBFUNCTION",
        "LST GNBTRACKINGAREA",
        "LST NRCELL",
        "LST NRDUCELL",
        "DSP NRDUCELL",
    ),
}
_TECH_LABELS: dict[str, str] = {
    "2G": "2G",
    "3G": "3G",
    "4G": "4G LTE",
    "5G": "5G NR",
}


def explain_missing_commands(
    expected_technology: str,
    present_commands,
    issues: list[PrecheckIssue],
) -> list[PrecheckIssue]:
    """Prefix a plain reason when the return does not match the selected technology."""
    if not any(issue.code == "MISSING_COMMAND" for issue in issues):
        return issues
    expected = "5G" if expected_technology == "5G NR" else expected_technology
    present = {str(command).upper() for command in present_commands}
    expected_cmds = set(_TECH_COMMANDS.get(expected, ()))
    if expected_cmds & present:
        return issues

    detected = None
    found: list[str] = []
    for tech, commands in _TECH_COMMANDS.items():
        if tech == expected:
            continue
        overlap = [command for command in commands if command in present]
        if overlap and (detected is None or len(overlap) > len(found)):
            detected = tech
            found = overlap

    expected_label = _TECH_LABELS.get(expected, expected)
    if detected:
        message = (
            f"The MML return is not compatible with {expected_label}. "
            f"It matches {_TECH_LABELS[detected]} ({', '.join(found)}) "
            "and does not contain the commands expected for this input."
        )
    else:
        expected_list = ", ".join(_TECH_COMMANDS.get(expected, ())) or "the selected technology"
        message = (
            f"The MML return is not compatible with {expected_label}. "
            f"None of the expected commands were found ({expected_list})."
        )
    return [PrecheckIssue(code="INCOMPATIBLE_RETURN", message=message), *issues]


def missing_command(command: str) -> PrecheckIssue:
    return PrecheckIssue(
        code="MISSING_COMMAND",
        message=f"Command '{command}' was not found in the return file.",
        command=command,
    )


def command_failed(command: str, retcode: int, detail: str = "") -> PrecheckIssue:
    suffix = f" {detail}".rstrip() if detail else ""
    return PrecheckIssue(
        code="COMMAND_FAILED",
        message=f"Command '{command}' failed with RETCODE={retcode}.{suffix}",
        command=command,
    )


def missing_field(command: str, field: str) -> PrecheckIssue:
    return PrecheckIssue(
        code="MISSING_FIELD",
        message=f"Required field '{field}' was not found in '{command}'.",
        command=command,
        field=field,
    )


def no_records(command: str) -> PrecheckIssue:
    return PrecheckIssue(
        code="NO_RECORDS",
        message=f"Command '{command}' returned no records.",
        command=command,
    )


def missing_return_file() -> PrecheckIssue:
    return PrecheckIssue(
        code="MISSING_RETURN_FILE",
        message="Import the Pre-check result file before processing the analysis.",
    )


def analysis_busy() -> PrecheckIssue:
    return PrecheckIssue(
        code="ANALYSIS_BUSY",
        message="This analysis is already being updated. Try again in a moment.",
    )


def precheck_not_selected() -> PrecheckIssue:
    return PrecheckIssue(
        code="PRECHECK_NOT_SELECTED",
        message="Pre-check is not part of this analysis.",
    )


def technology_not_supported(technology: str) -> PrecheckIssue:
    return PrecheckIssue(
        code="TECHNOLOGY_NOT_SUPPORTED",
        message=f"Pre-check is available only for 5G NR. Selected technology: {technology}.",
    )


def selected_cells_missing(missing: list[str]) -> PrecheckIssue:
    if not missing:
        return PrecheckIssue(
            code="SELECTED_CELLS_MISSING",
            message="Select at least one cell before running pre-check.",
        )
    names = ", ".join(missing[:5])
    suffix = "…" if len(missing) > 5 else ""
    return PrecheckIssue(
        code="SELECTED_CELLS_MISSING",
        message=f"Selected cells were not found in the imported EP: {names}{suffix}.",
    )


def ep_field_missing(field: str) -> PrecheckIssue:
    return PrecheckIssue(
        code="EP_FIELD_MISSING",
        message=f"Required EP field '{field}' is missing for the selected site cells.",
        field=field,
    )


def ep_field_inconsistent(field: str) -> PrecheckIssue:
    return PrecheckIssue(
        code="EP_FIELD_INCONSISTENT",
        message=f"EP field '{field}' is not consistent across the selected site cells.",
        field=field,
    )


@dataclass
class PrecheckError(Exception):
    """Raised for pre-check prerequisites or EP resolution failures."""

    title: str
    issues: list[PrecheckIssue] = field(default_factory=list)

    def __str__(self) -> str:
        if self.issues:
            return f"{self.title}: {self.issues[0].message}"
        return self.title

    @property
    def message(self) -> str:
        return str(self)

    @property
    def code(self) -> str:
        return self.issues[0].code if self.issues else "PRECHECK_ERROR"
