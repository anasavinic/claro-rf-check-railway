from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from ep_import.models import EpCell, ImportJob, ImportJobStatus
from ep_import.services.persist import process_job

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.django_db
def test_process_job_persists_cells(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    source = FIXTURES / "ep_claro_minimal.xlsx"
    job = ImportJob(
        original_filename="RNP_SRAN_CO_minimal.xlsx",
        status=ImportJobStatus.PENDING,
    )
    with source.open("rb") as fh:
        job.stored_file.save("RNP_SRAN_CO_minimal.xlsx", SimpleUploadedFile(source.name, fh.read()))
    job.save()

    process_job(job)
    job.refresh_from_db()

    assert job.status == ImportJobStatus.SUCCESS
    assert job.region == "CO"
    assert job.counts["5G"] == 2
    assert EpCell.objects.filter(job=job, technology="5G").count() == 2


@pytest.mark.django_db
def test_upload_endpoint_eager(auth_client, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    settings.CELERY_TASK_ALWAYS_EAGER = True
    source = FIXTURES / "ep_claro_minimal.xlsx"
    with source.open("rb") as fh:
        response = auth_client.post(
            reverse("ep_import:upload"),
            {
                "file": SimpleUploadedFile(
                    "RNP_SRAN_CO_minimal.xlsx",
                    fh.read(),
                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
                "technology": "5G",
            },
            HTTP_ACCEPT="application/json",
        )
    assert response.status_code in (200, 202)
    data = response.json()
    assert "job" in data
    job = ImportJob.objects.get(pk=data["job"]["id"])
    assert job.status == ImportJobStatus.SUCCESS
    assert EpCell.objects.filter(job=job).count() == 6


@pytest.mark.django_db
def test_site_cells_page(auth_client):
    response = auth_client.get(reverse("ep_import:site_cells", kwargs={"technology": "5G"}))
    assert response.status_code == 200
    assert b"Select site and cells" in response.content
    assert b"EP file" in response.content
    assert b"Initial site validation." in response.content
    html = response.content.decode()
    assert "alpinejs-csp-3.15.8" in html
    assert "alpine.min.js" not in html
    assert 'x-data="epSiteCells"' in html
    assert 'x-data="epSiteCells({' not in html
    assert 'data-technology="5G"' in html
    assert 'data-generate-scripts-url="/check/generate-scripts/"' in html
    assert '@click="generateScripts"' in html
    assert '@click="selectAllCells()"' not in html


@pytest.mark.django_db
def test_home_loads_alpine_csp(auth_client):
    response = auth_client.get(reverse("home:index"))
    assert response.status_code == 200
    html = response.content.decode()
    assert "alpinejs-csp-3.15.8" in html
    assert 'x-data="toast"' in html


@pytest.mark.django_db
def test_site_cells_precheck_only_for_5g(auth_client):
    response_4g = auth_client.get(reverse("ep_import:site_cells", kwargs={"technology": "4G"}))
    assert response_4g.status_code == 200
    assert b"Initial site validation." not in response_4g.content
    assert b"Full Check" in response_4g.content

    response_5g = auth_client.get(reverse("ep_import:site_cells", kwargs={"technology": "5G"}))
    assert b"Initial site validation." in response_5g.content
    assert b"Full Check" in response_5g.content


@pytest.mark.django_db
def test_sites_and_cells_api(auth_client, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    source = FIXTURES / "ep_claro_minimal.xlsx"
    job = ImportJob(original_filename="RNP_SRAN_CO_minimal.xlsx")
    with source.open("rb") as fh:
        job.stored_file.save("min.xlsx", SimpleUploadedFile(source.name, fh.read()))
    job.save()
    process_job(job)

    sites_resp = auth_client.get(
        reverse("ep_import:job_sites", kwargs={"job_id": job.id}),
        {"technology": "5G"},
        HTTP_ACCEPT="application/json",
    )
    assert sites_resp.status_code == 200
    sites = sites_resp.json()["sites"]
    assert sites[0]["site_name"] == "ES02ACEPT02"

    cells_resp = auth_client.get(
        reverse("ep_import:job_cells", kwargs={"job_id": job.id}),
        {"technology": "5G", "site": "ES02ACEPT02"},
        HTTP_ACCEPT="application/json",
    )
    assert cells_resp.status_code == 200
    assert len(cells_resp.json()["cells"]) == 2
    assert cells_resp.json()["total"] == 2
    assert cells_resp.json()["page"] == 1
    assert cells_resp.json()["has_next"] is False


@pytest.mark.django_db
def test_sites_and_cells_are_paginated(auth_client, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    source = FIXTURES / "ep_claro_minimal.xlsx"
    job = ImportJob(original_filename="RNP_SRAN_CO_minimal.xlsx")
    with source.open("rb") as fh:
        job.stored_file.save("min.xlsx", SimpleUploadedFile(source.name, fh.read()))
    job.save()
    process_job(job)

    for index in range(3):
        EpCell.objects.create(
            job=job,
            technology="5G",
            site_name=f"SITE_{index}",
            cell_name=f"CELL_{index}",
            on_air="NO" if index == 0 else "YES",
        )

    sites_resp = auth_client.get(
        reverse("ep_import:job_sites", kwargs={"job_id": job.id}),
        {"technology": "5G", "page": 1, "page_size": 2},
        HTTP_ACCEPT="application/json",
    )
    body = sites_resp.json()
    assert sites_resp.status_code == 200
    assert body["total"] == body["sites_total"]
    assert body["total"] >= 3
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert body["has_next"] is True
    assert len(body["sites"]) == 2
    inactive = next(site for site in body["sites"] if site["site_name"] == "SITE_0")
    assert inactive["status"] == "Inactive"

    cells_resp = auth_client.get(
        reverse("ep_import:job_cells", kwargs={"job_id": job.id}),
        {"technology": "5G", "site": "ES02ACEPT02", "q": "52S02", "page_size": 1},
        HTTP_ACCEPT="application/json",
    )
    cells = cells_resp.json()
    assert cells["total"] >= 1
    assert cells["page_size"] == 1
    assert len(cells["cells"]) == 1
    assert "52S02" in cells["cells"][0]["cell_name"]
