"""Tests for Combined RF Check foundation."""

from __future__ import annotations

import json

import pytest
from django.urls import reverse

from combined.services.combined import (
    SESSION_COMBINED_KEY,
    create_combined_check,
    site_family_keys,
    sites_across_technologies,
)
from ep_import.models import EpCell, ImportJob, ImportJobStatus
from precheck.models import CheckAnalysisStatus, CombinedCheck


def _ready_multi_tech_job(*, user):
    job = ImportJob.objects.create(
        created_by=user,
        original_filename="ep.xlsx",
        stored_file="ep/ep.xlsx",
        content_sha256="abc",
        status=ImportJobStatus.SUCCESS,
        counts={"2G": 0, "3G": 0, "4G": 2, "5G": 2},
    )
    EpCell.objects.create(
        job=job,
        technology="4G",
        site_name="SITE_A",
        cell_name="LTE_1",
        on_air="YES",
        raw={"ENODEB ID": "100"},
    )
    EpCell.objects.create(
        job=job,
        technology="4G",
        site_name="SITE_A",
        cell_name="LTE_2",
        on_air="YES",
        raw={"ENODEB ID": "100"},
    )
    EpCell.objects.create(
        job=job,
        technology="5G",
        site_name="SITE_A",
        cell_name="NR_1",
        on_air="YES",
        raw={"gNodeB ID": "200"},
    )
    EpCell.objects.create(
        job=job,
        technology="5G",
        site_name="SITE_B",
        cell_name="NR_2",
        on_air="YES",
        raw={"gNodeB ID": "201"},
    )
    return job


@pytest.mark.django_db
def test_create_combined_requires_two_technologies(auth_client):
    with pytest.raises(ValueError):
        create_combined_check(user=auth_client.user, technologies=["5G"])


@pytest.mark.django_db
def test_sites_across_technologies_groups_badges(auth_client):
    job = _ready_multi_tech_job(user=auth_client.user)
    sites = sites_across_technologies(job, ["4G", "5G"])
    by_name = {s["site_name"]: s for s in sites}
    assert by_name["SITE_A"]["technologies"] == ["4G", "5G"]
    assert by_name["SITE_A"]["cell_count"] == 3
    assert by_name["SITE_B"]["technologies"] == ["5G"]


def test_site_family_keys_group_prefixed_station_names():
    keys = site_family_keys(["ES01PRCLG21", "NS01PRCLG21", "S01PRCLG21", "OTHER"])
    assert keys["ES01PRCLG21"] == "S01PRCLG21"
    assert keys["NS01PRCLG21"] == "S01PRCLG21"
    assert keys["S01PRCLG21"] == "S01PRCLG21"
    assert keys["OTHER"] == "OTHER"


@pytest.mark.django_db
def test_configure_starts_with_no_technologies_selected(auth_client):
    response = auth_client.get(reverse("combined:configure"))
    assert response.status_code == 200
    assert b'data-selected="[]"' in response.content
    assert b"0 technologies selected" in response.content


