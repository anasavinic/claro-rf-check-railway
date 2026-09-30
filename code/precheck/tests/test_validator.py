from pathlib import Path

import pytest
from django.core.files.base import ContentFile

from ep_import.models import EpCell, ImportJob, ImportJobStatus
from precheck.models import (
    CheckAnalysis,
    CheckAnalysisStatus,
    CheckReturnFile,
    CheckType,
    PrecheckResultStatus,
)
from precheck.services.errors import PrecheckError
from precheck.services.mml_parser import parse_precheck_return
from precheck.services.validator import (
    VALIDATION_GNODEB_ID,
    VALIDATION_STATUS_CONSISTENT,
    VALIDATION_STATUS_INCONSISTENT,
    VALIDATION_TRACKING_AREA,
    compare_precheck,
    evaluate_precheck,
    get_precheck_snapshot,
    normalize_comparable,
    process_precheck,
    resolve_expected_from_ep,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def ep_job(db):
    return ImportJob.objects.create(
        original_filename="RNP_SRAN_CO_test.xlsx",
        stored_file="ep_imports/test.xlsx",
        status=ImportJobStatus.SUCCESS,
    )


def _add_cell(job, *, cell_name: str, gnb_id=1060541, tac=4151041, site="S01PRCLG21"):
    return EpCell.objects.create(
        job=job,
        technology="5G",
        region="CO",
        site_name=site,
        cell_name=cell_name,
        raw={"gNBId": gnb_id, "Tracking Area ID": tac},
    )


def _analysis(job, cells: list[str], **kwargs):
    defaults = {
        "ep_job": job,
        "technology": "5G",
        "site_name": "S01PRCLG21",
        "selected_cells": cells,
        "pre_check": True,
        "full_check": False,
        "status": CheckAnalysisStatus.AWAITING_RETURNS,
    }
    defaults.update(kwargs)
    return CheckAnalysis.objects.create(**defaults)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1060541, "1060541"),
        ("1060541", "1060541"),
        ("1060541.0", "1060541"),
        (1060541.0, "1060541"),
        (" 4151041 ", "4151041"),
        (None, ""),
        ("NULL", ""),
    ],
)
def test_normalize_comparable(value, expected):
    assert normalize_comparable(value) == expected


@pytest.mark.django_db
def test_resolve_expected_from_ep(ep_job):
    _add_cell(ep_job, cell_name="CELL_A")
    _add_cell(ep_job, cell_name="CELL_B")
    analysis = _analysis(ep_job, ["CELL_A", "CELL_B"])

    expected = resolve_expected_from_ep(analysis)

    assert expected.gnodeb_id == "1060541"
    assert expected.tracking_area_code == "4151041"


@pytest.mark.django_db
def test_resolve_expected_rejects_inconsistent_ep(ep_job):
    _add_cell(ep_job, cell_name="CELL_A", gnb_id=1060541)
    _add_cell(ep_job, cell_name="CELL_B", gnb_id=999)
    analysis = _analysis(ep_job, ["CELL_A", "CELL_B"])

    with pytest.raises(PrecheckError) as exc:
        resolve_expected_from_ep(analysis)

    assert exc.value.issues[0].code == "EP_FIELD_INCONSISTENT"


@pytest.mark.django_db
def test_resolve_expected_rejects_missing_ep_field(ep_job):
    EpCell.objects.create(
        job=ep_job,
        technology="5G",
        site_name="S01PRCLG21",
        cell_name="CELL_A",
        raw={"Tracking Area ID": 4151041},
    )
    analysis = _analysis(ep_job, ["CELL_A"])

    with pytest.raises(PrecheckError) as exc:
        resolve_expected_from_ep(analysis)

    assert exc.value.issues[0].code == "EP_FIELD_MISSING"


@pytest.mark.django_db
def test_compare_precheck_completed(ep_job):
    _add_cell(ep_job, cell_name="CELL_A")
    analysis = _analysis(ep_job, ["CELL_A"])
    extraction = parse_precheck_return(_load("precheck_only_5g_return.txt"))

    outcome = compare_precheck(resolve_expected_from_ep(analysis), extraction)

    assert outcome.overall_status == PrecheckResultStatus.COMPLETED
    assert outcome.blocks_next_step is False
    assert {item["code"]: item["status"] for item in outcome.validations} == {
        VALIDATION_GNODEB_ID: VALIDATION_STATUS_CONSISTENT,
        VALIDATION_TRACKING_AREA: VALIDATION_STATUS_CONSISTENT,
    }


