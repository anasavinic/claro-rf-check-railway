import json
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from ep_import.models import EpCell, ImportJob, ImportJobStatus
from precheck.models import CheckAnalysis, CheckAnalysisStatus
from precheck.services.analysis import SESSION_ANALYSIS_KEY

FIXTURES = Path(__file__).parent / "fixtures"


def _ready_3g_job(user=None):
    job = ImportJob.objects.create(
        original_filename="RNP_SRAN_CO_3g.xlsx",
        stored_file="ep_imports/test_3g.xlsx",
        status=ImportJobStatus.SUCCESS,
        created_by=user,
    )
    EpCell.objects.create(
        job=job,
        technology="3G",
        region="SUL",
        site_name="NS01PRCLG21",
        cell_name="31S01PRCLG2103",
        raw={"CELLNAME": "31S01PRCLG2103", "CELL ID": 30589, "RNC ID": 641},
    )
    return job


def _start_full_check_3g(auth_client, job):
    if job.created_by_id is None:
        job.created_by = auth_client.user
        job.save(update_fields=["created_by"])
    response = auth_client.post(
        reverse("ep_import:generate_scripts"),
        data=json.dumps(
            {
                "job_id": str(job.id),
                "technology": "3G",
                "site": "NS01PRCLG21",
                "cells": ["31S01PRCLG2103"],
                "pre_check": False,
                "full_check": True,
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 200
    analysis_id = response.json()["analysis_id"]
    assert auth_client.session[SESSION_ANALYSIS_KEY] == analysis_id
    return CheckAnalysis.objects.get(pk=analysis_id)


@pytest.mark.django_db
def test_generate_scripts_3g_full_check(auth_client):
    job = _ready_3g_job(user=auth_client.user)
    analysis = _start_full_check_3g(auth_client, job)
    assert analysis.full_check is True
    assert analysis.pre_check is False
    assert analysis.technology == "3G"

    scripts = auth_client.get(reverse("ep_import:scripts", kwargs={"technology": "3G"}))
    assert scripts.status_code == 200
    assert b"Full Check" in scripts.content
    assert b"LST UCELL" in scripts.content


@pytest.mark.django_db
def test_upload_and_process_full_check_3g_happy_path(auth_client):
    job = _ready_3g_job(user=auth_client.user)
    analysis = _start_full_check_3g(auth_client, job)
    payload = (FIXTURES / "full_check_3g_return.txt").read_bytes()

    returns_page = auth_client.get(reverse("precheck:import_returns", kwargs={"technology": "3G"}))
    assert returns_page.status_code == 200
    assert b"Full Check result" in returns_page.content

    upload = auth_client.post(
        reverse("poscheck:upload_full_check_return"),
        {"file": SimpleUploadedFile("full_check.txt", payload, content_type="text/plain")},
        HTTP_ACCEPT="application/json",
    )
    assert upload.status_code == 200
    assert upload.json()["type"] == "Success"

    process = auth_client.post(reverse("precheck:process", kwargs={"technology": "3G"}), HTTP_ACCEPT="application/json")
    assert process.status_code == 200
    body = process.json()
    assert body["type"] == "Success"
    assert body["redirect_url"] == reverse("poscheck:result")

    analysis.refresh_from_db()
    assert analysis.status == CheckAnalysisStatus.COMPLETED

    result_page = auth_client.get(reverse("poscheck:result"))
    assert result_page.status_code == 200
    assert b"Full Check" in result_page.content
    assert f'href="{reverse("reports:export", kwargs={"analysis_id": analysis.id})}"'.encode() in result_page.content


def _ready_5g_job(user=None):
    job = ImportJob.objects.create(
        original_filename="RNP_SRAN_CO_5g.xlsx",
        stored_file="ep_imports/test_5g.xlsx",
        status=ImportJobStatus.SUCCESS,
        created_by=user,
    )
    for cell_name, cell_id, pci in (
        ("55S01PRCLG2101", 100, 516),
        ("55S01PRCLG2102", 101, 517),
        ("55S01PRCLG2103", 102, 518),
    ):
        EpCell.objects.create(
            job=job,
            technology="5G",
            region="SUL",
            site_name="S01PRCLG21",
            cell_name=cell_name,
            raw={
                "gNBId": 1060541,
                "Tracking Area ID": 4151041,
                "CellId": cell_id,
                "FrequencyBand": "n78",
                "PhysicalCellId": pci,
                "DlNarfcn": 623334,
            },
        )
    return job


def _start_full_check_5g(auth_client, job):
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
                "cells": ["55S01PRCLG2101", "55S01PRCLG2102", "55S01PRCLG2103"],
                "pre_check": False,
                "full_check": True,
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 200
    analysis_id = response.json()["analysis_id"]
    assert auth_client.session[SESSION_ANALYSIS_KEY] == analysis_id
    return CheckAnalysis.objects.get(pk=analysis_id)


@pytest.mark.django_db
def test_generate_scripts_5g_full_check_only(auth_client):
    job = _ready_5g_job(user=auth_client.user)
    analysis = _start_full_check_5g(auth_client, job)
    assert analysis.full_check is True
    assert analysis.pre_check is False
    assert analysis.technology == "5G"

    scripts = auth_client.get(reverse("ep_import:scripts", kwargs={"technology": "5G"}))
    assert scripts.status_code == 200
    assert b"Full Check" in scripts.content
    assert b"LST NRCELL" in scripts.content
    assert b"Pre-check result" not in scripts.content
    assert b"LST GNODEBFUNCTION:;" in scripts.content  # present inside Full Check script


@pytest.mark.django_db
def test_upload_and_process_full_check_5g_happy_path(auth_client):
    job = _ready_5g_job(user=auth_client.user)
    analysis = _start_full_check_5g(auth_client, job)
    payload = (FIXTURES / "full_check_5g_return.txt").read_bytes()

    returns_page = auth_client.get(reverse("precheck:import_returns", kwargs={"technology": "5G"}))
    assert returns_page.status_code == 200
    assert b"Full Check result" in returns_page.content
    assert b"Pre-check result" not in returns_page.content

    upload = auth_client.post(
        reverse("poscheck:upload_full_check_return"),
        {"file": SimpleUploadedFile("full_check_5g.txt", payload, content_type="text/plain")},
        HTTP_ACCEPT="application/json",
    )
    assert upload.status_code == 200
    assert upload.json()["type"] == "Success"

    process = auth_client.post(reverse("precheck:process", kwargs={"technology": "5G"}), HTTP_ACCEPT="application/json")
    assert process.status_code == 200
    body = process.json()
    assert body["type"] == "Success"
    assert body["redirect_url"] == reverse("poscheck:result")

    analysis.refresh_from_db()
    assert analysis.status == CheckAnalysisStatus.COMPLETED

    result_page = auth_client.get(reverse("poscheck:result"))
    assert result_page.status_code == 200
    assert b"Full Check" in result_page.content
    assert b"gNodeB ID" in result_page.content
    assert f'href="{reverse("reports:export", kwargs={"analysis_id": analysis.id})}"'.encode() in result_page.content
