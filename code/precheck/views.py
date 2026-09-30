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
from ep_import.services.scripts import ep_cell_id_from_raw, generate_full_check_script, generate_precheck_script
from poscheck.services.orchestrator import get_poscheck_snapshot
from poscheck.services.returns import has_full_check_return
from precheck.forms import PrecheckReturnUploadForm
from precheck.models import (
    CheckAnalysis,
    CheckAnalysisStatus,
    CheckExecution,
    CheckExecutionStatus,
    CheckType,
    PrecheckResultStatus,
)
from precheck.services.analysis import SESSION_ANALYSIS_KEY
from precheck.services.authorization import can_mutate_analysis, mutable_analysis, visible_analysis
from precheck.services.errors import PrecheckError
from precheck.services.execution import (
    build_process_response,
    enqueue_check_execution,
    execution_status_payload,
)
from precheck.services.returns import MAX_RETURN_UPLOAD_BYTES, has_precheck_return, store_precheck_return
from precheck.services.validator import get_precheck_snapshot
from precheck.tasks import process_check_execution

logger = logging.getLogger("precheck.views")

TECH_NAV = [
    ("2G", "2G"),
    ("3G", "3G"),
    ("4G", "4G"),
    ("5G", "5G NR"),
]


def _wants_json(request: HttpRequest) -> bool:
    accept = request.headers.get("Accept", "")
    return "application/json" in accept or request.headers.get("X-Requested-With") == "XMLHttpRequest"


def precheck_login_required(view):
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


def _supports_returns(analysis: CheckAnalysis) -> bool:
    return bool(analysis.pre_check or analysis.full_check)


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


def _bsc_for_analysis(analysis: CheckAnalysis) -> str:
    if analysis.technology != "2G":
        return ""
    cell = (
        EpCell.objects.filter(
            job_id=analysis.ep_job_id,
            technology=analysis.technology,
            site_name=analysis.site_name,
            cell_name__in=analysis.selected_cells or [],
        )
        .order_by("cell_name")
        .first()
    )
    if cell is None:
        return ""
    return str((cell.raw or {}).get("BSC") or "").strip()


def _enodeb_id_for_analysis(analysis: CheckAnalysis) -> str:
    if analysis.technology != "4G":
        return ""
    cell = (
        EpCell.objects.filter(
            job_id=analysis.ep_job_id,
            technology=analysis.technology,
            site_name=analysis.site_name,
            cell_name__in=analysis.selected_cells or [],
        )
        .order_by("cell_name")
        .first()
    )
    if cell is None:
        return ""
    value = (cell.raw or {}).get("ENODEB ID")
    if value is None:
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


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
        "full_check_script": (
            generate_full_check_script(
                analysis.technology,
                site_name=analysis.site_name,
                cell_names=analysis.selected_cells or [],
                cell_ids=_cell_ids_for_analysis(analysis),
                bsc=_bsc_for_analysis(analysis),
                bts=analysis.site_name,
                enodeb_id=_enodeb_id_for_analysis(analysis),
            )
            if analysis.full_check
            else ""
        ),
        "precheck_return": precheck_file,
        "has_precheck_return": precheck_file is not None,
        "full_check_return": full_check_file,
        "has_full_check_return": full_check_file is not None,
        "can_mutate": can_mutate,
        "can_process": bool(can_mutate and has_required),
        "can_reanalyze": bool(can_mutate and _supports_returns(analysis) and terminal),
        "max_return_mb": MAX_RETURN_UPLOAD_BYTES // (1024 * 1024),
        "upload_precheck_url": (
            reverse("precheck:upload_precheck_return", kwargs={"technology": analysis.technology})
            if can_mutate and analysis.pre_check
            else ""
        ),
        "upload_full_check_url": (
            reverse("poscheck:upload_full_check_return") if can_mutate and analysis.full_check else ""
        ),
        "process_url": reverse("precheck:process", kwargs={"technology": analysis.technology}) if can_mutate else "",
        "import_returns_url": reverse("precheck:import_returns", kwargs={"technology": analysis.technology}),
        "config_url": (
            reverse("ep_import:site_cells", kwargs={"technology": analysis.technology}) + f"?job={analysis.ep_job_id}"
        ),
        "export_url": reverse("reports:export", kwargs={"analysis_id": analysis.id}),
        "email_url": reverse("reports:email", kwargs={"analysis_id": analysis.id}),
    }


@precheck_login_required
@require_GET
def import_returns(request: HttpRequest, technology: str = "5G") -> HttpResponse:
    analysis = _current_analysis(request)
    if not analysis or not _supports_returns(analysis):
        return redirect(reverse("ep_import:site_cells", kwargs={"technology": technology or "5G"}))
    can_mutate = can_mutate_analysis(request.user, analysis)
    return render(request, "precheck/import_returns.html", _analysis_context(analysis, can_mutate=can_mutate))


