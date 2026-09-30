import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import IntegrityError

from ep_import.models import ImportJob, ImportJobStatus
from precheck.models import (
    CheckAnalysis,
    CheckAnalysisStatus,
    CheckReturnFile,
    CheckType,
    PrecheckResult,
    PrecheckResultStatus,
)


@pytest.fixture
def ep_job(db):
    return ImportJob.objects.create(
        original_filename="RNP_SRAN_CO_test.xlsx",
        stored_file="ep_imports/test.xlsx",
        status=ImportJobStatus.SUCCESS,
    )


@pytest.mark.django_db
def test_check_analysis_links_ep_job(ep_job):
    user = get_user_model().objects.create_user(username="precheck-user", password="pass")
    analysis = CheckAnalysis.objects.create(
        created_by=user,
        ep_job=ep_job,
        technology="5G",
        site_name="S01PRCLG21",
        selected_cells=["55S01PRCLG2101"],
        pre_check=True,
        full_check=False,
        status=CheckAnalysisStatus.AWAITING_RETURNS,
    )

    assert analysis.ep_job_id == ep_job.id
    assert analysis.pre_check is True
    assert analysis.selected_cells == ["55S01PRCLG2101"]


@pytest.mark.django_db
def test_return_file_unique_per_check_type(ep_job):
    analysis = CheckAnalysis.objects.create(
        ep_job=ep_job,
        site_name="S01PRCLG21",
        selected_cells=["CELL_A"],
        pre_check=True,
        status=CheckAnalysisStatus.AWAITING_RETURNS,
    )
    CheckReturnFile.objects.create(
        analysis=analysis,
        check_type=CheckType.PRECHECK,
        original_filename="precheck.txt",
        stored_file=ContentFile(b"dummy", name="precheck.txt"),
        content_sha256="abc",
    )

    with pytest.raises(IntegrityError):
        CheckReturnFile.objects.create(
            analysis=analysis,
            check_type=CheckType.PRECHECK,
            original_filename="precheck-again.txt",
            stored_file=ContentFile(b"other", name="precheck-again.txt"),
            content_sha256="def",
        )


@pytest.mark.django_db
def test_precheck_result_stores_extraction(ep_job):
    analysis = CheckAnalysis.objects.create(
        ep_job=ep_job,
        site_name="S01PRCLG21",
        selected_cells=["CELL_A"],
        pre_check=True,
        status=CheckAnalysisStatus.COMPLETED,
    )
    result = PrecheckResult.objects.create(
        analysis=analysis,
        overall_status=PrecheckResultStatus.COMPLETED,
        validations=[
            {
                "code": "GNODEB_ID",
                "expected": "1060541",
                "found": "1060541",
                "status": "consistent",
                "note": "Matches EP gNBId.",
            }
        ],
        extracted={"gnodeb_id": "1060541", "tracking_area_code": "4151041", "ne_name": "S01PRCLG21"},
    )

    assert analysis.precheck_result.overall_status == PrecheckResultStatus.COMPLETED
    assert result.extracted["gnodeb_id"] == "1060541"
