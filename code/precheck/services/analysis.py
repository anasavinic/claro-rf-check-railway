"""Create and resolve check analyses from UI selections."""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser

from ep_import.models import ImportJob
from precheck.models import CheckAnalysis, CheckAnalysisStatus

SESSION_ANALYSIS_KEY = "check_analysis_id"


def create_check_analysis(
    *,
    user: AbstractBaseUser | None,
    job: ImportJob,
    site: str,
    cells: list[str],
    pre_check: bool,
    full_check: bool,
    technology: str = "5G",
) -> CheckAnalysis:
    """Persist the current selection so later steps do not depend only on the session."""
    return CheckAnalysis.objects.create(
        created_by=user if getattr(user, "is_authenticated", False) else None,
        ep_job=job,
        technology=technology,
        site_name=site,
        selected_cells=list(cells),
        pre_check=pre_check,
        full_check=full_check,
        status=CheckAnalysisStatus.AWAITING_RETURNS,
    )
