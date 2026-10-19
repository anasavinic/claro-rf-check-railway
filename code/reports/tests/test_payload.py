import pytest

from precheck.models import CheckAnalysisStatus, PrecheckResultStatus
from reports.services.errors import ExportError
from reports.services.payload import build_export_payload
from reports.tests.conftest import (
    make_analysis,
    make_poscheck_result,
    make_precheck_result,
)


@pytest.mark.django_db
def test_payload_matches_ui_validations(ep_job, user):
    analysis = make_analysis(ep_job, user, status=CheckAnalysisStatus.INCONSISTENT)
    make_precheck_result(analysis)

    payload = build_export_payload(analysis)

    assert payload.tech_label == "5G NR"
    assert payload.site == "S01PRCLG21"
    assert payload.check_types_label == "Pre-check"
    assert payload.analysis_status_label == "Inconsistent"
    assert payload.counts == {
        "total": 2,
        "consistent": 1,
        "inconsistent": 1,
        "failed": 0,
    }
    assert payload.score == 50
    assert [row.matches_ui() for row in payload.validations] == [
        {
            "label": "gNodeB ID",
            "expected": "1060541",
            "found": "1060541",
            "status": "OK",
            "note": "Matches EP gNBId.",
        },
        {
            "label": "Tracking Area Code",
            "expected": "4151041",
            "found": "4151040",
            "status": "NOK",
            "note": "Network Tracking Area Code differs from EP Tracking Area ID.",
        },
    ]


@pytest.mark.django_db
def test_payload_includes_precheck_and_full_check(ep_job, user):
    analysis = make_analysis(
        ep_job,
        user,
        pre_check=True,
        full_check=True,
        status=CheckAnalysisStatus.INCONSISTENT,
    )
    make_precheck_result(analysis, overall_status=PrecheckResultStatus.COMPLETED)
    make_poscheck_result(analysis)

    payload = build_export_payload(analysis)

    assert payload.check_types_label == "Pre-check + Full Check"
    assert [section.check_type for section in payload.sections] == [
        "Pre-check",
        "Full Check",
    ]
    assert payload.counts["total"] == 3


@pytest.mark.django_db
def test_payload_rejects_incomplete_analysis(ep_job, user):
    analysis = make_analysis(ep_job, user, status=CheckAnalysisStatus.AWAITING_RETURNS)

    with pytest.raises(ExportError) as exc:
        build_export_payload(analysis)

    assert exc.value.code == "ANALYSIS_NOT_EXPORTABLE"


@pytest.mark.django_db
def test_payload_rejects_execution_failure(ep_job, user):
    analysis = make_analysis(ep_job, user, status=CheckAnalysisStatus.FAILED)
    make_precheck_result(analysis, overall_status=PrecheckResultStatus.EXECUTION_FAILURE, validations=[])

    with pytest.raises(ExportError) as exc:
        build_export_payload(analysis)

    assert exc.value.code == "ANALYSIS_NOT_EXPORTABLE"


@pytest.mark.django_db
def test_payload_skips_missing_full_check_snapshot(ep_job, user):
    analysis = make_analysis(
        ep_job,
        user,
        pre_check=True,
        full_check=True,
        status=CheckAnalysisStatus.INCONSISTENT,
    )
    make_precheck_result(analysis)

    payload = build_export_payload(analysis)

    assert [section.check_type for section in payload.sections] == ["Pre-check"]


@pytest.mark.django_db
def test_combined_payload_aggregates_child_analyses(ep_job, user):
    from combined.services.combined import create_combined_check
    from reports.services.payload import build_combined_export_payload

    combined = create_combined_check(user=user, technologies=["4G", "5G"])
    combined.ep_job = ep_job
    combined.site_names = ["S01PRCLG21"]
    combined.status = CheckAnalysisStatus.INCONSISTENT
    combined.save(update_fields=["ep_job", "site_names", "status", "updated_at"])

    a4 = make_analysis(
        ep_job,
        user,
        technology="4G",
        site_name="S01PRCLG21",
        pre_check=False,
        full_check=True,
        status=CheckAnalysisStatus.COMPLETED,
        combined_check=combined,
    )
    a5 = make_analysis(
        ep_job,
        user,
        technology="5G",
        site_name="S01PRCLG21",
        pre_check=True,
        full_check=False,
        status=CheckAnalysisStatus.INCONSISTENT,
        combined_check=combined,
    )
    make_poscheck_result(a4)
    make_precheck_result(a5)

    payload = build_combined_export_payload(combined)

    assert "4G" in payload.technology
    assert "5G" in payload.technology
    assert payload.counts["total"] >= 2
    assert any("Full Check" in section.check_type for section in payload.sections)
    assert any("Pre-check" in section.check_type for section in payload.sections)


@pytest.mark.django_db
def test_combined_payload_rejects_when_only_failed_children(ep_job, user):
    from combined.services.combined import create_combined_check
    from reports.services.errors import ExportError
    from reports.services.payload import build_combined_export_payload

    combined = create_combined_check(user=user, technologies=["4G", "5G"])
    combined.ep_job = ep_job
    combined.site_names = ["S01PRCLG21"]
    combined.status = CheckAnalysisStatus.FAILED
    combined.save(update_fields=["ep_job", "site_names", "status", "updated_at"])
    analysis = make_analysis(
        ep_job,
        user,
        technology="5G",
        status=CheckAnalysisStatus.FAILED,
        combined_check=combined,
    )
    make_precheck_result(analysis)

    with pytest.raises(ExportError) as exc:
        build_combined_export_payload(combined)

    assert exc.value.code == "ANALYSIS_NOT_EXPORTABLE"
