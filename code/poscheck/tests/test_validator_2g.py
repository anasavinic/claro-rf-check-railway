from pathlib import Path

import pytest

from ep_import.models import EpCell, ImportJob, ImportJobStatus
from ep_import.services.scripts import apply_identifier_substitutions, generate_full_check_2g_script
from poscheck.services.orchestrator import evaluate_poscheck, process_poscheck
from poscheck.services.tech.g2.mml_parser import parse_full_check_2g_return
from poscheck.services.tech.g2.validator import (
    VALIDATION_BSC,
    VALIDATION_CELL_ID,
    VALIDATION_COMMAND,
    VALIDATION_STATUS_CONSISTENT,
    VALIDATION_STATUS_INCONSISTENT,
    resolve_expected_2g,
)
from precheck.models import CheckAnalysis, CheckAnalysisStatus, PrecheckResultStatus

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def ep_job(db):
    return ImportJob.objects.create(
        original_filename="RNP_SRAN_ES_2g.xlsx",
        stored_file="ep_imports/test_2g.xlsx",
        status=ImportJobStatus.SUCCESS,
    )


def _add_2g_cell(
    job,
    *,
    cell_name: str,
    cell_id: int,
    lac: int = 1028,
    bcch: int,
    site="BS01ESALG01",
    bsc="BSCES36",
):
    return EpCell.objects.create(
        job=job,
        technology="2G",
        region="ES",
        site_name=site,
        cell_name=cell_name,
        raw={
            "*GSM CELL NAME": cell_name,
            "*CI": cell_id,
            "*BTS NAME": site,
            "BSC": bsc,
            "*LAC": lac,
            "*FREQUENCY OF BCCH": bcch,
        },
    )


def _analysis_2g(job, cells: list[str], **kwargs):
    defaults = {
        "ep_job": job,
        "technology": "2G",
        "site_name": "BS01ESALG01",
        "selected_cells": cells,
        "pre_check": False,
        "full_check": True,
        "status": CheckAnalysisStatus.AWAITING_RETURNS,
    }
    defaults.update(kwargs)
    return CheckAnalysis.objects.create(**defaults)


def test_apply_identifier_substitutions_covers_operational_keys():
    rendered = apply_identifier_substitutions(
        'LST GCELL:IDTYPE=BYNAME,BTSNAME="{BTS}"; LST X:CELL="{CELL}",CELLID={CELLID},BSC={BSC};',
        {"BSC": "BSCES36", "BTS": "BS01ESALG01", "CELL": "22S01ESALG0101", "CELLID": "21097"},
    )
    assert 'BTSNAME="BS01ESALG01"' in rendered
    assert 'CELL="22S01ESALG0101"' in rendered
    assert "CELLID=21097" in rendered
    assert "BSC=BSCES36" in rendered


def test_generate_full_check_2g_script_embeds_identifiers():
    script = generate_full_check_2g_script(
        bsc="BSCES36",
        bts="BS01ESALG01",
        cell_names=["22S01ESALG0101", "22S01ESALG0103"],
        cell_ids=["21097", "21099"],
    )
    assert 'LST GCELL:IDTYPE=BYNAME,BTSNAME="BS01ESALG01";' in script
    assert 'LST G2GNCELL:IDTYPE=BYNAME,SRC2GNCELLNAME="22S01ESALG0101";' in script
    assert 'LST G3GNCELL:IDTYPE=BYNAME,SRC3GNCELLNAME="22S01ESALG0103";' in script
    assert 'DSP GCELLSTAT:IDTYPE=BYNAME,BTSNAMELST="BS01ESALG01";' in script
    assert "LST PTPBVC:;" in script
    assert 'LST GCELLMAIOPLAN:IDTYPE=BYNAME,CELLNAME="22S01ESALG0103";' in script


