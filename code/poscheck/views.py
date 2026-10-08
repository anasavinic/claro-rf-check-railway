from __future__ import annotations

import logging
from datetime import datetime

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET, require_POST

from ep_import.models import EpCell
from ep_import.services.scripts import (
    ep_cell_id_from_raw,
    first_selected_raw,
    generate_full_check_script,
    generate_precheck_script,
    script_fields_from_raw,
)
from poscheck.forms import PoscheckReturnUploadForm
from poscheck.services.errors import PoscheckError
from poscheck.services.orchestrator import get_poscheck_snapshot
from poscheck.services.returns import has_full_check_return, store_full_check_return
from precheck.models import CheckAnalysis, CheckAnalysisStatus, CheckExecutionStatus, CheckType, PrecheckResultStatus
from precheck.services.analysis import SESSION_ANALYSIS_KEY
from precheck.services.authorization import can_mutate_analysis, mutable_analysis, visible_analysis
from precheck.services.errors import PrecheckError
from precheck.services.execution import build_process_response, enqueue_check_execution
from precheck.services.returns import MAX_RETURN_UPLOAD_BYTES, has_precheck_return
from precheck.tasks import process_check_execution

logger = logging.getLogger("poscheck.views")

TECH_NAV = [
    ("2G", "2G"),
    ("3G", "3G"),
    ("4G", "4G"),
    ("5G", "5G NR"),
]


def _wants_json(request: HttpRequest) -> bool:
    accept = request.headers.get("Accept", "")
    return "application/json" in accept or request.headers.get("X-Requested-With") == "XMLHttpRequest"


def poscheck_login_required(view):
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated:
            return view(request, *args, **kwargs)
        if _wants_json(request):
            return JsonResponse(
                {
                    "type": "Error",
                    "title": "Authentication required",
                    "message": "Sign in to continue.",
                },
                status=401,
            )
        return redirect_to_login(request.get_full_path(), login_url=settings.LOGIN_URL)

    wrapper.__name__ = getattr(view, "__name__", "view")
    wrapper.__wrapped__ = view
    return wrapper


def _json_error(title: str, message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"type": "Error", "title": title, "message": message}, status=status)


def _current_analysis(request: HttpRequest) -> CheckAnalysis | None:
    return visible_analysis(request, request.session.get(SESSION_ANALYSIS_KEY))


def _current_mutable_analysis(request: HttpRequest) -> CheckAnalysis | None:
    return mutable_analysis(request, request.session.get(SESSION_ANALYSIS_KEY))


def _cell_ids_for_analysis(analysis: CheckAnalysis) -> list[str]:
    ids: list[str] = []
    cells = EpCell.objects.filter(
        job_id=analysis.ep_job_id,
        technology=analysis.technology,
        site_name=analysis.site_name,
        cell_name__in=analysis.selected_cells or [],
    )
    by_name = {cell.cell_name: cell for cell in cells}
    for name in analysis.selected_cells or []:
        cell = by_name.get(name)
        if not cell:
            continue
        value = ep_cell_id_from_raw(cell.raw, analysis.technology)
        if value:
            ids.append(value)
    return ids


def _full_check_script_for(analysis: CheckAnalysis) -> str:
    fields = script_fields_from_raw(
        analysis.technology,
        first_selected_raw(
            job_id=analysis.ep_job_id,
            technology=analysis.technology,
            site_name=analysis.site_name,
            cell_names=analysis.selected_cells or [],
        ),
    )
    return generate_full_check_script(
        analysis.technology,
        site_name=analysis.site_name,
        cell_names=analysis.selected_cells or [],
        cell_ids=_cell_ids_for_analysis(analysis),
        bsc=fields["bsc"],
        bts=fields["bts"],
        rnc=fields["rnc"],
        enodeb_id=fields["enodeb_id"],
    )


