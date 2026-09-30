from pathlib import Path

import pytest

from ep_import.models import EpCell, ImportJob, ImportJobStatus
from ep_import.services.scripts import generate_full_check_4g_script
from poscheck.services.orchestrator import evaluate_poscheck, get_poscheck_snapshot, process_poscheck
from poscheck.services.tech.g4.mml_parser import parse_full_check_4g_return
from poscheck.services.tech.g4.validator import (
    VALIDATION_CELL_ID,
    VALIDATION_COMMAND,
    VALIDATION_ENODEB_ID,
    VALIDATION_STATUS_CONSISTENT,
    VALIDATION_STATUS_INCONSISTENT,
    VALIDATION_TRACKING_AREA,
    resolve_expected_4g,
)
from precheck.models import CheckAnalysis, CheckAnalysisStatus, PrecheckResultStatus

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def ep_job(db):
    return ImportJob.objects.create(
        original_filename="RNP_SRAN_CO_4g.xlsx",
        stored_file="ep_imports/test_4g.xlsx",
        status=ImportJobStatus.SUCCESS,
    )


def _add_4g_cell(
    job,
    *,
    cell_name: str,
    cell_id: int,
    pci: int,
    enodeb_id: int = 410545,
    tac: int = 41041,
    site="S01PRCLG21",
):
    return EpCell.objects.create(
        job=job,
        technology="4G",
        region="SUL",
        site_name=site,
        cell_name=cell_name,
        raw={
            "CELL NAME": cell_name,
            "CELL ID": cell_id,
            "ENODEB ID": enodeb_id,
            "TAC": tac,
            "PCI": pci,
        },
    )


def _analysis_4g(job, cells: list[str], **kwargs):
    defaults = {
        "ep_job": job,
        "technology": "4G",
        "site_name": "S01PRCLG21",
        "selected_cells": cells,
        "pre_check": False,
        "full_check": True,
        "status": CheckAnalysisStatus.AWAITING_RETURNS,
    }
    defaults.update(kwargs)
    return CheckAnalysis.objects.create(**defaults)


def test_generate_full_check_4g_script_embeds_enodeb():
    script = generate_full_check_4g_script(enodeb_id="410545")
    assert script.startswith("LST CELL:;\n")
    assert "LST ENODEBFUNCTION:;" in script
    assert "LST EUTRANINTRAFREQNCELL:ENODEBID=410545;" in script
    assert "LST EUTRANINTERFREQNCELL:ENODEBID=410545;" in script


def test_parse_full_check_4g_return_from_fixture():
    extraction = parse_full_check_4g_return(_load("full_check_4g_return.txt"))

    assert extraction.ne_name == "S01PRCLG21"
    assert extraction.enodeb_id == "410545"
    assert extraction.tac == "41041"
    assert {cell.cell_name for cell in extraction.cells} == {
        "43S01PRCLG2101",
        "43S01PRCLG2102",
        "43S01PRCLG2103",
    }
    assert any(item.command == "LST CELL" and item.ok for item in extraction.commands)
    assert any(item.command == "LST ENODEBFUNCTION" and item.ok for item in extraction.commands)


@pytest.mark.django_db
def test_validator_4g_happy_path(ep_job):
    _add_4g_cell(ep_job, cell_name="43S01PRCLG2101", cell_id=8, pci=21)
    _add_4g_cell(ep_job, cell_name="43S01PRCLG2102", cell_id=9, pci=22)
    _add_4g_cell(ep_job, cell_name="43S01PRCLG2103", cell_id=10, pci=23)
    analysis = _analysis_4g(
        ep_job,
        ["43S01PRCLG2101", "43S01PRCLG2102", "43S01PRCLG2103"],
    )

    expected = resolve_expected_4g(analysis)
    assert expected.enodeb_id == "410545"
    assert expected.tac == "41041"
    assert len(expected.cells) == 3

    outcome = evaluate_poscheck(analysis, _load("full_check_4g_return.txt"))
    assert outcome.overall_status == PrecheckResultStatus.COMPLETED
    assert all(item["status"] == VALIDATION_STATUS_CONSISTENT for item in outcome.validations)
    assert any(item["code"] == VALIDATION_ENODEB_ID for item in outcome.validations)
    assert any(item["code"] == VALIDATION_TRACKING_AREA for item in outcome.validations)
    assert any(item["code"] == VALIDATION_CELL_ID for item in outcome.validations)
    assert any(item["code"] == VALIDATION_COMMAND for item in outcome.validations)


@pytest.mark.django_db
def test_validator_4g_enodeb_mismatch(ep_job):
    _add_4g_cell(ep_job, cell_name="43S01PRCLG2101", cell_id=8, pci=21, enodeb_id=999)
    analysis = _analysis_4g(ep_job, ["43S01PRCLG2101"])

    outcome = evaluate_poscheck(analysis, _load("full_check_4g_return.txt"))

    assert outcome.overall_status == PrecheckResultStatus.INCONSISTENT
    enodeb_items = [item for item in outcome.validations if item["code"] == VALIDATION_ENODEB_ID]
    assert enodeb_items
    assert enodeb_items[0]["status"] == VALIDATION_STATUS_INCONSISTENT
    assert enodeb_items[0]["expected"] == "999"
    assert enodeb_items[0]["found"] == "410545"


@pytest.mark.django_db
def test_validator_4g_cell_id_mismatch(ep_job):
    _add_4g_cell(ep_job, cell_name="43S01PRCLG2103", cell_id=99999, pci=23)
    analysis = _analysis_4g(ep_job, ["43S01PRCLG2103"])

    outcome = evaluate_poscheck(analysis, _load("full_check_4g_return.txt"))

    assert outcome.overall_status in {
        PrecheckResultStatus.INCONSISTENT,
        PrecheckResultStatus.EXECUTION_FAILURE,
    }
    cell_id_items = [item for item in outcome.validations if item["code"] == VALIDATION_CELL_ID]
    assert cell_id_items
    assert cell_id_items[0]["status"] == VALIDATION_STATUS_INCONSISTENT


@pytest.mark.django_db
def test_process_4g_persists(ep_job):
    _add_4g_cell(ep_job, cell_name="43S01PRCLG2103", cell_id=10, pci=23)
    analysis = _analysis_4g(ep_job, ["43S01PRCLG2103"])

    result = process_poscheck(analysis, return_text=_load("full_check_4g_return.txt"))
    analysis.refresh_from_db()

    assert result.overall_status == PrecheckResultStatus.COMPLETED
    assert analysis.status == CheckAnalysisStatus.COMPLETED
    assert result.extracted["enodeb_id"] == "410545"
    assert result.extracted["tac"] == "41041"
    snapshot = get_poscheck_snapshot(analysis.id)
    assert snapshot is not None
    assert snapshot["enodeb_id"] == "410545"
    assert snapshot["tac"] == "41041"
    assert snapshot["blocks_next_step"] is False
