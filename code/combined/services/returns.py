"""Store return files for CombinedCheck — one return per technology."""

from __future__ import annotations

from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction

from combined.services.combined import TECH_LABELS, tech_label
from poscheck.services.returns import store_full_check_return
from precheck.models import CheckAnalysis, CheckAnalysisStatus, CheckType, CombinedCheck
from precheck.services.errors import PrecheckError, PrecheckIssue
from precheck.services.execution import cancel_inflight_executions
from precheck.services.returns import store_precheck_return, validate_return_upload


def _unlock_for_upload(analyses: list[CheckAnalysis]) -> None:
    """Cancel in-flight work so return uploads are never blocked by stuck PROCESSING."""
    for analysis in analyses:
        cancel_inflight_executions(analysis, reason="RETURN_UPLOAD")
        if analysis.status == CheckAnalysisStatus.PROCESSING:
            analysis.status = CheckAnalysisStatus.AWAITING_RETURNS
            analysis.save(update_fields=["status", "updated_at"])


def store_combined_precheck_return(combined: CombinedCheck, uploaded: UploadedFile) -> int:
    """Attach the Pre-check return to every 5G child analysis that needs it."""
    issues = validate_return_upload(uploaded)
    if issues:
        raise PrecheckError("Upload error", issues)

    targets = list(combined.analyses.filter(pre_check=True, technology="5G").order_by("site_name"))
    if not targets:
        raise PrecheckError(
            "Upload error",
            [
                PrecheckIssue(
                    code="NO_PRECHECK_TARGETS",
                    message="No Pre-check analyses in this combined check.",
                )
            ],
        )

    raw = uploaded.read()
    name = Path(uploaded.name or "precheck.txt").name
    count = 0
    with transaction.atomic():
        _unlock_for_upload(targets)
        for analysis in targets:
            store_precheck_return(analysis, ContentFile(raw, name=name))
            count += 1
        if combined.status == CheckAnalysisStatus.PROCESSING:
            combined.status = CheckAnalysisStatus.AWAITING_RETURNS
            combined.save(update_fields=["status", "updated_at"])
    return count


def store_combined_full_check_return(
    combined: CombinedCheck,
    uploaded: UploadedFile,
    *,
    technology: str,
) -> int:
    """Attach Full Check return to child analyses of a single technology."""
    tech = str(technology or "").upper().strip()
    if tech == "5G NR":
        tech = "5G"
    if tech not in TECH_LABELS:
        raise PrecheckError(
            "Upload error",
            [
                PrecheckIssue(
                    code="TECHNOLOGY_REQUIRED",
                    message="Select which technology this Full Check return belongs to.",
                )
            ],
        )

    issues = validate_return_upload(uploaded)
    if issues:
        raise PrecheckError("Upload error", issues)

    targets = list(combined.analyses.filter(full_check=True, technology=tech).order_by("site_name"))
    if not targets:
        raise PrecheckError(
            "Upload error",
            [
                PrecheckIssue(
                    code="NO_FULLCHECK_TARGETS",
                    message=f"No Full Check analyses found for {tech_label(tech)}.",
                )
            ],
        )

    raw = uploaded.read()
    name = Path(uploaded.name or f"full_check_{tech}.txt").name
    count = 0
    with transaction.atomic():
        _unlock_for_upload(targets)
        for analysis in targets:
            # Refresh after unlock so store_* sees AWAITING_RETURNS.
            analysis.refresh_from_db()
            store_full_check_return(analysis, ContentFile(raw, name=name))
            count += 1
        if combined.status == CheckAnalysisStatus.PROCESSING:
            combined.status = CheckAnalysisStatus.AWAITING_RETURNS
            combined.save(update_fields=["status", "updated_at"])
    return count


def combined_return_ready(combined: CombinedCheck) -> bool:
    for analysis in combined.analyses.all():
        types = set(analysis.return_files.values_list("check_type", flat=True))
        if analysis.pre_check and CheckType.PRECHECK not in types:
            return False
        if analysis.full_check and CheckType.FULL_CHECK not in types:
            return False
    return combined.analyses.exists()


def returns_board(combined: CombinedCheck) -> dict:
    """Build per-technology return status for the scripts UI."""
    analyses = list(combined.analyses.prefetch_related("return_files").order_by("technology", "site_name"))
    techs = []
    for tech in ["2G", "3G", "4G", "5G"]:
        tech_analyses = [a for a in analyses if a.technology == tech]
        if not tech_analyses:
            continue
        needs_pre = any(a.pre_check for a in tech_analyses)
        needs_full = any(a.full_check for a in tech_analyses)
        pre_file = None
        full_file = None
        for analysis in tech_analyses:
            for rf in analysis.return_files.all():
                if rf.check_type == CheckType.PRECHECK and pre_file is None:
                    pre_file = rf
                if rf.check_type == CheckType.FULL_CHECK and full_file is None:
                    full_file = rf
        techs.append(
            {
                "technology": tech,
                "label": tech_label(tech),
                "needs_precheck": needs_pre,
                "needs_full_check": needs_full,
                "has_precheck": pre_file is not None,
                "has_full_check": full_file is not None,
                "precheck_filename": pre_file.original_filename if pre_file else "",
                "full_check_filename": full_file.original_filename if full_file else "",
                "ready": (not needs_pre or pre_file is not None) and (not needs_full or full_file is not None),
            }
        )

    return {
        "technologies": techs,
        "all_ready": bool(techs) and all(item["ready"] for item in techs),
        "has_precheck_slot": any(item["needs_precheck"] for item in techs),
        "full_check_techs": [item for item in techs if item["needs_full_check"]],
        "precheck_tech": next((item for item in techs if item["needs_precheck"]), None),
    }
