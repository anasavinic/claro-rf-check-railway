import json

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.urls import reverse

from precheck.models import CheckAnalysisStatus, PrecheckResultStatus
from precheck.services.analysis import SESSION_ANALYSIS_KEY
from reports.services.xlsx import XLSX_CONTENT_TYPE
from reports.tests.conftest import make_analysis, make_precheck_result
from reports.views import export_report, prepare_email


def _request(user, path: str):
    request = RequestFactory().get(path, HTTP_ACCEPT="application/json", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
    request.user = user
    return request


@pytest.mark.django_db
def test_export_downloads_xlsx_for_completed_analysis(ep_job, user):
    analysis = make_analysis(ep_job, user, status=CheckAnalysisStatus.INCONSISTENT)
    make_precheck_result(analysis)

    response = export_report(_request(user, f"/check/reports/{analysis.id}/export/"), analysis.id)

    assert response.status_code == 200
    assert XLSX_CONTENT_TYPE in response["Content-Type"]
    assert "Claro_RF_Check_Report_5G_S01PRCLG21.xlsx" in response["Content-Disposition"]
    assert response.content[:2] == b"PK"


@pytest.mark.django_db
def test_email_downloads_eml_for_completed_analysis(ep_job, user):
    analysis = make_analysis(ep_job, user, status=CheckAnalysisStatus.INCONSISTENT)
    make_precheck_result(analysis)

    response = prepare_email(_request(user, f"/check/reports/{analysis.id}/email/"), analysis.id)

    assert response.status_code == 200
    assert "message/rfc822" in response["Content-Type"]
    assert "Claro_RF_Check_Report_5G_S01PRCLG21.eml" in response["Content-Disposition"]
    assert b"X-Unsent: 1" in response.content
    assert b"gNodeB ID" in response.content


@pytest.mark.django_db
def test_export_rejects_incomplete_analysis(ep_job, user):
    analysis = make_analysis(ep_job, user, status=CheckAnalysisStatus.AWAITING_RETURNS)

    response = export_report(_request(user, f"/check/reports/{analysis.id}/export/"), analysis.id)

    assert response.status_code == 400
    body = json.loads(response.content)
    assert body["type"] == "Error"
    assert "completed" in body["message"].lower()


@pytest.mark.django_db
def test_export_rejects_execution_failure(ep_job, user):
    analysis = make_analysis(ep_job, user, status=CheckAnalysisStatus.FAILED)
    make_precheck_result(analysis, overall_status=PrecheckResultStatus.EXECUTION_FAILURE, validations=[])

    response = prepare_email(_request(user, f"/check/reports/{analysis.id}/email/"), analysis.id)

    assert response.status_code == 400
    assert json.loads(response.content)["type"] == "Error"


@pytest.mark.django_db
def test_other_user_cannot_export_analysis(ep_job, user):
    analysis = make_analysis(ep_job, user, status=CheckAnalysisStatus.INCONSISTENT)
    make_precheck_result(analysis)
    other = get_user_model().objects.create_user(username="other-report", password="pass")

    response = export_report(_request(other, f"/check/reports/{analysis.id}/export/"), analysis.id)

    assert response.status_code == 404


@pytest.mark.django_db
def test_result_page_exposes_export_actions(auth_client, ep_job, user):
    pytest.importorskip("core_connect_sso")
    analysis = make_analysis(ep_job, user, status=CheckAnalysisStatus.INCONSISTENT)
    make_precheck_result(analysis)
    session = auth_client.session
    session[SESSION_ANALYSIS_KEY] = str(analysis.id)
    session.save()

    page = auth_client.get(reverse("precheck:result", kwargs={"technology": "5G"}))

    assert page.status_code == 200
    export_url = reverse("reports:export", kwargs={"analysis_id": analysis.id})
    assert b"Coming soon" not in page.content
    assert f'href="{export_url}"'.encode() in page.content
    assert b"prepareEmail('eml')" in page.content
    assert b"prepareEmail('msg')" in page.content
    email_url = reverse("reports:email", kwargs={"analysis_id": analysis.id})
    assert export_url.encode() in page.content
    assert email_url.encode() in page.content


@pytest.mark.django_db
def test_email_downloads_msg_for_completed_analysis(ep_job, user):
    analysis = make_analysis(ep_job, user, status=CheckAnalysisStatus.INCONSISTENT)
    make_precheck_result(analysis)

    response = prepare_email(
        _request(user, f"/check/reports/{analysis.id}/email/?format=msg"),
        analysis.id,
    )

    assert response.status_code == 200
    assert "application/vnd.ms-outlook" in response["Content-Type"]
    assert "Claro_RF_Check_Report_5G_S01PRCLG21.msg" in response["Content-Disposition"]
    assert response.content[:8] == bytes.fromhex("D0CF11E0A1B11AE1")


@pytest.mark.django_db
def test_combined_result_exposes_export_and_email(auth_client, ep_job, user):
    from combined.services.combined import SESSION_COMBINED_KEY
    from precheck.models import CombinedCheck

    combined = CombinedCheck.objects.create(
        created_by=user,
        ep_job=ep_job,
        technologies=["4G", "5G"],
        site_names=["S01PRCLG21"],
        pre_check=True,
        full_check=False,
        status=CheckAnalysisStatus.INCONSISTENT,
    )
    analysis = make_analysis(
        ep_job,
        user,
        combined_check=combined,
        technology="5G",
        status=CheckAnalysisStatus.INCONSISTENT,
    )
    make_precheck_result(analysis)
    session = auth_client.session
    session[SESSION_COMBINED_KEY] = str(combined.id)
    session.save()

    page = auth_client.get(reverse("combined:result"))
    assert page.status_code == 200
    export_url = reverse("reports:combined_export")
    assert b"Coming soon" not in page.content
    assert f'href="{export_url}"'.encode() in page.content
    assert b"prepareEmail('msg')" in page.content
    assert export_url.encode() in page.content
    assert reverse("reports:combined_email").encode() in page.content

    exported = auth_client.get(
        reverse("reports:combined_export"),
        HTTP_ACCEPT="application/json",
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )
    assert exported.status_code == 200
    assert exported.content[:2] == b"PK"

    emailed = auth_client.get(
        reverse("reports:combined_email") + "?format=msg",
        HTTP_ACCEPT="application/json",
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )
    assert emailed.status_code == 200
    assert emailed.content[:8] == bytes.fromhex("D0CF11E0A1B11AE1")
