"""Local access scope for EP imports: view vs mutate."""

from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpRequest

from ep_import.models import ImportJob


def can_view_job(user, job: ImportJob) -> bool:
    """Owner or staff may consult a job. View does not imply mutate."""
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_staff or user.is_superuser:
        return True
    return job.created_by_id is not None and job.created_by_id == user.pk


def can_mutate_job(user, job: ImportJob) -> bool:
    """Only the job owner (or superuser) may change a job or start analyses on it."""
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    return job.created_by_id is not None and job.created_by_id == user.pk


def can_access_job(user, job: ImportJob) -> bool:
    """Backward-compatible alias for view access."""
    return can_view_job(user, job)


def get_authorized_job(request: HttpRequest, job_id) -> ImportJob:
    """Return the job for view access, or 404. Foreign UUIDs must not confirm existence."""
    try:
        job = ImportJob.objects.filter(pk=job_id).first()
    except (ValidationError, ValueError, TypeError):
        job = None
    if job is None or not can_view_job(request.user, job):
        raise Http404("EP import not found.")
    return job


def get_mutable_job(request: HttpRequest, job_id) -> ImportJob:
    """Return the job for mutation, or 404/403. Viewers cannot mutate."""
    try:
        job = ImportJob.objects.filter(pk=job_id).first()
    except (ValidationError, ValueError, TypeError):
        job = None
    if job is None or not can_view_job(request.user, job):
        raise Http404("EP import not found.")
    if not can_mutate_job(request.user, job):
        raise PermissionDenied("You do not have permission to modify this EP import.")
    return job


def visible_job(request: HttpRequest, job_id) -> ImportJob | None:
    if not job_id:
        return None
    try:
        job = ImportJob.objects.filter(pk=job_id).first()
    except (ValidationError, ValueError, TypeError):
        return None
    if job is None or not can_view_job(request.user, job):
        return None
    return job


def mutable_job(request: HttpRequest, job_id) -> ImportJob | None:
    """Job visible to the user and owned for mutation; None otherwise."""
    job = visible_job(request, job_id)
    if job is None or not can_mutate_job(request.user, job):
        return None
    return job
