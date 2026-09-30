from pathlib import Path

import pytest

from ep_import.models import EpCell, ImportJob, ImportJobStatus
from poscheck.services.orchestrator import evaluate_poscheck, process_poscheck
from poscheck.services.tech.g5.mml_parser import parse_full_check_5g_return
from poscheck.services.tech.g5.validator import (
    VALIDATION_ACTIVATE_STATE,
    VALIDATION_CELL_ID,
    VALIDATION_COMMAND,
    VALIDATION_DL_NARFCN,
    VALIDATION_GNODEB_ID,
    VALIDATION_NR_DU_STATE,
    VALIDATION_PHYSICAL_CELL_ID,
    VALIDATION_STATUS_CONSISTENT,
    VALIDATION_STATUS_INCONSISTENT,
    VALIDATION_TRACKING_AREA,
    resolve_expected_5g,
)
from precheck.models import CheckAnalysis, CheckAnalysisStatus, PrecheckResultStatus

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def ep_job(db):
    return ImportJob.objects.create(
        original_filename="RNP_SRAN_CO_5g.xlsx",
        stored_file="ep_imports/test_5g.xlsx",
        status=ImportJobStatus.SUCCESS,
    )


def _add_5g_cell(
    job,
    *,
    cell_name: str,
    cell_id: int,
    pci: int,
    narfcn: int = 623334,
    band: str = "n78",
    gnb_id: int = 1060541,
    tac: int = 4151041,
    site: str = "S01PRCLG21",
):
    return EpCell.objects.create(
        job=job,
        technology="5G",
        region="SUL",
        site_name=site,
        cell_name=cell_name,
        raw={
            "gNBId": gnb_id,
            "Tracking Area ID": tac,
            "CellId": cell_id,
            "FrequencyBand": band,
            "PhysicalCellId": pci,
            "DlNarfcn": narfcn,
        },
    )


def _analysis_5g(job, cells: list[str], **kwargs):
    defaults = {
        "ep_job": job,
        "technology": "5G",
        "site_name": "S01PRCLG21",
        "selected_cells": cells,
        "pre_check": False,
        "full_check": True,
        "status": CheckAnalysisStatus.AWAITING_RETURNS,
    }
    defaults.update(kwargs)
    return CheckAnalysis.objects.create(**defaults)


def test_parse_full_check_5g_return_from_fixture():
    extraction = parse_full_check_5g_return(_load("full_check_5g_return.txt"))
    assert extraction.gnodeb_id == "1060541"
    assert extraction.tracking_area_code == "4151041"
    assert {cell.cell_name for cell in extraction.cells} >= {
        "55S01PRCLG2101",
        "55S01PRCLG2102",
        "55S01PRCLG2103",
    }
    first = next(cell for cell in extraction.cells if cell.cell_name == "55S01PRCLG2101")
    assert first.cell_id == "100"
    assert first.physical_cell_id == "516"
    assert first.downlink_narfcn == "623334"
    assert first.activate_state == "Activated"
    assert first.nr_du_cell_state == "Normal"
    assert any(item.command == "LST NRCELL" and item.ok for item in extraction.commands)
    assert any(
        item.command.startswith("DSP BRDMFRINFO") or item.command == "DSP BRDMFRINFO" for item in extraction.commands
    )
    assert any(
        item.command.startswith("CHK DATA2LIC") or item.command == "CHK DATA2LIC" for item in extraction.commands
    )


@pytest.mark.django_db
def test_validator_5g_happy_path(ep_job):
    _add_5g_cell(ep_job, cell_name="55S01PRCLG2101", cell_id=100, pci=516)
    _add_5g_cell(ep_job, cell_name="55S01PRCLG2102", cell_id=101, pci=517)
    _add_5g_cell(ep_job, cell_name="55S01PRCLG2103", cell_id=102, pci=518)
    analysis = _analysis_5g(ep_job, ["55S01PRCLG2101", "55S01PRCLG2102", "55S01PRCLG2103"])

    expected = resolve_expected_5g(analysis)
    assert expected.gnodeb_id == "1060541"
    assert expected.tracking_area_code == "4151041"

    outcome = evaluate_poscheck(analysis, _load("full_check_5g_return.txt"))
    assert outcome.overall_status == PrecheckResultStatus.COMPLETED
    assert all(item["status"] == VALIDATION_STATUS_CONSISTENT for item in outcome.validations)
    codes = {item["code"] for item in outcome.validations}
    assert VALIDATION_GNODEB_ID in codes
    assert VALIDATION_TRACKING_AREA in codes
    assert VALIDATION_CELL_ID in codes
    assert VALIDATION_PHYSICAL_CELL_ID in codes
    assert VALIDATION_DL_NARFCN in codes
    assert VALIDATION_ACTIVATE_STATE in codes
    assert VALIDATION_NR_DU_STATE in codes
    assert VALIDATION_COMMAND in codes


@pytest.mark.django_db
def test_validator_5g_detects_mismatch(ep_job):
    _add_5g_cell(ep_job, cell_name="55S01PRCLG2101", cell_id=999, pci=516)
    analysis = _analysis_5g(ep_job, ["55S01PRCLG2101"])
    outcome = evaluate_poscheck(analysis, _load("full_check_5g_return.txt"))
    assert outcome.overall_status == PrecheckResultStatus.INCONSISTENT
    cell_id_items = [item for item in outcome.validations if item["code"] == VALIDATION_CELL_ID]
    assert cell_id_items
    assert cell_id_items[0]["status"] == VALIDATION_STATUS_INCONSISTENT


@pytest.mark.django_db
def test_process_5g_persists(ep_job):
    _add_5g_cell(ep_job, cell_name="55S01PRCLG2101", cell_id=100, pci=516)
    analysis = _analysis_5g(ep_job, ["55S01PRCLG2101"])
    result = process_poscheck(analysis, return_text=_load("full_check_5g_return.txt"))
    analysis.refresh_from_db()
    assert result.overall_status == PrecheckResultStatus.COMPLETED
    assert analysis.status == CheckAnalysisStatus.COMPLETED
