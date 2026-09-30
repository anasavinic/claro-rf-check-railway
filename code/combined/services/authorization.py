"""Authorization helpers for Combined RF checks."""

from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpRequest

from ep_import.services.authorization import can_mutate_job, can_view_job
from precheck.models import CombinedCheck


def can_view_combined(user, combined: CombinedCheck) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if combined.created_by_id is not None and combined.created_by_id == user.pk:
        return True
    if combined.ep_job_id is None:
        return combined.created_by_id is None or combined.created_by_id == user.pk
    if combined.created_by_id is None and can_mutate_job(user, combined.ep_job):
        return True
    return can_view_job(user, combined.ep_job)


def can_mutate_combined(user, combined: CombinedCheck) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    if combined.created_by_id is not None:
        return combined.created_by_id == user.pk
    if combined.ep_job_id is not None:
        return can_mutate_job(user, combined.ep_job)
    return True


def visible_combined(request: HttpRequest, combined_id) -> CombinedCheck | None:
    if not combined_id:
        return None
    try:
        combined = CombinedCheck.objects.select_related("ep_job").filter(pk=combined_id).first()
    except (ValidationError, ValueError, TypeError):
        return None
    if combined is None or not can_view_combined(request.user, combined):
        return None
    return combined


def mutable_combined(request: HttpRequest, combined_id) -> CombinedCheck | None:
    combined = visible_combined(request, combined_id)
    if combined is None or not can_mutate_combined(request.user, combined):
        return None
    return combined


def get_mutable_combined(request: HttpRequest, combined_id) -> CombinedCheck:
    combined = mutable_combined(request, combined_id)
    if combined is None:
        viewed = visible_combined(request, combined_id)
        if viewed is not None:
            raise PermissionDenied("You do not have permission to modify this combined check.")
        raise Http404("Combined check not found.")
    return combined
