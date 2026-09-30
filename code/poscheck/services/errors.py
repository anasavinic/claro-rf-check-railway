"""Re-export precheck errors with thin Full Check aliases."""

from __future__ import annotations

from precheck.services.errors import (  # noqa: F401
    PrecheckError,
    PrecheckIssue,
    PrecheckParseError,
    analysis_busy,
    command_failed,
    empty_return,
    ep_field_inconsistent,
    ep_field_missing,
    explain_missing_commands,
    missing_command,
    missing_field,
    missing_return_file,
    no_records,
    precheck_not_selected,
    selected_cells_missing,
    technology_not_supported,
    unrecognized_format,
)

PoscheckError = PrecheckError
PoscheckIssue = PrecheckIssue
PoscheckParseError = PrecheckParseError


def full_check_not_selected() -> PrecheckIssue:
    return PrecheckIssue(
        code="FULL_CHECK_NOT_SELECTED",
        message="Full Check is not part of this analysis.",
    )


def missing_full_check_return_file() -> PrecheckIssue:
    return PrecheckIssue(
        code="MISSING_RETURN_FILE",
        message="Import the Full Check result file before processing the analysis.",
    )
