from pathlib import Path

import pytest

from precheck.services.errors import PrecheckParseError
from precheck.services.mml_parser import (
    GNODEB_ID_FIELD,
    PRECHECK_COMMAND_GNODEB,
    PRECHECK_COMMAND_TRACKING_AREA,
    TRACKING_AREA_CODE_FIELD,
    parse_precheck_return,
    parse_precheck_return_bytes,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_precheck_only_return():
    result = parse_precheck_return(_load("precheck_only_5g_return.txt"))

    assert result.gnodeb_id == "1060541"
    assert result.tracking_area_code == "4151041"
    assert result.ne_name == "S01PRCLG21"
    assert result.gnodeb_function.command == PRECHECK_COMMAND_GNODEB
    assert result.tracking_area.command == PRECHECK_COMMAND_TRACKING_AREA
    assert result.gnodeb_function.fields[GNODEB_ID_FIELD] == "1060541"
    assert result.tracking_area.fields[TRACKING_AREA_CODE_FIELD] == "4151041"


def test_parse_full_check_return_ignores_extra_commands():
    """A Full Check dump is accepted when both pre-check commands are present."""
    result = parse_precheck_return(_load("full_check_5g_return.txt"))

    assert result.gnodeb_id == "1060541"
    assert result.tracking_area_code == "4151041"
    assert result.ne_name == "S01PRCLG21"
    assert "LST NRCELL" not in result.as_dict()["commands"]


def test_parse_precheck_return_bytes():
    payload = _load("full_check_5g_return.txt").encode("utf-8")
    result = parse_precheck_return_bytes(payload)
    assert result.gnodeb_id == "1060541"
    assert result.tracking_area_code == "4151041"


def test_missing_tracking_area_command():
    text = _load("precheck_only_5g_return.txt").split("LST GNBTRACKINGAREA:;")[0]

    with pytest.raises(PrecheckParseError) as exc:
        parse_precheck_return(text)

    assert any(issue.code == "MISSING_COMMAND" for issue in exc.value.issues)
    assert PRECHECK_COMMAND_TRACKING_AREA in exc.value.issues[0].message


def test_command_failed_retcode():
    text = _load("precheck_only_5g_return.txt").replace(
        "RETCODE = 0  Operation succeeded.",
        "RETCODE = 1  Operation failed.",
        1,
    )

    with pytest.raises(PrecheckParseError) as exc:
        parse_precheck_return(text)

    assert any(issue.code == "COMMAND_FAILED" for issue in exc.value.issues)


def test_missing_gnodeb_id_field():
    text = _load("precheck_only_5g_return.txt").replace(
        "gNodeB ID  =  1060541",
        "gNodeB ID Length(bit)  =  27",
        1,
    )

    with pytest.raises(PrecheckParseError) as exc:
        parse_precheck_return(text)

    assert any(issue.code == "MISSING_FIELD" and issue.field == GNODEB_ID_FIELD for issue in exc.value.issues)


def test_empty_return():
    with pytest.raises(PrecheckParseError) as exc:
        parse_precheck_return("   ")

    assert exc.value.issues[0].code == "EMPTY_RETURN"


def test_no_records():
    text = (
        _load("precheck_only_5g_return.txt")
        .replace(
            "(Number of results = 1)",
            "(Number of results = 0)",
            1,
        )
        .replace(
            "gNodeB ID  =  1060541",
            "gNodeB ID  =  NULL",
            1,
        )
    )

    with pytest.raises(PrecheckParseError) as exc:
        parse_precheck_return(text)

    assert any(issue.code == "NO_RECORDS" for issue in exc.value.issues)
