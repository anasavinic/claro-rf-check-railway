from pathlib import Path

import pytest

from poscheck.services.errors import PoscheckParseError
from poscheck.services.tech.g5.mml_parser import parse_full_check_5g_return

FIXTURES = Path(__file__).parent / "fixtures"


def test_mml_parser_5g_extracts_site_and_cells():
    text = (FIXTURES / "full_check_5g_return.txt").read_text(encoding="utf-8")
    extraction = parse_full_check_5g_return(text)

    assert extraction.ne_name == "S01PRCLG21"
    assert extraction.gnodeb_id == "1060541"
    assert extraction.tracking_area_code == "4151041"
    assert len(extraction.cells) == 3
    assert all(cell.activate_state == "Activated" for cell in extraction.cells)
    assert all(cell.nr_du_cell_state == "Normal" for cell in extraction.cells)
    assert all(
        item.ok for item in extraction.commands if item.command in {"LST NRCELL", "LST NRDUCELL", "DSP NRDUCELL"}
    )


def test_mml_parser_5g_reads_gerencia_task_session_marker():
    text = "\n".join(
        [
            "Script Task : Claro_RF_Check_Combined_FullCheck_5G",
            "==========Succeeded MML Command==========",
            "MML Command-----LST GNODEBFUNCTION:;",
            "NE : S01GOGNA83",
            "Report : +++    S01GOGNA83        2026-10-01 13:13:34",
            "%%/*1885279874 MML Session=1790871214*/LST GNODEBFUNCTION:;%%",
            "RETCODE = 0  Operation succeeded.",
            "                     gNodeB ID  =  203562",
            "(Number of results = 1)",
            "---    END",
            "",
        ]
    )
    from poscheck.services.mml_common import parse_blocks

    blocks = parse_blocks(text)
    assert len(blocks) == 1
    assert blocks[0].command == "LST GNODEBFUNCTION"
    assert blocks[0].ne_name == "S01GOGNA83"
    assert blocks[0].fields["gNodeB ID"] == "203562"


def test_mml_parser_5g_explains_incompatible_4g_return():
    text = "\n".join(
        [
            "LST CELL:;",
            "+++ ES01PRCLG21",
            "RETCODE = 0  Operation succeeded.",
            "---    END",
            "",
        ]
    )
    with pytest.raises(PoscheckParseError) as exc:
        parse_full_check_5g_return(text)

    assert exc.value.issues[0].code == "INCOMPATIBLE_RETURN"
    assert "not compatible with 5G NR" in exc.value.issues[0].message
    assert "4G LTE" in exc.value.issues[0].message
    assert "LST CELL" in exc.value.issues[0].message
