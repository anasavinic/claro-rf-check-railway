import json

import pytest
from django.urls import reverse

from ep_import.models import EpCell, ImportJob, ImportJobStatus
from ep_import.services.scripts import (
    FULL_CHECK_5G_COMMANDS,
    PRECHECK_5G_COMMANDS,
    generate_full_check_4g_script,
    generate_full_check_5g_script,
    generate_full_check_script,
    generate_precheck_5g_script,
    generate_precheck_script,
)


def _ready_job(user=None):
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
        site_name="SITE_001",
        cell_name="CELL_001",
        raw={"gNBId": 123, "Tracking Area ID": 456},
    )
    return job


def test_precheck_script_contains_only_approved_commands():
    content = generate_precheck_5g_script()

    assert content == "LST GNODEBFUNCTION:;\nLST GNBTRACKINGAREA:;\n"
    assert content.splitlines() == list(PRECHECK_5G_COMMANDS)
    assert "LST NRCELL:;" not in content


def test_full_check_script_matches_approved_command_list():
    content = generate_full_check_5g_script()

    assert content.splitlines() == list(FULL_CHECK_5G_COMMANDS)
    assert content.endswith("\n")


def test_generate_full_check_4g_script_is_site_wide_and_ordered():
    content = generate_full_check_4g_script(enodeb_id="410545")
    lines = content.splitlines()

    assert lines[0] == "LST CELL:;"
    assert lines[1] == "LST ENODEBFUNCTION:;"
    assert "LST EUTRANINTRAFREQNCELL:ENODEBID=410545;" in lines
    assert "LST EUTRANINTERFREQNCELL:ENODEBID=410545;" in lines
    assert "CHK DATA2LIC:FUNCTIONTYPE=eNodeB;" in lines
    assert "CHK DATA2LIC:FUNCTIONTYPE=gNodeB;" in lines
    assert "DSP LICINFO:FUNCTIONTYPE=eNodeB;" in lines
    assert lines[-1] == "LST CELLRESEL:;"
    assert content.endswith("\n")
    assert "CELLID=" not in content


def test_generate_full_check_4g_script_defaults_enodeb_placeholder():
    content = generate_full_check_4g_script()
    assert "LST EUTRANINTRAFREQNCELL:ENODEBID=0000;" in content


def test_generate_full_check_script_dispatches_4g():
    assert generate_full_check_script("4G", enodeb_id="99") == generate_full_check_4g_script(enodeb_id="99")


def test_exported_script_uses_gerencia_header_and_site_braces():
    content = generate_full_check_script("5G", site_name="S01GOGNA83")
    lines = content.splitlines()

    assert lines[0] == "//# --- 5G NR · S01GOGNA83 ---"
    assert lines[1] == "DSP NRDUCELL:;{S01GOGNA83}"
    assert lines[-1] == "CHK DATA2LIC:FUNCTIONTYPE=gNodeB;{S01GOGNA83}"
    assert all(line == lines[0] or line.endswith("{S01GOGNA83}") for line in lines)


def test_full_check_2g_suffix_uses_bsc_and_keeps_bts_name():
    content = generate_full_check_script(
        "2G",
        site_name="S01DFSQSM1",
        bts="BS01DFSQSM1",
        bsc="BSCAC33",
        cell_names=["22S01DFSQSM101"],
        cell_ids=["1"],
    )
    lines = content.splitlines()

    assert lines[0] == "//# --- 2G · S01DFSQSM1 ---"
    assert lines[1] == 'LST GCELL:IDTYPE=BYNAME,BTSNAME="BS01DFSQSM1";{BSCAC33}'
    assert all(line == lines[0] or line.endswith("{BSCAC33}") for line in lines)
    assert "{S01DFSQSM1}" not in content
    assert "{BS01DFSQSM1}" not in content


def test_full_check_3g_suffix_uses_rnc_name():
    content = generate_full_check_script(
        "3G",
        site_name="S01DFSQSM1",
        rnc="RNCAC01",
        cell_names=["22S01DFSQSM101"],
        cell_ids=["11"],
    )
    lines = content.splitlines()

    assert lines[0] == "//# --- 3G · S01DFSQSM1 ---"
    assert lines[1].endswith("{RNCAC01}")
    assert "BSCAC33" not in content
    assert all(line == lines[0] or line.endswith("{RNCAC01}") for line in lines)