@precheck_login_required
@require_POST
def upload_precheck_return(request: HttpRequest, technology: str = "5G") -> HttpResponse:
    analysis = _current_mutable_analysis(request)
    if analysis is None:
        viewed = _current_analysis(request)
        if viewed is not None and viewed.pre_check:
            return _json_error(
                "Upload error",
                "You do not have permission to modify this analysis.",
                status=403,
            )
        return _json_error("Upload error", "No active pre-check analysis was found.")

    if not analysis.pre_check:
        return _json_error("Upload error", "No active pre-check analysis was found.")

    form = PrecheckReturnUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        message = next(iter(form.errors.values()))[0] if form.errors else "Invalid upload."
        return _json_error("Upload error", str(message))

    try:
        stored = store_precheck_return(analysis, form.cleaned_data["file"])
    except PrecheckError as exc:
        status = 409 if exc.code == "ANALYSIS_BUSY" else 400
        return _json_error(exc.title, exc.issues[0].message if exc.issues else str(exc), status=status)
    except Exception:
        logger.exception("Pre-check return upload failed")
        return _json_error("Upload error", "Could not upload the return file. Try again.", status=500)

    analysis.refresh_from_db()
    can_process = has_precheck_return(analysis) and (not analysis.full_check or has_full_check_return(analysis))
    return JsonResponse(
        {
            "type": "Success",
            "title": "Return imported",
            "message": "Pre-check result file uploaded successfully.",
            "filename": stored.original_filename,
            "can_process": can_process,
            "status": analysis.status,
        }
    )


@precheck_login_required
@require_POST
def process(request: HttpRequest, technology: str = "5G") -> HttpResponse:
    analysis = _current_mutable_analysis(request)
    if analysis is None:
        viewed = _current_analysis(request)
        if viewed is not None and _supports_returns(viewed):
            return _json_error(
                "Could not process",
                "You do not have permission to modify this analysis.",
                status=403,
            )
        return _json_error("Could not process", "No active check analysis was found.")

    if not _supports_returns(analysis):
        return _json_error("Could not process", "No active check analysis was found.")

    if analysis.pre_check and not has_precheck_return(analysis):
        return _json_error("Could not process", "Import the Pre-check result file before processing.")
    if analysis.full_check and not has_full_check_return(analysis):
        return _json_error("Could not process", "Import the Full Check result file before processing.")

    try:
        execution, created = enqueue_check_execution(analysis, user=request.user)
        if created or (execution.status == CheckExecutionStatus.PENDING and not execution.task_id):
            process_check_execution.delay(str(execution.id))
        execution.refresh_from_db()
    except PrecheckError as exc:
        status_code = 409 if exc.code == "ANALYSIS_BUSY" else 400
        return _json_error(exc.title, exc.issues[0].message if exc.issues else str(exc), status=status_code)
    except PermissionDenied:
        return _json_error("Could not process", "You do not have permission to modify this analysis.", status=403)

    return _execution_process_response(execution, created=created)


@precheck_login_required
@require_GET
def execution_status(request: HttpRequest, execution_id) -> HttpResponse:
    try:
        execution = CheckExecution.objects.select_related("analysis").get(pk=execution_id)
    except CheckExecution.DoesNotExist:
        return _json_error("Not found", "Execution was not found.", status=404)

    analysis = visible_analysis(request, execution.analysis_id)
    if analysis is None:
        return _json_error("Not found", "Execution was not found.", status=404)

    return JsonResponse(
        {
            "type": "Success",
            "execution": execution_status_payload(execution),
            "status_url": reverse("precheck:execution_status", kwargs={"execution_id": execution.id}),
            "redirect_url": execution.redirect_url or "",
        }
    )


def _execution_process_response(execution: CheckExecution, *, created: bool) -> JsonResponse:
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


@precheck_login_required
@require_GET
def result(request: HttpRequest, technology: str = "5G") -> HttpResponse:
    analysis = _current_analysis(request)
    if not analysis or not analysis.pre_check:
        return redirect(reverse("ep_import:site_cells", kwargs={"technology": technology or "5G"}))

    snapshot = get_precheck_snapshot(analysis.id)
    if not snapshot:
        return redirect(reverse("precheck:import_returns", kwargs={"technology": analysis.technology}))
    if snapshot["status"] == PrecheckResultStatus.EXECUTION_FAILURE:
        return redirect(reverse("precheck:failure", kwargs={"technology": analysis.technology}))

    can_mutate = can_mutate_analysis(request.user, analysis)
    pos_snapshot = get_poscheck_snapshot(analysis.id) if analysis.full_check else None
    context = {
        **_analysis_context(analysis, can_mutate=can_mutate),
        "snapshot": _display_snapshot(snapshot),
        "is_inconsistent": snapshot["status"] == PrecheckResultStatus.INCONSISTENT,
        "has_poscheck_result": pos_snapshot is not None
        and pos_snapshot["status"] != PrecheckResultStatus.EXECUTION_FAILURE,
    }
    return render(request, "precheck/result.html", context)


@precheck_login_required
@require_GET
def failure(request: HttpRequest, technology: str = "5G") -> HttpResponse:
    analysis = _current_analysis(request)
    if not analysis or not analysis.pre_check:
        return redirect(reverse("ep_import:site_cells", kwargs={"technology": technology or "5G"}))

    snapshot = get_precheck_snapshot(analysis.id)
    if not snapshot:
        return redirect(reverse("precheck:import_returns", kwargs={"technology": analysis.technology}))
    if snapshot["status"] != PrecheckResultStatus.EXECUTION_FAILURE:
        return redirect(reverse("precheck:result", kwargs={"technology": analysis.technology}))

    can_mutate = can_mutate_analysis(request.user, analysis)
    context = {
        **_analysis_context(analysis, can_mutate=can_mutate),
        "snapshot": _display_snapshot(snapshot),
        "run_again_url": reverse("precheck:process", kwargs={"technology": analysis.technology}) if can_mutate else "",
    }
    return render(request, "precheck/failure.html", context)