@pytest.mark.django_db
def test_compare_precheck_inconsistent(ep_job):
    _add_cell(ep_job, cell_name="CELL_A", gnb_id=111, tac=222)
    analysis = _analysis(ep_job, ["CELL_A"])
    extraction = parse_precheck_return(_load("full_check_5g_return.txt"))

    outcome = compare_precheck(resolve_expected_from_ep(analysis), extraction)

    assert outcome.overall_status == PrecheckResultStatus.INCONSISTENT
    assert outcome.blocks_next_step is True
    by_code = {item["code"]: item for item in outcome.validations}
    assert by_code[VALIDATION_GNODEB_ID]["status"] == VALIDATION_STATUS_INCONSISTENT
    assert by_code[VALIDATION_GNODEB_ID]["expected"] == "111"
    assert by_code[VALIDATION_GNODEB_ID]["found"] == "1060541"
    assert by_code[VALIDATION_TRACKING_AREA]["status"] == VALIDATION_STATUS_INCONSISTENT


@pytest.mark.django_db
def test_process_precheck_persists_completed_result(ep_job):
    _add_cell(ep_job, cell_name="CELL_A")
    analysis = _analysis(ep_job, ["CELL_A"])

    result = process_precheck(analysis, return_text=_load("full_check_5g_return.txt"))
    analysis.refresh_from_db()

    assert result.overall_status == PrecheckResultStatus.COMPLETED
    assert analysis.status == CheckAnalysisStatus.COMPLETED
    assert result.extracted["gnodeb_id"] == "1060541"
    assert result.extracted["tracking_area_code"] == "4151041"
    assert len(result.validations) == 2


@pytest.mark.django_db
def test_process_precheck_from_stored_return_file(ep_job):
    _add_cell(ep_job, cell_name="CELL_A")
    analysis = _analysis(ep_job, ["CELL_A"])
    payload = _load("precheck_only_5g_return.txt").encode("utf-8")
    CheckReturnFile.objects.create(
        analysis=analysis,
        check_type=CheckType.PRECHECK,
        original_filename="precheck.txt",
        stored_file=ContentFile(payload, name="precheck.txt"),
        content_sha256="sha",
    )

    result = process_precheck(analysis)

    assert result.overall_status == PrecheckResultStatus.COMPLETED
    snapshot = get_precheck_snapshot(analysis.id)
    assert snapshot is not None
    assert snapshot["status"] == PrecheckResultStatus.COMPLETED
    assert snapshot["gnodeb_id"] == "1060541"
    assert snapshot["tracking_area_code"] == "4151041"
    assert snapshot["blocks_next_step"] is False
    assert snapshot["counts"]["consistent"] == 2


@pytest.mark.django_db
def test_process_precheck_execution_failure_on_parse_error(ep_job):
    _add_cell(ep_job, cell_name="CELL_A")
    analysis = _analysis(ep_job, ["CELL_A"])

    result = process_precheck(analysis, return_text="not a gerencia return")
    analysis.refresh_from_db()

    assert result.overall_status == PrecheckResultStatus.EXECUTION_FAILURE
    assert analysis.status == CheckAnalysisStatus.FAILED
    assert result.error_code
    assert result.error_title == "Execution failure"
    snapshot = get_precheck_snapshot(analysis.id)
    assert snapshot["blocks_next_step"] is True
    assert snapshot["counts"]["total"] == 0


@pytest.mark.django_db
def test_process_precheck_execution_failure_when_return_missing(ep_job):
    _add_cell(ep_job, cell_name="CELL_A")
    analysis = _analysis(ep_job, ["CELL_A"])

    result = process_precheck(analysis)

    assert result.overall_status == PrecheckResultStatus.EXECUTION_FAILURE
    assert result.error_code == "MISSING_RETURN_FILE"


@pytest.mark.django_db
def test_process_precheck_rejects_non_5g(ep_job):
    _add_cell(ep_job, cell_name="CELL_A")
    analysis = _analysis(ep_job, ["CELL_A"], technology="4G")

    result = process_precheck(analysis, return_text=_load("precheck_only_5g_return.txt"))

    assert result.overall_status == PrecheckResultStatus.EXECUTION_FAILURE
    assert result.error_code == "TECHNOLOGY_NOT_SUPPORTED"


@pytest.mark.django_db
def test_evaluate_precheck_matches_process(ep_job):
    _add_cell(ep_job, cell_name="CELL_A")
    analysis = _analysis(ep_job, ["CELL_A"])
    text = _load("precheck_only_5g_return.txt")

    outcome = evaluate_precheck(analysis, text)
    result = process_precheck(analysis, return_text=text)

    assert outcome.overall_status == result.overall_status
    assert outcome.validations == result.validations


@pytest.mark.django_db
def test_get_precheck_snapshot_absent():
    assert get_precheck_snapshot("00000000-0000-0000-0000-000000000001") is None