@pytest.mark.django_db
def test_generate_scripts_validates_selection_and_opens_scripts_page(auth_client):
    job = _ready_job(user=auth_client.user)

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

    assert response.status_code == 200
    assert response.json()["redirect_url"] == reverse("ep_import:scripts", kwargs={"technology": "5G"})
    assert "analysis_id" in response.json()

    page = auth_client.get(response.json()["redirect_url"])
    assert page.status_code == 200
    assert b"Generated scripts" in page.content
    assert b"LST GNODEBFUNCTION:;" in page.content
    assert b"LST GNBTRACKINGAREA:;" in page.content
    assert b"LST NRCELL:;" not in page.content
    assert b"Process analysis" in page.content


@pytest.mark.django_db
def test_generate_scripts_rejects_cell_outside_selected_site(auth_client):
    job = _ready_job(user=auth_client.user)

    response = auth_client.post(
        reverse("ep_import:generate_scripts"),
        data=json.dumps(
            {
                "job_id": str(job.id),
                "technology": "5G",
                "site": "SITE_001",
                "cells": ["OTHER_CELL"],
                "pre_check": True,
                "full_check": False,
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["type"] == "Error"


@pytest.mark.django_db
def test_download_precheck_script(auth_client):
    job = _ready_job(user=auth_client.user)
    session = auth_client.session
    session["check_script_selection"] = {
        "job_id": str(job.id),
        "technology": "5G",
        "site": "SITE_001",
        "cells": ["CELL_001"],
        "pre_check": True,
        "full_check": False,
    }
    session.save()

    response = auth_client.get(
        reverse("ep_import:download_script", kwargs={"technology": "5G", "check_type": "precheck"})
    )

    assert response.status_code == 200
    assert response.content.decode() == generate_precheck_script("5G", site_name="SITE_001")
    assert response.content.decode().splitlines()[0] == "//# --- 5G NR · SITE_001 ---"
    assert response["Content-Disposition"] == 'attachment; filename="Claro_RF_Check_PreCheck_5G.txt"'


def _ready_job_4g(user=None):
    job = ImportJob.objects.create(
        original_filename="RNP_SRAN_CO_4g.xlsx",
        stored_file="ep_imports/test_4g.xlsx",
        status=ImportJobStatus.SUCCESS,
        created_by=user,
    )
    EpCell.objects.create(
        job=job,
        technology="4G",
        region="SUL",
        site_name="S01PRCLG21",
        cell_name="43S01PRCLG2101",
        raw={
            "CELL NAME": "43S01PRCLG2101",
            "CELL ID": 8,
            "ENODEB ID": 410545,
            "TAC": 41041,
            "PCI": 21,
        },
    )
    return job


@pytest.mark.django_db
def test_generate_scripts_4g_full_check(auth_client):
    from html import escape

    job = _ready_job_4g(user=auth_client.user)

    response = auth_client.post(
        reverse("ep_import:generate_scripts"),
        data=json.dumps(
            {
                "job_id": str(job.id),
                "technology": "4G",
                "site": "S01PRCLG21",
                "cells": ["43S01PRCLG2101"],
                "pre_check": False,
                "full_check": True,
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    page = auth_client.get(response.json()["redirect_url"])
    assert page.status_code == 200
    assert b"LST CELL:;" in page.content
    assert b"LST ENODEBFUNCTION:;" in page.content
    assert b"LST EUTRANINTRAFREQNCELL:ENODEBID=410545;" in page.content
    assert b"LST UCELL" not in page.content
    expected = generate_full_check_script("4G", site_name="S01PRCLG21", enodeb_id="410545")
    assert escape(expected).strip().encode() in page.content
    download = auth_client.get(
        reverse(
            "ep_import:download_script",
            kwargs={"technology": "4G", "check_type": "full-check"},
        )
    )
    assert download.status_code == 200
    assert download.content.decode() == expected
    assert download["Content-Disposition"] == 'attachment; filename="Claro_RF_Check_FullCheck_4G.txt"'
