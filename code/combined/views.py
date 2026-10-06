"""Views for Combined RF Check (multi-technology flow)."""

from __future__ import annotations

import json

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from combined.services.authorization import can_mutate_combined, mutable_combined, visible_combined
from combined.services.combined import (
    SESSION_COMBINED_KEY,
    TECH_OPTIONS,
    attach_ep_job,
    build_scripts,
    create_combined_check,
    materialize_analyses,
    set_sites,
    sites_across_technologies,
    tech_label,
    total_cells,
)
from combined.services.execution import combined_process_status, enqueue_combined_execution, recover_stuck_analyses
from combined.services.results import build_combined_result, failure_reasons, has_comparable_results
from combined.services.returns import (
    combined_return_ready,
    returns_board,
    store_combined_full_check_return,
    store_combined_precheck_return,
)
from ep_import.models import ImportJobStatus
from ep_import.services.authorization import visible_job
from poscheck.services.errors import PoscheckError
from precheck.models import CheckAnalysisStatus, CombinedCheck
from precheck.services.errors import PrecheckError

TECH_NAV = [
    ("2G", "2G"),
    ("3G", "3G"),
    ("4G", "4G"),
    ("5G", "5G NR"),
]


def _wants_json(request: HttpRequest) -> bool:
    accept = request.headers.get("Accept", "")
    return "application/json" in accept or request.headers.get("X-Requested-With") == "XMLHttpRequest"


def combined_login_required(view):
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


def _json_error(title: str, message: str, *, status: int = 400) -> JsonResponse:
    return JsonResponse({"type": "Error", "title": title, "message": message}, status=status)


def _current_combined(request: HttpRequest) -> CombinedCheck | None:
    return visible_combined(request, request.session.get(SESSION_COMBINED_KEY))


def _current_mutable(request: HttpRequest) -> CombinedCheck | None:
    return mutable_combined(request, request.session.get(SESSION_COMBINED_KEY))


def _base_context(combined: CombinedCheck | None = None) -> dict:
    return {
        "active_nav": "combined",
        "tech_nav": TECH_NAV,
        "tech_options": TECH_OPTIONS,
        "combined": combined,
    }


def _summary_context(combined: CombinedCheck) -> dict:
    techs = combined.technologies or []
    return {
        "technologies": techs,
        "tech_labels": [tech_label(t) for t in techs],
        "tech_summary": ", ".join(tech_label(t) for t in techs) or "--",
        "site_names": combined.site_names or [],
        "site_count": len(combined.site_names or []),
        "cell_count": total_cells(combined) if combined.analyses.exists() else 0,
        "pre_check": combined.pre_check,
        "full_check": combined.full_check,
        "status": combined.status,
    }


@combined_login_required
@require_GET
def configure(request: HttpRequest) -> HttpResponse:
    combined = _current_combined(request)
    selected = list(combined.technologies) if combined and combined.technologies else []
    return render(
        request,
        "combined/configure.html",
        {
            **_base_context(combined),
            "selected_technologies": selected,
            "selected_technologies_json": json.dumps(selected),
            "step": "configure",
            **(
                _summary_context(combined)
                if combined
                else {
                    "tech_summary": ", ".join(tech_label(t) for t in selected),
                    "site_count": 0,
                    "cell_count": 0,
                }
            ),
        },
    )


@combined_login_required
@require_POST
def save_configure(request: HttpRequest) -> HttpResponse:
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return _json_error("Could not save", "Invalid request body.")

    technologies = data.get("technologies") or []
    try:
        combined = create_combined_check(user=request.user, technologies=technologies)
    except ValueError as exc:
        return _json_error("Could not save", str(exc))

    request.session[SESSION_COMBINED_KEY] = str(combined.id)
    return JsonResponse(
        {
            "type": "Success",
            "combined_id": str(combined.id),
            "redirect_url": reverse("combined:sites"),
        }
    )


@combined_login_required
@require_GET
def sites(request: HttpRequest) -> HttpResponse:
    combined = _current_combined(request)
    if combined is None or len(combined.technologies or []) < 2:
        return redirect(reverse("combined:configure"))

    job = None
    job_id = request.GET.get("job") or request.session.get("ep_import_job_id")
    if job_id:
        job = visible_job(request, job_id)
    if job is None and combined.ep_job_id:
        job = visible_job(request, combined.ep_job_id)

    if job is not None and combined.ep_job_id != job.id and can_mutate_combined(request.user, combined):
        attach_ep_job(combined, job)
        combined.refresh_from_db()

    site_rows: list[dict] = []
    if job and job.status == ImportJobStatus.SUCCESS:
        site_rows = sites_across_technologies(job, combined.technologies or [])

    return render(
        request,
        "combined/sites.html",
        {
            **_base_context(combined),
            **_summary_context(combined),
            "step": "sites",
            "job": job,
            "sites": site_rows,
            "selected_sites": combined.site_names or [],
            "selected_sites_json": json.dumps(combined.site_names or []),
            "upload_url": reverse("ep_import:upload"),
            "generate_url": reverse("combined:generate_scripts"),
            "polling": bool(job and job.status in {ImportJobStatus.PENDING, ImportJobStatus.PROCESSING}),
        },
    )


