"""Persist a validated EP stream into ImportJob / EpCell."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator

from django.db import IntegrityError, transaction
from django.db.utils import InterfaceError, OperationalError
from django.utils import timezone

from ep_import.models import EpCell, ImportJob, ImportJobStatus, ImportStage
from ep_import.schema import PERSIST_BATCH_SIZE
from ep_import.services.errors import (
    EpImportError,
    TransientImportError,
    import_timed_out,
    unexpected_failure,
)
from ep_import.services.importer import ValidationResult, iter_valid_cells, validate_workbook
from ep_import.services.normalizer import NormalizedCell
from ep_import.services.source import owned_workbook_stream

logger = logging.getLogger("ep_import")

_TRANSIENT_ERRORS = (OperationalError, InterfaceError, ConnectionError, TimeoutError, TransientImportError)


def process_job(job: ImportJob, *, task_id: str = "") -> ImportJob:
    """Validate then persist. Never stores partial cells. Never returns exception text to the user."""
    started = time.monotonic()
    locked = _claim(job, task_id)
    if locked is None or locked.status == ImportJobStatus.SUCCESS:
        return locked or job
    job = locked
    _log(job, "ep_import.started")

    try:
        with job.stored_file.open("rb") as stored:
            with owned_workbook_stream(stored) as stream:
                result = validate_workbook(
                    stream,
                    job.original_filename,
                    size=job.stored_file.size,
                    progress=lambda stage, processed, total: _progress(job, stage, processed, total),
                )
                stream.seek(0)
                _progress(job, ImportStage.PERSISTING, 0, result.row_count)
                _persist_stream(job, iter_valid_cells(stream, job.original_filename, result.region), result)
    except EpImportError as exc:
        return _fail(job, exc.title, [issue.as_dict() for issue in exc.issues], started, exc.issues[0].code)
    except _TRANSIENT_ERRORS as exc:
        _log(job, "ep_import.retry", error_code=type(exc).__name__, duration_ms=_elapsed(started))
        raise TransientImportError("transient import failure") from exc
    except Exception as exc:
        if type(exc).__name__ == "SoftTimeLimitExceeded":
            return _fail(
                job,
                "Import timed out",
                [import_timed_out().as_dict()],
                started,
                "IMPORT_TIMEOUT",
            )
        logger.exception(
            "ep_import.failed",
            extra={
                "job_id": str(job.id),
                "stage": job.stage,
                "error_code": "UNEXPECTED_ERROR",
                "duration_ms": _elapsed(started),
            },
        )
        return _fail(
            job,
            "Import error",
            [unexpected_failure().as_dict()],
            started,
            "UNEXPECTED_ERROR",
        )

    _log(
        job,
        "ep_import.succeeded",
        duration_ms=_elapsed(started),
        rows=job.rows_processed,
    )
    return job


def _claim(job: ImportJob, task_id: str) -> ImportJob | None:
    with transaction.atomic():
        locked = ImportJob.objects.select_for_update().get(pk=job.pk)
        if locked.status == ImportJobStatus.SUCCESS:
            return locked
        if locked.status == ImportJobStatus.PROCESSING and locked.task_id and task_id and locked.task_id != task_id:
            return locked
        locked.status = ImportJobStatus.PROCESSING
        locked.stage = ImportStage.VALIDATING
        locked.started_at = timezone.now()
        locked.task_id = task_id or locked.task_id
        locked.issues = []
        locked.error_title = ""
        locked.rows_processed = 0
        locked.rows_total = None
        locked.save(
            update_fields=[
                "status",
                "stage",
                "started_at",
                "task_id",
                "issues",
                "error_title",
                "rows_processed",
                "rows_total",
            ]
        )
        return locked


def _persist_stream(job: ImportJob, cells: Iterator[NormalizedCell], result: ValidationResult) -> None:
    processed = 0
    try:
        with transaction.atomic():
            job.cells.all().delete()
            batch: list[EpCell] = []
            for cell in cells:
                batch.append(
                    EpCell(
                        job=job,
                        technology=cell.technology.value,
                        region=cell.region or "",
                        state=cell.state or "",
                        site_name=cell.site_name,
                        cell_name=cell.cell_name,
                        on_air=cell.on_air or "",
                        raw=cell.raw,
                    )
                )
                if len(batch) >= PERSIST_BATCH_SIZE:
                    EpCell.objects.bulk_create(batch)
                    processed += len(batch)
                    batch.clear()
            if batch:
                EpCell.objects.bulk_create(batch)
                processed += len(batch)

            job.region = result.region or ""
            job.counts = result.counts
            job.ignored_sheets = result.ignored_sheets
            job.issues = [warning.as_dict() for warning in result.warnings]
            job.status = ImportJobStatus.SUCCESS
            job.stage = ImportStage.DONE
            job.rows_processed = processed
            job.rows_total = result.row_count
            job.finished_at = timezone.now()
            job.save(
                update_fields=[
                    "region",
                    "counts",
                    "ignored_sheets",
                    "issues",
                    "status",
                    "stage",
                    "rows_processed",
                    "rows_total",
                    "finished_at",
                ]
            )
    except IntegrityError as exc:
        logger.exception(
            "ep_import.persist_rejected",
            extra={"job_id": str(job.id), "stage": ImportStage.PERSISTING, "error_code": "DUPLICATE_CELL"},
        )
        raise EpImportError(
            title="EP file has invalid rows",
            issues=[],
        ) from exc


def _progress(job: ImportJob, stage: str, processed: int, total: int | None) -> None:
    job.stage = stage
    job.rows_processed = processed
    if total is not None:
        job.rows_total = total
    job.save(update_fields=["stage", "rows_processed", "rows_total"])


def _fail(job: ImportJob, title: str, issues: list[dict], started: float, error_code: str) -> ImportJob:
    if not issues:
        issues = [unexpected_failure().as_dict()]
        if title == "EP file has invalid rows":
            issues = [
                {
                    "code": "DUPLICATE_CELL",
                    "message": "The file contains duplicate cells and was not imported.",
                    "sheet": None,
                    "column": None,
                    "row": None,
                    "severity": "error",
                }
            ]
    job.status = ImportJobStatus.FAILED
    job.stage = ImportStage.FAILED
    job.error_title = title or "Import error"
    job.issues = issues
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "stage", "error_title", "issues", "finished_at"])
    _log(job, "ep_import.failed", error_code=error_code, duration_ms=_elapsed(started))
    return job


def _log(job: ImportJob, event: str, **fields) -> None:
    logger.info(
        event,
        extra={
            "job_id": str(job.id),
            "correlation_id": str(job.id),
            "stage": job.stage,
            "user_id": getattr(job, "created_by_id", None),
            **fields,
        },
    )


def _elapsed(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