def test_parse_full_check_2g_return_from_fixture():
    extraction = parse_full_check_2g_return(_load("full_check_2g_return.txt"))

    assert extraction.ne_name == "BSCES36"
    assert extraction.bsc == "BSCES36"
    assert extraction.bts_name == "BS01ESALG01"
    assert {cell.cell_name for cell in extraction.cells} == {
        "22S01ESALG0101",
        "22S01ESALG0102",
        "22S01ESALG0103",
    }
    by_name = {cell.cell_name: cell for cell in extraction.cells}
    assert by_name["22S01ESALG0101"].cell_id == "H'5269(21097)"
    assert by_name["22S01ESALG0101"].lac == "H'0404(1028)"
    assert by_name["22S01ESALG0101"].bcch_frequency == "89"
    assert any(
        item.command == "LST G2GNCELL" and item.cell_name == "22S01ESALG0101" and item.ok
        for item in extraction.commands
    )
    assert any(item.command == "DSP GCELLSTAT" and item.ok for item in extraction.commands)


@pytest.mark.django_db
def test_resolve_and_evaluate_2g_full_check_happy_path(ep_job):
    _add_2g_cell(ep_job, cell_name="22S01ESALG0101", cell_id=21097, bcch=89)
    _add_2g_cell(ep_job, cell_name="22S01ESALG0102", cell_id=21098, bcch=91)
    _add_2g_cell(ep_job, cell_name="22S01ESALG0103", cell_id=21099, bcch=93)
    analysis = _analysis_2g(
        ep_job,
        ["22S01ESALG0101", "22S01ESALG0102", "22S01ESALG0103"],
    )

    expected = resolve_expected_2g(analysis)
    assert expected.bsc == "BSCES36"
    assert expected.bts_name == "BS01ESALG01"
    assert len(expected.cells) == 3

    outcome = evaluate_poscheck(analysis, _load("full_check_2g_return.txt"))
    assert outcome.overall_status == PrecheckResultStatus.COMPLETED
    assert all(item["status"] == VALIDATION_STATUS_CONSISTENT for item in outcome.validations)
    assert any(item["code"] == VALIDATION_BSC for item in outcome.validations)
    assert any(item["code"] == VALIDATION_CELL_ID for item in outcome.validations)
    assert any(item["code"] == VALIDATION_COMMAND for item in outcome.validations)


@pytest.mark.django_db
def test_evaluate_2g_detects_cell_id_mismatch(ep_job):
    _add_2g_cell(ep_job, cell_name="22S01ESALG0103", cell_id=99999, bcch=93)
    analysis = _analysis_2g(ep_job, ["22S01ESALG0103"])

    outcome = evaluate_poscheck(analysis, _load("full_check_2g_return.txt"))

    assert outcome.overall_status == PrecheckResultStatus.INCONSISTENT
    cell_id_items = [item for item in outcome.validations if item["code"] == VALIDATION_CELL_ID]
    assert cell_id_items
    assert cell_id_items[0]["status"] == VALIDATION_STATUS_INCONSISTENT


@pytest.mark.django_db
def test_evaluate_2g_extra_cells_stay_on_result_payload(ep_job):
    _add_2g_cell(ep_job, cell_name="22S01ESALG0101", cell_id=21097, bcch=89)
    _add_2g_cell(ep_job, cell_name="21S01ESALG0101", cell_id=21094, bcch=629)
    analysis = _analysis_2g(ep_job, ["22S01ESALG0101", "21S01ESALG0101"])

    outcome = evaluate_poscheck(analysis, _load("full_check_2g_return.txt"))

    assert outcome.overall_status == PrecheckResultStatus.INCONSISTENT
    assert outcome.validations
    missing = [
        item
        for item in outcome.validations
        if item.get("cell_name") == "21S01ESALG0101" and item["status"] != VALIDATION_STATUS_CONSISTENT
    ]
    assert missing


@pytest.mark.django_db
def test_process_full_check_2g_persists_result(ep_job):
    _add_2g_cell(ep_job, cell_name="22S01ESALG0103", cell_id=21099, bcch=93)
    analysis = _analysis_2g(ep_job, ["22S01ESALG0103"])

    result = process_poscheck(analysis, return_text=_load("full_check_2g_return.txt"))
    analysis.refresh_from_db()

    assert result.overall_status == PrecheckResultStatus.COMPLETED
    assert analysis.status == CheckAnalysisStatus.COMPLETED
    assert result.extracted["bsc"] == "BSCES36"
    assert result.extracted["bts_name"] == "BS01ESALG01"