@combined_login_required
@require_POST
def generate_scripts(request: HttpRequest) -> HttpResponse:
    combined = _current_mutable(request)
    if combined is None:
        return _json_error("Could not generate scripts", "No active combined check was found.")

    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return _json_error("Could not generate scripts", "Invalid request body.")

    site_names = data.get("sites") or data.get("site_names") or []
    job_id = data.get("job_id") or request.session.get("ep_import_job_id")
    if job_id:
        job = visible_job(request, job_id)
        if job is None:
            return _json_error("Could not generate scripts", "EP import job was not found.")
        if job.status != ImportJobStatus.SUCCESS:
            return _json_error("Could not generate scripts", "Wait until the EP import finishes.")
        attach_ep_job(combined, job)

    try:
        set_sites(combined, site_names)
        materialize_analyses(combined)
    except ValueError as exc:
        return _json_error("Could not generate scripts", str(exc))

    request.session[SESSION_COMBINED_KEY] = str(combined.id)
    return JsonResponse(
        {
            "type": "Success",
            "combined_id": str(combined.id),
            "redirect_url": reverse("combined:scripts"),
        }
    )


@combined_login_required
@require_GET
def scripts(request: HttpRequest) -> HttpResponse:
    combined = _current_combined(request)
    if combined is None or not combined.analyses.exists():
        return redirect(reverse("combined:configure"))

    can_mutate = can_mutate_combined(request.user, combined)
    if can_mutate:
        recover_stuck_analyses(combined)
        combined.refresh_from_db()

    scripts_payload = build_scripts(combined)
    board = returns_board(combined)
    ready = combined_return_ready(combined)
    script_cards = []
    for tech, payload in scripts_payload["by_technology"].items():
        script_cards.append(
            {
                "technology": tech,
                "label": payload["label"],
                "precheck_script": payload["precheck_script"],
                "full_check_script": payload["full_check_script"],
                "download_precheck_url": (
                    reverse("combined:download_script", kwargs={"check_type": "precheck"}) + f"?technology={tech}"
                ),
                "download_full_check_url": (
                    reverse("combined:download_script", kwargs={"check_type": "full-check"}) + f"?technology={tech}"
                ),
            }
        )
    script_cards.sort(key=lambda item: ["2G", "3G", "4G", "5G"].index(item["technology"]))

    return render(
        request,
        "combined/scripts.html",
        {
            **_base_context(combined),
            **_summary_context(combined),
            "step": "scripts",
            "script_cards": script_cards,
            "returns_board": board,
            "pre_check": combined.pre_check,
            "full_check": combined.full_check,
            "can_import": can_mutate,
            "can_process": can_mutate and ready,
            "upload_precheck_url": reverse("combined:upload_precheck") if can_mutate else "",
            "upload_full_check_url": reverse("combined:upload_full_check") if can_mutate else "",
            "process_url": reverse("combined:process") if can_mutate else "",
        },
    )


