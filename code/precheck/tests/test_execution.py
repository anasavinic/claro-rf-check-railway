"""Async CheckExecution enqueue / claim / idempotency tests."""

from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from ep_import.models import EpCell, ImportJob, ImportJobStatus
from precheck.models import (
    CheckAnalysis,
    CheckAnalysisStatus,
    CheckExecution,
    CheckExecutionStatus,
    PrecheckResult,
)
from precheck.services.analysis import SESSION_ANALYSIS_KEY
from precheck.services.execution import enqueue_check_execution, run_check_execution
from precheck.services.returns import store_precheck_return

FIXTURES = Path(__file__).parent / "fixtures"


def _ready_job(user):
    job = ImportJob.objects.create(
        original_filename="RNP_SRAN_CO_test.xlsx",
        stored_file="ep_imports/test.xlsx",
        status=ImportJobStatus.SUCCESS,
        created_by=user,
    )
    EpCell.objects.create(
        job=job,
        technology="5G",
        region="CO",
        site_name="S01PRCLG21",
        cell_name="CELL_001",
        raw={"gNBId": 1060541, "Tracking Area ID": 4151041},
    )
    return job


def _analysis_with_return(user):
    job = _ready_job(user)
    analysis = CheckAnalysis.objects.create(
        created_by=user,
        ep_job=job,
        technology="5G",
        site_name="S01PRCLG21",
        selected_cells=["CELL_001"],
        pre_check=True,
        full_check=False,
        status=CheckAnalysisStatus.AWAITING_RETURNS,
    )
    payload = (FIXTURES / "full_check_5g_return.txt").read_bytes()
    store_precheck_return(analysis, SimpleUploadedFile("precheck.txt", payload, content_type="text/plain"))
    analysis.refresh_from_db()
    return analysis


@pytest.mark.django_db
def test_enqueue_and_run_creates_execution_history(user):
    analysis = _analysis_with_return(user)
    execution, created = enqueue_check_execution(analysis, user=user)
    assert created is True
    assert execution.status == CheckExecutionStatus.PENDING
    analysis.refresh_from_db()
    assert analysis.status == CheckAnalysisStatus.PROCESSING

    run_check_execution(execution, task_id="task-1")
    execution.refresh_from_db()
    analysis.refresh_from_db()

    assert execution.status == CheckExecutionStatus.SUCCESS
    assert execution.task_id == "task-1"
    assert execution.finished_at is not None
    assert analysis.status == CheckAnalysisStatus.COMPLETED
    result = PrecheckResult.objects.get(analysis=analysis)
    assert result.execution_id == execution.id


@pytest.mark.django_db
def test_same_inputs_are_idempotent_when_result_exists(user):
    analysis = _analysis_with_return(user)
    first, _ = enqueue_check_execution(analysis, user=user)
    run_check_execution(first, task_id="task-1")

    second, created = enqueue_check_execution(analysis, user=user)
    assert created is False
    assert second.id == first.id
    assert CheckExecution.objects.filter(analysis=analysis).count() == 1


@pytest.mark.django_db
def test_process_endpoint_eager_returns_redirect(auth_client, user):
    analysis = _analysis_with_return(user)
    session = auth_client.session
    session[SESSION_ANALYSIS_KEY] = str(analysis.id)
    session.save()

    response = auth_client.post(
        reverse("precheck:process", kwargs={"technology": "5G"}), HTTP_ACCEPT="application/json"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["redirect_url"] == reverse("precheck:result", kwargs={"technology": "5G"})
    assert "execution" in body
    assert body["execution"]["status"] == CheckExecutionStatus.SUCCESS
    assert CheckExecution.objects.filter(analysis=analysis).exists()


@pytest.mark.django_db
def test_reupload_clears_result_and_allows_new_execution(user):
    analysis = _analysis_with_return(user)
    first, _ = enqueue_check_execution(analysis, user=user)
    run_check_execution(first, task_id="task-1")
    assert PrecheckResult.objects.filter(analysis=analysis).exists()

    payload = (FIXTURES / "full_check_5g_return.txt").read_bytes() + b"\n# v2\n"
    store_precheck_return(
        analysis,
        SimpleUploadedFile("precheck-v2.txt", payload, content_type="text/plain"),
    )
    analysis.refresh_from_db()
    assert analysis.status == CheckAnalysisStatus.AWAITING_RETURNS
    assert not PrecheckResult.objects.filter(analysis=analysis).exists()

    second, created = enqueue_check_execution(analysis, user=user)
    assert created is True
    assert second.id != first.id