def _analysis_context(analysis: CheckAnalysis, *, can_mutate: bool = True) -> dict:
    precheck_file = analysis.return_files.filter(check_type=CheckType.PRECHECK).first()
    full_check_file = analysis.return_files.filter(check_type=CheckType.FULL_CHECK).first()
    terminal = analysis.status in {
        CheckAnalysisStatus.COMPLETED,
        CheckAnalysisStatus.INCONSISTENT,
        CheckAnalysisStatus.FAILED,
    }
    requires_pre = bool(analysis.pre_check)
    requires_full = bool(analysis.full_check)
    has_required = (not requires_pre or precheck_file is not None) and (
        not requires_full or full_check_file is not None
    )
    return {
        "analysis": analysis,
        "job": analysis.ep_job,
        "technology": analysis.technology,
        "tech_label": "5G NR" if analysis.technology == "5G" else analysis.technology,
        "active_nav": analysis.technology,
        "tech_nav": TECH_NAV,
        "site": analysis.site_name,
        "selected_cells": analysis.selected_cells,
        "selected_cells_count": len(analysis.selected_cells or []),
        "pre_check": analysis.pre_check,
        "full_check": analysis.full_check,
        "precheck_script": (
            generate_precheck_script(
                analysis.technology,
                site_name=analysis.site_name,
                cell_names=analysis.selected_cells or [],
            )
            if analysis.pre_check
            else ""
        ),
        "full_check_script": (_full_check_script_for(analysis) if analysis.full_check else ""),
        "precheck_return": precheck_file,
        "has_precheck_return": precheck_file is not None,
        "full_check_return": full_check_file,
        "has_full_check_return": full_check_file is not None,
        "can_mutate": can_mutate,
        "can_process": bool(can_mutate and has_required),
        "can_reanalyze": bool(can_mutate and requires_full and terminal),
        "max_return_mb": MAX_RETURN_UPLOAD_BYTES // (1024 * 1024),
        "upload_precheck_url": (
            reverse("precheck:upload_precheck_return", kwargs={"technology": analysis.technology})
            if can_mutate and analysis.pre_check
            else ""
        ),
        "upload_full_check_url": (
            reverse("poscheck:upload_full_check_return") if can_mutate and analysis.full_check else ""
        ),
        "process_url": reverse("poscheck:process") if can_mutate else "",
        "import_returns_url": reverse("precheck:import_returns", kwargs={"technology": analysis.technology}),
        "config_url": (
            reverse("ep_import:site_cells", kwargs={"technology": analysis.technology}) + f"?job={analysis.ep_job_id}"
        ),
        "export_url": reverse("reports:export", kwargs={"analysis_id": analysis.id}),
        "email_url": reverse("reports:email", kwargs={"analysis_id": analysis.id}),
    }


@poscheck_login_required
@require_POST
def upload_full_check_return(request: HttpRequest) -> HttpResponse:
    analysis = _current_mutable_analysis(request)
    if analysis is None:
        viewed = _current_analysis(request)
        if viewed is not None and viewed.full_check:
            return _json_error(
                "Upload error",
                "You do not have permission to modify this analysis.",
                status=403,
            )
        return _json_error("Upload error", "No active Full Check analysis was found.")

    if not analysis.full_check:
        return _json_error("Upload error", "No active Full Check analysis was found.")

    form = PoscheckReturnUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        message = next(iter(form.errors.values()))[0] if form.errors else "Invalid upload."
        return _json_error("Upload error", str(message))

    try:
        stored = store_full_check_return(analysis, form.cleaned_data["file"])
    except PoscheckError as exc:
        status = 409 if exc.code == "ANALYSIS_BUSY" else 400
        return _json_error(exc.title, exc.issues[0].message if exc.issues else str(exc), status=status)
    except Exception:
        logger.exception("Full Check return upload failed")
        return _json_error("Upload error", "Could not upload the return file. Try again.", status=500)

    analysis.refresh_from_db()
    can_process = (not analysis.pre_check or has_precheck_return(analysis)) and has_full_check_return(analysis)
    return JsonResponse(
        {
            "type": "Success",
            "title": "Return imported",
            "message": "Full Check result file uploaded successfully.",
            "filename": stored.original_filename,
            "can_process": can_process,
            "status": analysis.status,
        }
    )


