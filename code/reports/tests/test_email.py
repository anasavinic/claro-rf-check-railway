from email import policy
from email.parser import BytesParser

import pytest

from precheck.models import CheckAnalysisStatus
from reports.services.email import render_email, render_msg
from reports.services.payload import build_export_payload
from reports.tests.conftest import make_analysis, make_precheck_result


@pytest.mark.django_db
def test_email_draft_uses_consolidated_results(ep_job, user):
    analysis = make_analysis(ep_job, user, status=CheckAnalysisStatus.INCONSISTENT)
    make_precheck_result(analysis)
    payload = build_export_payload(analysis)

    message = BytesParser(policy=policy.default).parsebytes(render_email(payload, from_address="rf@example.com"))

    assert message["X-Unsent"] == "1"
    assert message["From"] == "rf@example.com"
    assert "S01PRCLG21" in message["Subject"]
    body = message.get_body(preferencelist=("plain",)).get_content()
    assert "gNodeB ID | 1060541 | 1060541 | OK |" in body
    assert "Tracking Area Code | 4151041 | 4151040 | NOK |" in body
    assert "Overall Score: 50%" in body

    attachments = list(message.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "Claro_RF_Check_Report_5G_S01PRCLG21.xlsx"
    blob = attachments[0].get_payload(decode=True)
    if blob is None:
        blob = attachments[0].get_content()
    assert blob[:2] == b"PK"


@pytest.mark.django_db
def test_msg_draft_is_an_outlook_file_with_the_same_results(ep_job, user):
    analysis = make_analysis(ep_job, user, status=CheckAnalysisStatus.INCONSISTENT)
    make_precheck_result(analysis)
    payload = build_export_payload(analysis)

    content = render_msg(payload, from_address="rf@example.com")

    assert content[:8] == bytes.fromhex("D0CF11E0A1B11AE1")
    assert "Claro RF Check".encode("utf-16-le") in content
    assert "gNodeB ID".encode("utf-16-le") in content
