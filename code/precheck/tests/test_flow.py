import json
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from ep_import.models import EpCell, ImportJob, ImportJobStatus
from precheck.models import (
    CheckAnalysis,
    CheckAnalysisStatus,
    CheckReturnFile,
    CheckType,
    PrecheckResult,
    PrecheckResultStatus,
)
from precheck.services.analysis import SESSION_ANALYSIS_KEY

FIXTURES = Path(__file__).parent / "fixtures"


def _ready_job_with_cell(user=None, **raw):
    job = ImportJob.objects.create(
        original_filename="RNP_SRAN_CO_test.xlsx",
        stored_file="ep_imports/test.xlsx",
        status=ImportJobStatus.SUCCESS,
        created_by=user,
    )
    defaults = {"gNBId": 1060541, "Tracking Area ID": 4151041}
    defaults.update(raw)
    EpCell.objects.create(
        job=job,
        technology="5G",
        region="CO",
        site_name="S01PRCLG21",
        cell_name="CELL_001",
        raw=defaults,
    )
    return job


def _start_precheck(auth_client, job):
    if job.created_by_id is None:
        job.created_by = auth_client.user
        job.save(update_fields=["created_by"])
    response = auth_client.post(
        reverse("ep_import:generate_scripts"),
        data=json.dumps(
            {
                "job_id": str(job.id),
                "technology": "5G",
                "site": "S01PRCLG21",
                "cells": ["CELL_001"],
                "pre_check": True,
                "full_check": False,
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 200
    analysis_id = response.json()["analysis_id"]
    assert auth_client.session[SESSION_ANALYSIS_KEY] == analysis_id
    return CheckAnalysis.objects.get(pk=analysis_id)


@pytest.mark.django_db
def test_generate_scripts_persists_check_analysis(auth_client):
    job = _ready_job_with_cell()
    analysis = _start_precheck(auth_client, job)

    assert analysis.pre_check is True
    assert analysis.site_name == "S01PRCLG21"
    assert analysis.selected_cells == ["CELL_001"]
    assert analysis.status == CheckAnalysisStatus.AWAITING_RETURNS

    scripts = auth_client.get(reverse("ep_import:scripts", kwargs={"technology": "5G"}))
    assert scripts.status_code == 200
    assert b"Process analysis" in scripts.content


@pytest.mark.django_db
def test_import_returns_requires_active_analysis(auth_client):
    response = auth_client.get(reverse("precheck:import_returns", kwargs={"technology": "5G"}))
    assert response.status_code == 302
    assert response.url == reverse("ep_import:site_cells", kwargs={"technology": "5G"})


@pytest.mark.django_db
def test_upload_and_process_precheck_happy_path(auth_client):
    job = _ready_job_with_cell()
    analysis = _start_precheck(auth_client, job)
    payload = (FIXTURES / "full_check_5g_return.txt").read_bytes()

    returns_page = auth_client.get(reverse("precheck:import_returns", kwargs={"technology": "5G"}))
    assert returns_page.status_code == 200
    assert b"Import results" in returns_page.content
    assert b"Pre-check result" in returns_page.content
    assert b"Process analysis" in returns_page.content
    assert b"Drag or click to upload" in returns_page.content

    upload = auth_client.post(
        reverse("precheck:upload_precheck_return", kwargs={"technology": "5G"}),
        {"file": SimpleUploadedFile("precheck.txt", payload, content_type="text/plain")},
        HTTP_ACCEPT="application/json",
    )
    assert upload.status_code == 200
    assert upload.json()["type"] == "Success"
    assert CheckReturnFile.objects.filter(analysis=analysis, check_type=CheckType.PRECHECK).exists()

    process = auth_client.post(reverse("precheck:process", kwargs={"technology": "5G"}), HTTP_ACCEPT="application/json")
    assert process.status_code == 200
    body = process.json()
    assert body["redirect_url"] == reverse("precheck:result", kwargs={"technology": "5G"})
    assert body["status"] == PrecheckResultStatus.COMPLETED

    analysis.refresh_from_db()
    assert analysis.status == CheckAnalysisStatus.COMPLETED

    result_page = auth_client.get(reverse("precheck:result", kwargs={"technology": "5G"}))
    assert result_page.status_code == 200
    assert b"Analysis results" in result_page.content
    assert b"Completed" in result_page.content
    assert b"1060541" in result_page.content
    assert b"4151041" in result_page.content
    assert b"precheck-validations-data" in result_page.content
    assert b"Replace MML return" in result_page.content
    assert f'href="{reverse("reports:export", kwargs={"analysis_id": analysis.id})}"'.encode() in result_page.content
    assert b"Coming soon" not in result_page.content


@pytest.mark.django_db
def test_replace_return_resets_and_allows_reprocess(auth_client):
    job = _ready_job_with_cell()
    analysis = _start_precheck(auth_client, job)
    payload = (FIXTURES / "full_check_5g_return.txt").read_bytes()

    auth_client.post(
        reverse("precheck:upload_precheck_return", kwargs={"technology": "5G"}),
        {"file": SimpleUploadedFile("precheck.txt", payload, content_type="text/plain")},
        HTTP_ACCEPT="application/json",
    )
    assert (
        auth_client.post(
            reverse("precheck:process", kwargs={"technology": "5G"}), HTTP_ACCEPT="application/json"
        ).status_code
        == 200
    )
    analysis.refresh_from_db()
    assert analysis.status == CheckAnalysisStatus.COMPLETED
    assert PrecheckResult.objects.filter(analysis=analysis).exists()

    replace = auth_client.post(
        reverse("precheck:upload_precheck_return", kwargs={"technology": "5G"}),
        {
            "file": SimpleUploadedFile(
                "precheck-v2.txt",
                payload + b"\n# corrected\n",
                content_type="text/plain",
            )
        },
        HTTP_ACCEPT="application/json",
    )
    assert replace.status_code == 200
    analysis.refresh_from_db()
    assert analysis.status == CheckAnalysisStatus.AWAITING_RETURNS
    assert not PrecheckResult.objects.filter(analysis=analysis).exists()

    process = auth_client.post(reverse("precheck:process", kwargs={"technology": "5G"}), HTTP_ACCEPT="application/json")
    assert process.status_code == 200
    assert process.json()["redirect_url"] == reverse("precheck:result", kwargs={"technology": "5G"})
    analysis.refresh_from_db()
    assert analysis.status == CheckAnalysisStatus.COMPLETED


@pytest.mark.django_db
def test_process_while_busy_returns_conflict(auth_client):
    job = _ready_job_with_cell()
    analysis = _start_precheck(auth_client, job)
    payload = (FIXTURES / "full_check_5g_return.txt").read_bytes()
    auth_client.post(
        reverse("precheck:upload_precheck_return", kwargs={"technology": "5G"}),
        {"file": SimpleUploadedFile("precheck.txt", payload, content_type="text/plain")},
        HTTP_ACCEPT="application/json",
    )
    analysis.status = CheckAnalysisStatus.PROCESSING
    analysis.save(update_fields=["status", "updated_at"])

    response = auth_client.post(
        reverse("precheck:process", kwargs={"technology": "5G"}), HTTP_ACCEPT="application/json"
    )
    assert response.status_code == 409
    assert "already" in response.json()["message"].lower()

    upload = auth_client.post(
        reverse("precheck:upload_precheck_return", kwargs={"technology": "5G"}),
        {"file": SimpleUploadedFile("precheck2.txt", payload, content_type="text/plain")},
        HTTP_ACCEPT="application/json",
    )
    assert upload.status_code == 409


@pytest.mark.django_db
def test_staff_cannot_mutate_another_users_analysis(auth_client):
    from django.contrib.auth import get_user_model
    from django.test import Client

    owner = get_user_model().objects.create_user(username="analysis-owner", password="pass")
    job = _ready_job_with_cell(user=owner)

    owner_client = Client()
    owner_client.force_login(owner)
    owner_client.user = owner
    analysis = _start_precheck(owner_client, job)

    # Staff (auth_client) can view via session but must not mutate
    session = auth_client.session
    session[SESSION_ANALYSIS_KEY] = str(analysis.id)
    session.save()

    returns_page = auth_client.get(reverse("precheck:import_returns", kwargs={"technology": "5G"}))
    assert returns_page.status_code == 200

    payload = (FIXTURES / "full_check_5g_return.txt").read_bytes()
    upload = auth_client.post(
        reverse("precheck:upload_precheck_return", kwargs={"technology": "5G"}),
        {"file": SimpleUploadedFile("precheck.txt", payload, content_type="text/plain")},
        HTTP_ACCEPT="application/json",
    )
    assert upload.status_code == 403

    process = auth_client.post(reverse("precheck:process", kwargs={"technology": "5G"}), HTTP_ACCEPT="application/json")
    assert process.status_code == 403


@pytest.mark.django_db
def test_process_without_upload_is_rejected(auth_client):
    job = _ready_job_with_cell()
    _start_precheck(auth_client, job)

    response = auth_client.post(
        reverse("precheck:process", kwargs={"technology": "5G"}), HTTP_ACCEPT="application/json"
    )
    assert response.status_code == 400
    assert response.json()["type"] == "Error"


@pytest.mark.django_db
def test_process_failure_redirects_to_failure_page(auth_client):
    job = _ready_job_with_cell()
    analysis = _start_precheck(auth_client, job)

    auth_client.post(
        reverse("precheck:upload_precheck_return", kwargs={"technology": "5G"}),
        {"file": SimpleUploadedFile("bad.txt", b"not a gerencia return", content_type="text/plain")},
        HTTP_ACCEPT="application/json",
    )
    process = auth_client.post(reverse("precheck:process", kwargs={"technology": "5G"}), HTTP_ACCEPT="application/json")
    assert process.status_code == 200
    assert process.json()["redirect_url"] == reverse("precheck:failure", kwargs={"technology": "5G"})

    analysis.refresh_from_db()
    assert analysis.status == CheckAnalysisStatus.FAILED

    failure_page = auth_client.get(reverse("precheck:failure", kwargs={"technology": "5G"}))
    assert failure_page.status_code == 200
    assert b"Unable to complete the RF Check" in failure_page.content
    assert b"Execution details" in failure_page.content
    assert b"View technical details" in failure_page.content
    assert b"Run again" in failure_page.content


@pytest.mark.django_db
def test_other_user_cannot_access_analysis(auth_client, client):
    from django.contrib.auth import get_user_model

    job = _ready_job_with_cell()
    job.created_by = auth_client.user
    job.save(update_fields=["created_by"])
    analysis = _start_precheck(auth_client, job)

    other = get_user_model().objects.create_user(username="other-user", password="pass")
    client.force_login(other)
    session = client.session
    session[SESSION_ANALYSIS_KEY] = str(analysis.id)
    session.save()

    response = client.get(reverse("precheck:import_returns", kwargs={"technology": "5G"}))
    assert response.status_code == 302
    assert response.url == reverse("ep_import:site_cells", kwargs={"technology": "5G"})


@pytest.mark.django_db
def test_upload_rejects_non_text_extension(auth_client):
    job = _ready_job_with_cell()
    _start_precheck(auth_client, job)

    response = auth_client.post(
        reverse("precheck:upload_precheck_return", kwargs={"technology": "5G"}),
        {"file": SimpleUploadedFile("return.xlsx", b"PK\x03\x04", content_type="application/vnd.ms-excel")},
        HTTP_ACCEPT="application/json",
    )
    assert response.status_code == 400
    assert "Accepted formats" in response.json()["message"]
