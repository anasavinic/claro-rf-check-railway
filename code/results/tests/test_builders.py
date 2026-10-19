from combined.services.results import build_combined_result
from precheck.models import CheckAnalysisStatus
from precheck.services.validator import get_precheck_snapshot
from results.adapters import precheck_source_snapshot, to_combined_ui_snapshot
from results.builders import build_from_analysis, build_from_combined
from results.status import (
    CHECK_KIND_FULL_CHECK,
    CHECK_KIND_PRECHECK,
    OUTCOME_ALERT,
    OUTCOME_FAILURE,
    OUTCOME_SUCCESS,
    SCOPE_COMBINED,
    SCOPE_SINGLE,
)
from results.tests.conftest import (
    make_analysis,
    make_combined,
    make_poscheck_result,
    make_precheck_result,
)


def test_build_from_analysis_precheck_only(ep_job, user):
    analysis = make_analysis(ep_job, user)
    make_precheck_result(analysis)

    consolidated = build_from_analysis(analysis)

    assert consolidated.scope == SCOPE_SINGLE
    assert consolidated.id == str(analysis.id)
    assert len(consolidated.sections) == 1
    assert consolidated.sections[0].check_kind == CHECK_KIND_PRECHECK
    assert consolidated.counts["total"] == 2
    assert consolidated.counts["consistent"] == 1
    assert consolidated.counts["inconsistent"] == 1
    assert consolidated.counts["success"] == 1
    assert consolidated.counts["failure"] == 1

    outcomes = {item.code: item.outcome for item in consolidated.validations}
    assert outcomes["GNODEB_ID"] == OUTCOME_SUCCESS
    assert outcomes["TRACKING_AREA_CODE"] == OUTCOME_FAILURE


def test_build_from_analysis_both_checks(ep_job, user):
    analysis = make_analysis(
        ep_job,
        user,
        technology="4G",
        site_name="ES01PRCLG21",
        pre_check=False,
        full_check=True,
        status=CheckAnalysisStatus.COMPLETED,
    )
    make_poscheck_result(analysis)

    consolidated = build_from_analysis(analysis)

    assert len(consolidated.sections) == 1
    assert consolidated.sections[0].check_kind == CHECK_KIND_FULL_CHECK
    assert consolidated.counts["failed"] == 1
    assert consolidated.counts["alert"] == 1
    assert any(item.outcome == OUTCOME_ALERT for item in consolidated.validations)


def test_precheck_adapter_matches_source_snapshot(ep_job, user):
    analysis = make_analysis(ep_job, user)
    make_precheck_result(analysis)

    consolidated = build_from_analysis(analysis)
    adapted = precheck_source_snapshot(consolidated)
    original = get_precheck_snapshot(analysis.id)

    assert adapted is not None and original is not None
    assert adapted["status"] == original["status"]
    assert adapted["counts"] == original["counts"]
    assert adapted["validations"] == original["validations"]
    assert adapted["gnodeb_id"] == original["gnodeb_id"]


def test_build_from_combined_aggregates_technologies(ep_job, user):
    combined = make_combined(ep_job, user)
    a5 = make_analysis(
        ep_job,
        user,
        technology="5G",
        site_name="S01PRCLG21",
        pre_check=True,
        full_check=False,
        combined_check=combined,
        status=CheckAnalysisStatus.INCONSISTENT,
    )
    a4 = make_analysis(
        ep_job,
        user,
        technology="4G",
        site_name="ES01PRCLG21",
        pre_check=False,
        full_check=True,
        combined_check=combined,
        status=CheckAnalysisStatus.COMPLETED,
        selected_cells=["43S01PRCLG2101"],
    )
    make_precheck_result(a5)
    make_poscheck_result(a4)

    consolidated = build_from_combined(combined)
    ui = to_combined_ui_snapshot(consolidated)
    via_combined = build_combined_result(combined)

    assert consolidated.scope == SCOPE_COMBINED
    assert list(consolidated.technologies) == ["4G", "5G"]
    assert ui["has_pre_results"] is True
    assert ui["has_full_results"] is True
    assert ui["counts"]["total"] == 4
    assert via_combined["counts"] == ui["counts"]
    assert via_combined["pre_validations"] == ui["pre_validations"]
    assert via_combined["full_validations"] == ui["full_validations"]
    assert via_combined["combined"] == combined