@combined_login_required
@require_GET
def download_script(request: HttpRequest, check_type: str) -> HttpResponse:
    combined = _current_combined(request)
    if combined is None or not combined.analyses.exists():
        return redirect(reverse("combined:configure"))

    scripts_payload = build_scripts(combined)
    technology = (request.GET.get("technology") or "").upper().strip()
    if technology == "5G NR":
        technology = "5G"

    if technology and technology in scripts_payload["by_technology"]:
        bucket = scripts_payload["by_technology"][technology]
        if check_type == "precheck" and bucket["precheck_script"]:
            content = bucket["precheck_script"]
            filename = f"Claro_RF_Check_Combined_PreCheck_{technology}.txt"
        elif check_type == "full-check" and bucket["full_check_script"]:
            content = bucket["full_check_script"]
            filename = f"Claro_RF_Check_Combined_FullCheck_{technology}.txt"
        else:
            return _json_error("Not found", "The requested check type is not part of the selection.", status=404)
    elif check_type == "precheck" and combined.pre_check:
        content = scripts_payload["precheck_script"]
        filename = "Claro_RF_Check_Combined_PreCheck.txt"
    elif check_type == "full-check" and combined.full_check:
        content = scripts_payload["full_check_script"]
        filename = "Claro_RF_Check_Combined_FullCheck.txt"
    else:
        return _json_error("Not found", "The requested check type is not part of the selection.", status=404)

    response = HttpResponse(content, content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@combined_login_required
@require_POST
def upload_precheck(request: HttpRequest) -> HttpResponse:
    combined = _current_mutable(request)
    if combined is None:
        return _json_error("Upload error", "No active combined check was found.")
    uploaded = request.FILES.get("file")
    if uploaded is None:
        return _json_error("Upload error", "Select a return file to upload.")
    try:
        count = store_combined_precheck_return(combined, uploaded)
    except PrecheckError as exc:
        return _json_error(exc.title, exc.issues[0].message if exc.issues else str(exc))
    board = returns_board(combined)
    return JsonResponse(
        {
            "type": "Success",
            "title": "Pre-check return imported",
            "message": f"Return attached to {count} analysis(es).",
            "filename": uploaded.name,
            "technology": "5G",
            "check_type": "precheck",
            "returns_board": board,
            "can_process": combined_return_ready(combined),
        }
    )


@combined_login_required
@require_POST
def upload_full_check(request: HttpRequest) -> HttpResponse:
    combined = _current_mutable(request)
    if combined is None:
        return _json_error("Upload error", "No active combined check was found.")
    uploaded = request.FILES.get("file")
    if uploaded is None:
        return _json_error("Upload error", "Select a return file to upload.")
    technology = (request.POST.get("technology") or "").strip()
    if not technology:
        return _json_error("Upload error", "Select which technology this Full Check return belongs to.")
    try:
        count = store_combined_full_check_return(combined, uploaded, technology=technology)
    except (PrecheckError, PoscheckError) as exc:
        message = exc.issues[0].message if getattr(exc, "issues", None) else str(exc)
        title = getattr(exc, "title", "Upload error")
        return _json_error(title, message)
    board = returns_board(combined)
    return JsonResponse(
        {
            "type": "Success",
            "title": f"Full Check return imported ({tech_label(technology.upper())})",
            "message": f"Return attached to {count} analysis(es).",
            "filename": uploaded.name,
            "technology": technology.upper(),
            "check_type": "full_check",
            "returns_board": board,
            "can_process": combined_return_ready(combined),
        }
    )


@combined_login_required
@require_POST
def process(request: HttpRequest) -> HttpResponse:
    combined = _current_mutable(request)
    if combined is None:
        return _json_error("Could not process", "No active combined check was found.", status=403)

    try:
        enqueue_combined_execution(combined, user=request.user)
    except PrecheckError as exc:
        status_code = 409 if exc.code == "ANALYSIS_BUSY" else 400
        return _json_error(exc.title, exc.issues[0].message if exc.issues else str(exc), status=status_code)
    except PermissionDenied:
        return _json_error("Could not process", "You do not have permission to modify this analysis.", status=403)

    status_url = reverse("combined:process_status")
    return JsonResponse(
        {
            "type": "Success",
            "title": "Processing started",
            "message": "Combined check is being processed.",
            "status_url": status_url,
            "redirect_url": "",
        },
        status=202,
    )


@combined_login_required
@require_GET
def process_status(request: HttpRequest) -> HttpResponse:
    combined = _current_combined(request)
    if combined is None:
        return _json_error("Not found", "Combined check was not found.", status=404)
    payload = combined_process_status(combined)
    http_status = 200 if payload["finished"] else 202
    return JsonResponse({"type": "Success", **payload}, status=http_status)


@combined_login_required
@require_GET
def result(request: HttpRequest) -> HttpResponse:
    combined = _current_combined(request)
    if combined is None or not combined.analyses.exists():
        return redirect(reverse("combined:configure"))

    if combined.status not in {
        CheckAnalysisStatus.COMPLETED,
        CheckAnalysisStatus.INCONSISTENT,
        CheckAnalysisStatus.FAILED,
    }:
        # Still allow viewing partial results if any child finished
        if not any(
            a.status
            in {
                CheckAnalysisStatus.COMPLETED,
                CheckAnalysisStatus.INCONSISTENT,
                CheckAnalysisStatus.FAILED,
            }
            for a in combined.analyses.all()
        ):
            return redirect(reverse("combined:scripts"))

    snapshot = build_combined_result(combined)
    if snapshot["is_failed"] and not snapshot["has_pre_results"] and not snapshot["has_full_results"]:
        return redirect(reverse("combined:failure"))

    return render(
        request,
        "combined/result.html",
        {
            **_base_context(combined),
            **_summary_context(combined),
            "step": "result",
            "snapshot": snapshot,
            "export_url": reverse("reports:combined_export"),
            "email_url": reverse("reports:combined_email"),
        },
    )


@combined_login_required
@require_GET
def failure(request: HttpRequest) -> HttpResponse:
    combined = _current_combined(request)
    if combined is None:
        return redirect(reverse("combined:configure"))
    if has_comparable_results(combined):
        return redirect(reverse("combined:result"))
    return render(
        request,
        "combined/failure.html",
        {
            **_base_context(combined),
            **_summary_context(combined),
            "step": "result",
            "process_url": reverse("combined:process"),
            "failure_reasons": failure_reasons(combined),
        },
    )