@pytest.mark.django_db
def test_configure_and_materialize_flow(auth_client):
    job = _ready_multi_tech_job(user=auth_client.user)

    response = auth_client.post(
        reverse("combined:save_configure"),
        data=json.dumps({"technologies": ["4G", "5G"]}),
        content_type="application/json",
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "Success"
    assert auth_client.session[SESSION_COMBINED_KEY] == payload["combined_id"]

    combined = CombinedCheck.objects.get(pk=payload["combined_id"])
    assert combined.technologies == ["4G", "5G"]
    assert combined.pre_check is True
    assert combined.full_check is True

    gen = auth_client.post(
        reverse("combined:generate_scripts"),
        data=json.dumps({"job_id": str(job.id), "sites": ["SITE_A"]}),
        content_type="application/json",
    )
    assert gen.status_code == 200
    assert gen.json()["redirect_url"] == reverse("combined:scripts")

    combined.refresh_from_db()
    assert combined.status == CheckAnalysisStatus.AWAITING_RETURNS
    analyses = list(combined.analyses.order_by("technology"))
    assert [a.technology for a in analyses] == ["4G", "5G"]
    assert analyses[0].pre_check is False and analyses[0].full_check is True
    assert analyses[1].pre_check is True and analyses[1].full_check is True
    assert set(analyses[0].selected_cells) == {"LTE_1", "LTE_2"}
    assert analyses[1].selected_cells == ["NR_1"]

    scripts_page = auth_client.get(reverse("combined:scripts"))
    assert scripts_page.status_code == 200
    assert b"Generated Scripts" in scripts_page.content
    assert b"Scripts by technology" in scripts_page.content
    assert b"4G LTE" in scripts_page.content
    assert b"5G NR" in scripts_page.content
    assert b"Import results" in scripts_page.content
    assert b"Full Check" in scripts_page.content


@pytest.mark.django_db
def test_full_check_upload_requires_technology(auth_client):
    from django.core.files.uploadedfile import SimpleUploadedFile

    job = _ready_multi_tech_job(user=auth_client.user)
    auth_client.post(
        reverse("combined:save_configure"),
        data=json.dumps({"technologies": ["4G", "5G"]}),
        content_type="application/json",
    )
    auth_client.post(
        reverse("combined:generate_scripts"),
        data=json.dumps({"job_id": str(job.id), "sites": ["SITE_A"]}),
        content_type="application/json",
    )

    missing = auth_client.post(
        reverse("combined:upload_full_check"),
        data={"file": SimpleUploadedFile("full.txt", b"RETCODE = 0")},
    )
    assert missing.status_code == 400

    ok = auth_client.post(
        reverse("combined:upload_full_check"),
        data={
            "technology": "4G",
            "file": SimpleUploadedFile("full_4g.txt", b"RETCODE = 0\nLST CELL"),
        },
    )
    assert ok.status_code == 200
    payload = ok.json()
    assert payload["type"] == "Success"
    assert payload["technology"] == "4G"
    board = payload["returns_board"]
    by_tech = {item["technology"]: item for item in board["technologies"]}
    assert by_tech["4G"]["has_full_check"] is True
    assert by_tech["5G"]["has_full_check"] is False


@pytest.mark.django_db
def test_full_check_upload_unlocks_processing_analyses(auth_client):
    from django.core.files.uploadedfile import SimpleUploadedFile

    job = _ready_multi_tech_job(user=auth_client.user)
    auth_client.post(
        reverse("combined:save_configure"),
        data=json.dumps({"technologies": ["3G", "4G"]}),
        content_type="application/json",
    )
    # Need 3G cells in job
    EpCell.objects.create(
        job=job,
        technology="3G",
        site_name="SITE_A",
        cell_name="UMTS_1",
        on_air="YES",
        raw={"CELL ID": "11"},
    )
    auth_client.post(
        reverse("combined:generate_scripts"),
        data=json.dumps({"job_id": str(job.id), "sites": ["SITE_A"]}),
        content_type="application/json",
    )
    combined = CombinedCheck.objects.get(pk=auth_client.session[SESSION_COMBINED_KEY])
    for analysis in combined.analyses.all():
        analysis.status = CheckAnalysisStatus.PROCESSING
        analysis.save(update_fields=["status", "updated_at"])

    ok = auth_client.post(
        reverse("combined:upload_full_check"),
        data={
            "technology": "3G",
            "file": SimpleUploadedFile("full_3g.txt", b"RETCODE = 0\nLST UCELL"),
        },
    )
    assert ok.status_code == 200
    assert ok.json()["type"] == "Success"
    assert combined.analyses.filter(technology="3G").first().status == CheckAnalysisStatus.AWAITING_RETURNS


@pytest.mark.django_db
def test_recover_stuck_processing_before_reprocess(auth_client):
    from combined.services.execution import recover_stuck_analyses

    job = _ready_multi_tech_job(user=auth_client.user)
    auth_client.post(
        reverse("combined:save_configure"),
        data=json.dumps({"technologies": ["4G", "5G"]}),
        content_type="application/json",
    )
    auth_client.post(
        reverse("combined:generate_scripts"),
        data=json.dumps({"job_id": str(job.id), "sites": ["SITE_A"]}),
        content_type="application/json",
    )
    combined = CombinedCheck.objects.get(pk=auth_client.session[SESSION_COMBINED_KEY])
    for analysis in combined.analyses.all():
        analysis.status = CheckAnalysisStatus.PROCESSING
        analysis.save(update_fields=["status", "updated_at"])
    combined.status = CheckAnalysisStatus.PROCESSING
    combined.save(update_fields=["status", "updated_at"])

    recovered = recover_stuck_analyses(combined)
    assert recovered == 2
    combined.refresh_from_db()
    assert combined.status == CheckAnalysisStatus.AWAITING_RETURNS
    assert all(a.status == CheckAnalysisStatus.AWAITING_RETURNS for a in combined.analyses.all())


@pytest.mark.django_db
def test_sidebar_hides_reports_and_settings(auth_client):
    response = auth_client.get(reverse("home:index"))
    assert response.status_code == 200
    assert b"Reports" not in response.content
    assert b"Settings" not in response.content
    assert b"Combined RF check" in response.content
