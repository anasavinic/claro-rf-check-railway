"""Access scope for check analyses: view vs mutate, owner-scoped."""

from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpRequest

from ep_import.services.authorization import can_mutate_job, can_view_job
from precheck.models import CheckAnalysis


def can_view_analysis(user, analysis: CheckAnalysis) -> bool:
    """Owner of the analysis, or staff who can view the linked EP job."""
    if not getattr(user, "is_authenticated", False):
        return False
    if analysis.created_by_id is not None and analysis.created_by_id == user.pk:
        return True
    if analysis.created_by_id is None and can_mutate_job(user, analysis.ep_job):
        return True
    return can_view_job(user, analysis.ep_job)


def can_mutate_analysis(user, analysis: CheckAnalysis) -> bool:
    """Only the analysis owner (or superuser) may upload returns or process."""
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    if analysis.created_by_id is not None:
        return analysis.created_by_id == user.pk
    return can_mutate_job(user, analysis.ep_job)


def can_access_analysis(user, analysis: CheckAnalysis) -> bool:
    """Backward-compatible alias for view access."""
    return can_view_analysis(user, analysis)


def get_authorized_analysis(request: HttpRequest, analysis_id) -> CheckAnalysis:
    try:
        analysis = CheckAnalysis.objects.select_related("ep_job").filter(pk=analysis_id).first()
    except (ValidationError, ValueError, TypeError):
        analysis = None
    if analysis is None or not can_view_analysis(request.user, analysis):
        raise Http404("Check analysis not found.")
    return analysis


def get_mutable_analysis(request: HttpRequest, analysis_id) -> CheckAnalysis:
    try:
        analysis = CheckAnalysis.objects.select_related("ep_job").filter(pk=analysis_id).first()
    except (ValidationError, ValueError, TypeError):
        analysis = None
    if analysis is None or not can_view_analysis(request.user, analysis):
        raise Http404("Check analysis not found.")
    if not can_mutate_analysis(request.user, analysis):
        raise PermissionDenied("You do not have permission to modify this analysis.")
    return analysis


def visible_analysis(request: HttpRequest, analysis_id) -> CheckAnalysis | None:
    if not analysis_id:
        return None
    try:
        analysis = CheckAnalysis.objects.select_related("ep_job").filter(pk=analysis_id).first()
    except (ValidationError, ValueError, TypeError):
        return None
    if analysis is None or not can_view_analysis(request.user, analysis):
        return None
    return analysis


def mutable_analysis(request: HttpRequest, analysis_id) -> CheckAnalysis | None:
    analysis = visible_analysis(request, analysis_id)
    if analysis is None or not can_mutate_analysis(request.user, analysis):
        return None
    return analysis
