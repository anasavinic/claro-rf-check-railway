import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from ep_import.models import ImportJob, ImportJobStatus
from poscheck.models import PoscheckResult
from precheck.models import CheckAnalysis, CheckAnalysisStatus, PrecheckResult, PrecheckResultStatus


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        username="rf-report-user",
        password="pass",  # pragma: allowlist secret
        email="rf@example.com",
        is_staff=True,
    )


@pytest.fixture
def auth_client(client, user):
    client.force_login(user)
    client.user = user
    return client


@pytest.fixture
def ep_job(user):
    return ImportJob.objects.create(
        original_filename="RNP_SRAN_CO_test.xlsx",
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
        "selected_cells": ["CELL_001"],
        "pre_check": True,
        "full_check": False,
        "status": CheckAnalysisStatus.COMPLETED,
    }
    defaults.update(kwargs)
    return CheckAnalysis.objects.create(**defaults)


def precheck_validations():
    return [
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
            "note": "Network Tracking Area Code differs from EP Tracking Area ID.",
        },
    ]


def make_precheck_result(analysis, **kwargs):
    defaults = {
        "analysis": analysis,
        "overall_status": PrecheckResultStatus.INCONSISTENT,
        "validations": precheck_validations(),
        "extracted": {"gnodeb_id": "1060541", "tracking_area_code": "4151040", "ne_name": "S01PRCLG21"},
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
                "code": "GNODEB_ID",
                "label": "gNodeB ID",
                "expected": "1060541",
                "found": "1060541",
                "status": "consistent",
                "note": "Matches EP gNBId.",
            }
        ],
        "extracted": {"gnodeb_id": "1060541"},
        "processed_at": timezone.now(),
    }
    defaults.update(kwargs)
    return PoscheckResult.objects.create(**defaults)