@poscheck_login_required
@require_POST
def process(request: HttpRequest) -> HttpResponse:
    analysis = _current_mutable_analysis(request)
    if analysis is None:
        viewed = _current_analysis(request)
        if viewed is not None and viewed.full_check:
            return _json_error(
                "Could not process",
                "You do not have permission to modify this analysis.",
                status=403,
            )
        return _json_error("Could not process", "No active Full Check analysis was found.")

    if not analysis.full_check:
        return _json_error("Could not process", "No active Full Check analysis was found.")

    if not has_full_check_return(analysis):
        return _json_error("Could not process", "Import the Full Check result file before processing.")
    if analysis.pre_check and not has_precheck_return(analysis):
        return _json_error("Could not process", "Import the Pre-check result file before processing.")

    try:
        execution, created = enqueue_check_execution(analysis, user=request.user)
        if created or (execution.status == CheckExecutionStatus.PENDING and not execution.task_id):
            process_check_execution.delay(str(execution.id))
        execution.refresh_from_db()
    except (PrecheckError, PoscheckError) as exc:
        status = 409 if getattr(exc, "code", "") == "ANALYSIS_BUSY" else 400
        issues = getattr(exc, "issues", None) or []
        message = issues[0].message if issues else str(exc)
        return _json_error(exc.title, message, status=status)
    except PermissionDenied:
        return _json_error("Could not process", "You do not have permission to modify this analysis.", status=403)

    payload, status_code = build_process_response(execution, created=created)
    return JsonResponse(payload, status=status_code)


def _format_processed_at(value: str | None) -> str:
    if not value:
        return "—"
    parsed = parse_datetime(value)
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    if timezone.is_aware(parsed):
        parsed = timezone.localtime(parsed)
    return parsed.strftime("%m/%d/%Y %H:%M")


def _display_snapshot(snapshot: dict) -> dict:
    display = dict(snapshot)
    display["processed_at"] = _format_processed_at(snapshot.get("processed_at"))
    return display


@poscheck_login_required
@require_GET
def result(request: HttpRequest) -> HttpResponse:
    analysis = _current_analysis(request)
    if not analysis or not analysis.full_check:
        return redirect(reverse("ep_import:site_cells", kwargs={"technology": "5G"}))

    snapshot = get_poscheck_snapshot(analysis.id)
    if not snapshot:
        return redirect(reverse("precheck:import_returns", kwargs={"technology": analysis.technology}))
    if snapshot["status"] == PrecheckResultStatus.EXECUTION_FAILURE:
        return redirect(reverse("poscheck:failure"))

    can_mutate = can_mutate_analysis(request.user, analysis)
    context = {
        **_analysis_context(analysis, can_mutate=can_mutate),
        "snapshot": _display_snapshot(snapshot),
        "is_inconsistent": snapshot["status"] == PrecheckResultStatus.INCONSISTENT,
        "active_result_tab": "full_check",
    }
    return render(request, "poscheck/result.html", context)


@poscheck_login_required
@require_GET
def failure(request: HttpRequest) -> HttpResponse:
    analysis = _current_analysis(request)
    if not analysis or not analysis.full_check:
        return redirect(reverse("ep_import:site_cells", kwargs={"technology": "5G"}))

    snapshot = get_poscheck_snapshot(analysis.id)
    if not snapshot:
        return redirect(reverse("precheck:import_returns", kwargs={"technology": analysis.technology}))
    if snapshot["status"] != PrecheckResultStatus.EXECUTION_FAILURE:
        return redirect(reverse("poscheck:result"))

    can_mutate = can_mutate_analysis(request.user, analysis)
    context = {
        **_analysis_context(analysis, can_mutate=can_mutate),
        "snapshot": _display_snapshot(snapshot),
        "run_again_url": reverse("poscheck:process") if can_mutate else "",
    }
    return render(request, "poscheck/failure.html", context)
