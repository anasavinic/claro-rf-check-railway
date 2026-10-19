from precheck.models import CheckAnalysisStatus
from results.builders import build_from_analysis, build_from_combined
from results.groupings import by_category, by_site, by_technology
from results.tests.conftest import (
    make_analysis,
    make_combined,
    make_poscheck_result,
    make_precheck_result,
)


def test_groupings_by_technology_site_and_category(ep_job, user):
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
    techs = {g.key: g.counts["total"] for g in by_technology(consolidated)}
    sites = {g.key: g.counts["total"] for g in by_site(consolidated)}
    categories = {g.key for g in by_category(consolidated)}

    assert techs == {"4G": 2, "5G": 2}
    assert sites == {"ES01PRCLG21": 2, "S01PRCLG21": 2}
    assert "GNODEB_ID" in categories
    assert "ENODEB_ID" in categories
    assert "CELL_NAME" in categories


def test_combined_ui_snapshot_exposes_group_summaries(ep_job, user):
    from results.adapters import to_combined_ui_snapshot

    analysis = make_analysis(ep_job, user)
    make_precheck_result(analysis)
    consolidated = build_from_analysis(analysis)
    ui = to_combined_ui_snapshot(consolidated)

    assert ui["sites"] == ["S01PRCLG21"]
    assert "GNODEB_ID" in ui["categories"]
    assert ui["by_category"]
    assert ui["by_site"][0]["key"] == "S01PRCLG21"
