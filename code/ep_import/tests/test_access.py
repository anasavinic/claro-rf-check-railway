import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from ep_import.models import ImportJob, ImportJobStatus


@pytest.mark.django_db
def test_upload_requires_authentication(client):
    response = client.post(
        reverse("ep_import:upload"),
        {"file": SimpleUploadedFile("RNP_SRAN_CO.xlsx", b"PK\x03\x04")},
        HTTP_ACCEPT="application/json",
    )
    assert response.status_code == 401
    assert "secret" not in response.json()["message"].lower()


@pytest.mark.django_db
def test_other_user_cannot_read_job(client):
    owner = get_user_model().objects.create_user(username="owner", password="pass")
    other = get_user_model().objects.create_user(username="other", password="pass")
    job = ImportJob.objects.create(
        created_by=owner,
        original_filename="RNP_SRAN_CO.xlsx",
        status=ImportJobStatus.SUCCESS,
    )
    client.force_login(other)

    response = client.get(
        reverse("ep_import:job_status", kwargs={"job_id": job.id}),
        HTTP_ACCEPT="application/json",
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_unknown_job_is_not_found(auth_client):
    response = auth_client.get(
        reverse("ep_import:job_status", kwargs={"job_id": "00000000-0000-0000-0000-000000000000"}),
        HTTP_ACCEPT="application/json",
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_staff_can_read_another_users_job(auth_client):
    owner = get_user_model().objects.create_user(username="owner", password="pass")
    job = ImportJob.objects.create(
        created_by=owner,
        original_filename="RNP_SRAN_CO.xlsx",
        status=ImportJobStatus.SUCCESS,
    )
    response = auth_client.get(
        reverse("ep_import:job_status", kwargs={"job_id": job.id}),
        HTTP_ACCEPT="application/json",
    )
    assert response.status_code == 200
    assert response.json()["id"] == str(job.id)


@pytest.mark.django_db
def test_staff_cannot_generate_scripts_on_another_users_job(auth_client):
    import json

    from ep_import.models import EpCell

    owner = get_user_model().objects.create_user(username="owner", password="pass")
    job = ImportJob.objects.create(
        created_by=owner,
        original_filename="RNP_SRAN_CO.xlsx",
        status=ImportJobStatus.SUCCESS,
        stored_file="ep_imports/test.xlsx",
    )
    EpCell.objects.create(
        job=job,
        technology="5G",
        site_name="SITE_001",
        cell_name="CELL_001",
        raw={"gNBId": 1, "Tracking Area ID": 2},
    )

    response = auth_client.post(
        reverse("ep_import:generate_scripts"),
        data=json.dumps(
            {
                "job_id": str(job.id),
                "technology": "5G",
                "site": "SITE_001",
                "cells": ["CELL_001"],
                "pre_check": True,
                "full_check": False,
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["type"] == "Error"
