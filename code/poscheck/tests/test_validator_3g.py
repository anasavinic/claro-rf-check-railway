from pathlib import Path

import pytest

from ep_import.models import EpCell, ImportJob, ImportJobStatus
from poscheck.services.orchestrator import evaluate_poscheck, process_poscheck
from poscheck.services.tech.g3.mml_parser import parse_full_check_3g_return
from poscheck.services.tech.g3.validator import (
    VALIDATION_CELL_ID,
    VALIDATION_COMMAND,
    VALIDATION_RNC_ID,
    VALIDATION_STATUS_CONSISTENT,
    VALIDATION_STATUS_INCONSISTENT,
    resolve_expected_3g,
)
from precheck.models import CheckAnalysis, CheckAnalysisStatus, PrecheckResultStatus

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def ep_job(db):
    return ImportJob.objects.create(
        original_filename="RNP_SRAN_CO_3g.xlsx",
        stored_file="ep_imports/test_3g.xlsx",
        status=ImportJobStatus.SUCCESS,
    )


def _add_3g_cell(job, *, cell_name: str, cell_id: int, rnc_id: int = 641, site="NS01PRCLG21"):
    return EpCell.objects.create(
        job=job,
        technology="3G",
        region="SUL",
        site_name=site,
        cell_name=cell_name,
        raw={"CELLNAME": cell_name, "CELL ID": cell_id, "RNC ID": rnc_id},
    )


def _analysis_3g(job, cells: list[str], **kwargs):
    defaults = {
        "ep_job": job,
        "technology": "3G",
        "site_name": "NS01PRCLG21",
        "selected_cells": cells,
        "pre_check": False,
        "full_check": True,
        "status": CheckAnalysisStatus.AWAITING_RETURNS,
    }
    defaults.update(kwargs)
    return CheckAnalysis.objects.create(**defaults)


def test_parse_full_check_3g_return_from_fixture():
    extraction = parse_full_check_3g_return(_load("full_check_3g_return.txt"))
    assert extraction.rnc_id == "641"
    assert len(extraction.cells) == 3


@pytest.mark.django_db
def test_validator_3g_happy_path(ep_job):
    _add_3g_cell(ep_job, cell_name="31S01PRCLG2101", cell_id=30587)
    _add_3g_cell(ep_job, cell_name="31S01PRCLG2102", cell_id=30588)
    _add_3g_cell(ep_job, cell_name="31S01PRCLG2103", cell_id=30589)
    analysis = _analysis_3g(ep_job, ["31S01PRCLG2101", "31S01PRCLG2102", "31S01PRCLG2103"])

    expected = resolve_expected_3g(analysis)
    assert expected.rnc_id == "641"

    outcome = evaluate_poscheck(analysis, _load("full_check_3g_return.txt"))
    assert outcome.overall_status == PrecheckResultStatus.COMPLETED
    assert all(item["status"] == VALIDATION_STATUS_CONSISTENT for item in outcome.validations)
    assert any(item["code"] == VALIDATION_RNC_ID for item in outcome.validations)
    assert any(item["code"] == VALIDATION_CELL_ID for item in outcome.validations)
    assert any(item["code"] == VALIDATION_COMMAND for item in outcome.validations)


@pytest.mark.django_db
def test_validator_3g_cell_id_mismatch(ep_job):
    _add_3g_cell(ep_job, cell_name="31S01PRCLG2103", cell_id=99999)
    analysis = _analysis_3g(ep_job, ["31S01PRCLG2103"])
    outcome = evaluate_poscheck(analysis, _load("full_check_3g_return.txt"))
    cell_id_items = [item for item in outcome.validations if item["code"] == VALIDATION_CELL_ID]
    assert cell_id_items
    assert cell_id_items[0]["status"] == VALIDATION_STATUS_INCONSISTENT


@pytest.mark.django_db
def test_process_3g_persists(ep_job):
    _add_3g_cell(ep_job, cell_name="31S01PRCLG2103", cell_id=30589)
    analysis = _analysis_3g(ep_job, ["31S01PRCLG2103"])
    result = process_poscheck(analysis, return_text=_load("full_check_3g_return.txt"))
    assert result.overall_status == PrecheckResultStatus.COMPLETED
