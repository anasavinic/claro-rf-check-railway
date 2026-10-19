import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from ep_import.models import ImportJob, ImportJobStatus
from poscheck.models import PoscheckResult
from precheck.models import (
    CheckAnalysis,
    CheckAnalysisStatus,
    CombinedCheck,
    PrecheckResult,
    PrecheckResultStatus,
)


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        username="results-user",
        password="pass",  # pragma: allowlist secret
        is_staff=True,
    )


@pytest.fixture
def ep_job(user):
    return ImportJob.objects.create(
        original_filename="RNP_SRAN_ES_test.xlsx",
        stored_file="ep_imports/test.xlsx",
        status=ImportJobStatus.SUCCESS,
        created_by=user,
    )


def make_analysis(ep_job, user, **kwargs):
    defaults = {
        "created_by": user,
        "ep_job": ep_job,
        "technology": "5G",
        "site_name": "S01PRCLG21",
        "selected_cells": ["55S01PRCLG2101"],
        "pre_check": True,
        "full_check": False,
        "status": CheckAnalysisStatus.INCONSISTENT,
    }
    defaults.update(kwargs)
    return CheckAnalysis.objects.create(**defaults)


def make_precheck_result(analysis, **kwargs):
    defaults = {
        "analysis": analysis,
        "overall_status": PrecheckResultStatus.INCONSISTENT,
        "validations": [
            {
                "code": "GNODEB_ID",
                "label": "gNodeB ID",
                "expected": "1060541",
                "found": "1060541",
                "status": "consistent",
                "note": "Matches EP gNBId.",
            },
            {
                "code": "TRACKING_AREA_CODE",
                "label": "Tracking Area Code",
                "expected": "4151041",
                "found": "4151040",
                "status": "inconsistent",
                "note": "Differs from EP.",
            },
        ],
        "extracted": {
            "gnodeb_id": "1060541",
            "tracking_area_code": "4151040",
            "ne_name": "S01PRCLG21",
        },
        "processed_at": timezone.now(),
    }
    defaults.update(kwargs)
    return PrecheckResult.objects.create(**defaults)


def make_poscheck_result(analysis, **kwargs):
    defaults = {
        "analysis": analysis,
        "overall_status": PrecheckResultStatus.COMPLETED,
        "validations": [
            {
                "code": "ENODEB_ID",
                "label": "eNodeB ID",
                "expected": "410545",
                "found": "410545",
                "status": "consistent",
                "note": "Matches EP.",
            },
            {
                "code": "CELL_NAME",
                "label": "Cell Name",
                "expected": "43S01PRCLG2101",
                "found": "",
                "status": "failed",
                "note": "Cell was not found.",
            },
        ],
        "extracted": {"enodeb_id": "410545", "ne_name": "S01PRCLG21"},
        "processed_at": timezone.now(),
    }
    defaults.update(kwargs)
    return PoscheckResult.objects.create(**defaults)


def make_combined(ep_job, user, **kwargs):
    defaults = {
        "created_by": user,
        "ep_job": ep_job,
        "technologies": ["4G", "5G"],
        "site_names": ["ES01PRCLG21", "S01PRCLG21"],
        "pre_check": True,
        "full_check": True,
        "status": CheckAnalysisStatus.INCONSISTENT,
    }
    defaults.update(kwargs)
    return CombinedCheck.objects.create(**defaults)
