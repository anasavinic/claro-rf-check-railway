"""Validate and store Gerencia Full Check return uploads."""

from __future__ import annotations

from pathlib import Path

from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils import timezone

from ep_import.services.content import sha256_file
from poscheck.models import PoscheckResult
from poscheck.services.errors import PoscheckError, analysis_busy
from precheck.models import CheckAnalysis, CheckAnalysisStatus, CheckReturnFile, CheckType
from precheck.services.returns import validate_return_upload

_RESET_AFTER_REPLACE = frozenset(
    {
        CheckAnalysisStatus.COMPLETED,
        CheckAnalysisStatus.INCONSISTENT,
        CheckAnalysisStatus.FAILED,
    }
)


def store_full_check_return(analysis: CheckAnalysis, uploaded: UploadedFile) -> CheckReturnFile:
    issues = validate_return_upload(uploaded)
    if issues:
        raise PoscheckError("Upload error", issues)

    digest = sha256_file(uploaded)

    with transaction.atomic():
        locked = CheckAnalysis.objects.select_for_update().get(pk=analysis.pk)
        if locked.status == CheckAnalysisStatus.PROCESSING:
            raise PoscheckError("Upload error", [analysis_busy()])

        existing = CheckReturnFile.objects.filter(
            analysis=locked,
            check_type=CheckType.FULL_CHECK,
        ).first()
        if existing is not None:
            if existing.content_sha256 == digest and existing.stored_file:
                _reset_for_reanalyze(locked)
                return existing
            if existing.stored_file:
                existing.stored_file.delete(save=False)
            existing.original_filename = Path(uploaded.name or "full_check.txt").name
            existing.stored_file = uploaded
            existing.content_sha256 = digest
            existing.uploaded_at = timezone.now()
            existing.save()
            stored = existing
        else:
            stored = CheckReturnFile.objects.create(
                analysis=locked,
                check_type=CheckType.FULL_CHECK,
                original_filename=Path(uploaded.name or "full_check.txt").name,
                stored_file=uploaded,
                content_sha256=digest,
            )

        _reset_for_reanalyze(locked)
        return stored


def _reset_for_reanalyze(analysis: CheckAnalysis) -> None:
    from precheck.services.execution import cancel_inflight_executions

    cancel_inflight_executions(analysis)
    deleted, _ = PoscheckResult.objects.filter(analysis=analysis).delete()
    if analysis.status in _RESET_AFTER_REPLACE or deleted:
        if analysis.status != CheckAnalysisStatus.AWAITING_RETURNS:
            analysis.status = CheckAnalysisStatus.AWAITING_RETURNS
            analysis.save(update_fields=["status", "updated_at"])


def has_full_check_return(analysis: CheckAnalysis) -> bool:
    return analysis.return_files.filter(check_type=CheckType.FULL_CHECK).exists()
