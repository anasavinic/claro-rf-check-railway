"""Validate and store Gerência return uploads for checks."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils import timezone

from ep_import.services.content import sha256_file
from precheck.models import CheckAnalysis, CheckAnalysisStatus, CheckReturnFile, CheckType, PrecheckResult
from precheck.services.errors import PrecheckError, PrecheckIssue, analysis_busy

MAX_RETURN_UPLOAD_BYTES: Final[int] = 10 * 1024 * 1024
ALLOWED_RETURN_EXTENSIONS: Final[frozenset[str]] = frozenset({".txt", ".log"})

_RESET_AFTER_REPLACE = frozenset(
    {
        CheckAnalysisStatus.COMPLETED,
        CheckAnalysisStatus.INCONSISTENT,
        CheckAnalysisStatus.FAILED,
    }
)


def validate_return_upload(uploaded: UploadedFile) -> list[PrecheckIssue]:
    name = getattr(uploaded, "name", "") or "file"
    suffix = Path(name).suffix.lower()
    issues: list[PrecheckIssue] = []
    if suffix not in ALLOWED_RETURN_EXTENSIONS:
        issues.append(
            PrecheckIssue(
                code="INVALID_RETURN_EXTENSION",
                message=f"Invalid format for '{name}'. Accepted formats: .txt, .log.",
            )
        )
    size = getattr(uploaded, "size", None)
    if size is not None and size > MAX_RETURN_UPLOAD_BYTES:
        issues.append(
            PrecheckIssue(
                code="RETURN_FILE_TOO_LARGE",
                message=(
                    f"File is too large ({size // (1024 * 1024)} MB). "
                    f"Maximum allowed: {MAX_RETURN_UPLOAD_BYTES // (1024 * 1024)} MB."
                ),
            )
        )
    if size == 0:
        issues.append(
            PrecheckIssue(
                code="EMPTY_RETURN",
                message="The return file is empty.",
            )
        )
    return issues


def store_precheck_return(analysis: CheckAnalysis, uploaded: UploadedFile) -> CheckReturnFile:
    issues = validate_return_upload(uploaded)
    if issues:
        raise PrecheckError("Upload error", issues)

    digest = sha256_file(uploaded)

    with transaction.atomic():
        locked = CheckAnalysis.objects.select_for_update().get(pk=analysis.pk)
        if locked.status == CheckAnalysisStatus.PROCESSING:
            raise PrecheckError("Upload error", [analysis_busy()])

        existing = CheckReturnFile.objects.filter(
            analysis=locked,
            check_type=CheckType.PRECHECK,
        ).first()
        if existing is not None:
            if existing.content_sha256 == digest and existing.stored_file:
                _reset_for_reanalyze(locked)
                return existing
            if existing.stored_file:
                existing.stored_file.delete(save=False)
            existing.original_filename = Path(uploaded.name or "precheck.txt").name
            existing.stored_file = uploaded
            existing.content_sha256 = digest
            existing.uploaded_at = timezone.now()
            existing.save()
            stored = existing
        else:
            stored = CheckReturnFile.objects.create(
                analysis=locked,
                check_type=CheckType.PRECHECK,
                original_filename=Path(uploaded.name or "precheck.txt").name,
                stored_file=uploaded,
                content_sha256=digest,
            )

        _reset_for_reanalyze(locked)
        return stored


def _reset_for_reanalyze(analysis: CheckAnalysis) -> None:
    """Invalidate prior results so a replaced MML can be reprocessed."""
    from poscheck.models import PoscheckResult
    from precheck.services.execution import cancel_inflight_executions

    cancel_inflight_executions(analysis)
    deleted_pre, _ = PrecheckResult.objects.filter(analysis=analysis).delete()
    deleted_pos, _ = PoscheckResult.objects.filter(analysis=analysis).delete()
    deleted = deleted_pre or deleted_pos
    if analysis.status in _RESET_AFTER_REPLACE or deleted:
        if analysis.status != CheckAnalysisStatus.AWAITING_RETURNS:
            analysis.status = CheckAnalysisStatus.AWAITING_RETURNS
            analysis.save(update_fields=["status", "updated_at"])


def has_precheck_return(analysis: CheckAnalysis) -> bool:
    return analysis.return_files.filter(check_type=CheckType.PRECHECK).exists()


def has_full_check_return(analysis: CheckAnalysis) -> bool:
    return analysis.return_files.filter(check_type=CheckType.FULL_CHECK).exists()
