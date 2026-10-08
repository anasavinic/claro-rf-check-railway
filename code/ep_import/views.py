from __future__ import annotations

import json

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from ep_import.forms import EpUploadForm
from ep_import.models import EpCell, ImportJob, ImportJobStatus
from ep_import.schema import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, MAX_UPLOAD_BYTES, Technology
from ep_import.services.authorization import can_mutate_job, get_authorized_job, mutable_job, visible_job
from ep_import.services.content import sha256_file
from ep_import.services.queries import cell_search, sites_page
from ep_import.services.scripts import (
    FULL_CHECK_ONLY_TECHNOLOGIES,
    ep_cell_id_from_raw,
    first_selected_raw,
    generate_full_check_script,
    generate_precheck_script,
    script_fields_from_raw,
)
from ep_import.tasks import process_ep_import
from precheck.models import CheckType
from precheck.services.analysis import SESSION_ANALYSIS_KEY, create_check_analysis
from precheck.services.authorization import can_mutate_analysis, visible_analysis
from precheck.services.returns import MAX_RETURN_UPLOAD_BYTES

TECH_NAV = [
    ("2G", "2G"),
    ("3G", "3G"),
    ("4G", "4G"),
    ("5G", "5G NR"),
]


def _wants_json(request: HttpRequest) -> bool:
    accept = request.headers.get("Accept", "")
    return "application/json" in accept or request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _job_status_payload(job: ImportJob) -> dict:
    return {
        "id": str(job.id),
        "status": job.status,
        "filename": job.original_filename,
        "region": job.region,
        "counts": job.counts,
        "issues": job.issues,
        "ignored_sheets": job.ignored_sheets,
        "error_title": job.error_title,
        "stage": job.stage,
        "rows_processed": job.rows_processed,
        "rows_total": job.rows_total,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "expires_at": job.expires_at.isoformat() if job.expires_at else None,
    }


def _tech_count(job: ImportJob | None, technology: str) -> int:
    if not job or not job.counts:
        return 0
    return int(job.counts.get(technology, 0) or 0)


def _page_params(request: HttpRequest) -> tuple[int, int]:
    try:
        page = max(1, int(request.GET.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = int(request.GET.get("page_size", DEFAULT_PAGE_SIZE))
    except (TypeError, ValueError):
        page_size = DEFAULT_PAGE_SIZE
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
    return page, page_size


def _pager(request: HttpRequest, *, page: int, page_size: int, total: int, target: str) -> dict:
    page_count = max(1, (total + page_size - 1) // page_size) if total else 1
    params = request.GET.copy()
    params.pop("page", None)
    params["page_size"] = str(page_size)
    query = params.urlencode()
    url = f"{request.path}?{query}" if query else f"{request.path}?"
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "page_count": page_count,
        "has_next": page * page_size < total,
        "has_prev": page > 1,
        "url": url,
        "target": target,
    }


def ep_login_required(view):
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


def _workspace_context(job: ImportJob | None, technology: str) -> dict:
    ctx = {
        "job": job,
        "technology": technology,
        "tech_label": "5G NR" if technology == "5G" else technology,
        "max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
        "tech_count": _tech_count(job, technology),
        "polling": bool(job and job.status in {ImportJobStatus.PENDING, ImportJobStatus.PROCESSING}),
        "sites": [],
        "sites_total": 0,
        "selected_site": "",
        "cells": [],
        "cells_total": 0,
        "site": "",
        "sites_pager": None,
        "search": "",
    }
    if job and job.status == ImportJobStatus.SUCCESS:
        sites, sites_total = sites_page(job, technology)
        ctx["sites"] = sites
        ctx["sites_total"] = sites_total
        ctx["sites_pager"] = {
            "page": 1,
            "page_size": DEFAULT_PAGE_SIZE,
            "total": sites_total,
            "page_count": max(1, (sites_total + DEFAULT_PAGE_SIZE - 1) // DEFAULT_PAGE_SIZE) if sites_total else 1,
            "has_next": sites_total > DEFAULT_PAGE_SIZE,
            "has_prev": False,
            "url": (
                reverse("ep_import:job_sites", kwargs={"job_id": job.id})
                + f"?technology={technology}&page_size={DEFAULT_PAGE_SIZE}"
            ),
            "target": "#sites-results",
        }
    return ctx


@ep_login_required
@require_http_methods(["GET", "POST"])
def site_cells(request: HttpRequest, technology: str = "5G") -> HttpResponse:
    tech = technology.upper()
    if tech not in {t.value for t in Technology}:
        tech = Technology.G5.value

    job_id = request.GET.get("job") or request.session.get("ep_import_job_id")
    job = visible_job(request, job_id)

    context = {
        **_workspace_context(job, tech),
        "upload_url": reverse("ep_import:upload"),
        "generate_scripts_url": reverse("ep_import:generate_scripts"),
        "active_nav": tech,
        "tech_nav": TECH_NAV,
    }
    return render(request, "ep_import/site_cells.html", context)


def _selection_error(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse(
        {
            "type": "Error",
            "title": "Could not generate scripts",
            "message": message,
        },
        status=status,
    )


@ep_login_required
@require_POST
def generate_scripts(request: HttpRequest) -> JsonResponse:
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return _selection_error("The selection payload is invalid.")

    technology = str(data.get("technology") or "").upper()
    if technology not in {Technology.G5.value, *FULL_CHECK_ONLY_TECHNOLOGIES}:
        return _selection_error("Script generation in this flow is available for 5G NR, 4G, 3G and 2G only.")

    pre_check = data.get("pre_check") is True
    full_check = data.get("full_check") is True
    if technology in FULL_CHECK_ONLY_TECHNOLOGIES:
        if not full_check:
            return _selection_error(f"{technology} currently supports Full Check (pós-check) only.")
        pre_check = False
    elif technology == Technology.G5.value and not pre_check and not full_check:
        return _selection_error("Select at least one check type.")
    if not pre_check and not full_check:
        return _selection_error("Select at least one check type.")

    job = mutable_job(request, data.get("job_id"))
    if not job or job.status != ImportJobStatus.SUCCESS:
        return _selection_error("Import and process a valid EP file before generating scripts.")

    site = str(data.get("site") or "").strip()
    cell_names = data.get("cells")
    if not site or not isinstance(cell_names, list) or not cell_names:
        return _selection_error("Select a site and at least one cell.")

    selected_cells = list(dict.fromkeys(str(name).strip() for name in cell_names if str(name).strip()))
    if not selected_cells:
        return _selection_error("Select at least one cell.")

    valid_cells = set(
        EpCell.objects.filter(
            job=job,
            technology=technology,
            site_name=site,
            cell_name__in=selected_cells,
        ).values_list("cell_name", flat=True)
    )
    if valid_cells != set(selected_cells):
        return _selection_error("The selection contains cells that do not belong to the site or the imported EP.")

    analysis = create_check_analysis(
        user=request.user,
        job=job,
        site=site,
        cells=selected_cells,
        pre_check=pre_check,
        full_check=full_check,
        technology=technology,
    )
    request.session[SESSION_ANALYSIS_KEY] = str(analysis.id)
    request.session["check_script_selection"] = {
        "analysis_id": str(analysis.id),
        "job_id": str(job.id),
        "technology": technology,
        "site": site,
        "cells": selected_cells,
        "pre_check": pre_check,
        "full_check": full_check,
    }

    return JsonResponse(
        {
            "type": "Success",
            "redirect_url": reverse("ep_import:scripts", kwargs={"technology": technology}),
            "analysis_id": str(analysis.id),
        }
    )


def _cell_ids_from_ep(job: ImportJob, technology: str, site: str, cell_names: list[str]) -> list[str]:
    """Resolve CellId / CI values from selected EP rows (used by 2G/3G full-check scripts)."""
    ids: list[str] = []
    qs = EpCell.objects.filter(
        job=job,
        technology=technology,
        site_name=site,
        cell_name__in=cell_names,
    )
    by_name = {cell.cell_name: cell for cell in qs}
    for name in cell_names:
        cell = by_name.get(name)
        if cell is None:
            continue
        value = ep_cell_id_from_raw(cell.raw, technology)
        if value:
            ids.append(value)
    return ids


def _can_import_returns(pre_check: bool, full_check: bool, technology: str) -> bool:
    if pre_check:
        return True
    return bool(full_check and technology in {*FULL_CHECK_ONLY_TECHNOLOGIES, Technology.G5.value})


def _full_check_script_for(
    technology: str,
    *,
    job: ImportJob | None,
    site: str,
    cells: list[str],
) -> str:
    cell_ids = _cell_ids_from_ep(job, technology, site, cells) if job is not None else []
    fields = script_fields_from_raw(
        technology,
        first_selected_raw(
            job_id=job.id if job is not None else None,
            technology=technology,
            site_name=site,
            cell_names=cells,
        ),
    )
    return generate_full_check_script(
        technology,
        site_name=site,
        cell_names=cells,
        cell_ids=cell_ids,
        bsc=fields["bsc"],
        bts=fields["bts"],
        rnc=fields["rnc"],
        enodeb_id=fields["enodeb_id"],
    )


def _saved_script_context(request: HttpRequest) -> dict | None:
    analysis = visible_analysis(request, request.session.get(SESSION_ANALYSIS_KEY))
    if analysis is None:
        selection = request.session.get("check_script_selection") or {}
        analysis = visible_analysis(request, selection.get("analysis_id"))

    if analysis is not None and analysis.ep_job.status == ImportJobStatus.SUCCESS:
        precheck_file = analysis.return_files.filter(check_type=CheckType.PRECHECK).first()
        full_check_file = analysis.return_files.filter(check_type=CheckType.FULL_CHECK).first()
        tech = analysis.technology
        can_mutate = can_mutate_analysis(request.user, analysis)
        can_import = bool(can_mutate and _can_import_returns(analysis.pre_check, analysis.full_check, tech))
        return {
            "analysis": analysis,
            "job": analysis.ep_job,
            "technology": tech,
            "tech_label": "5G NR" if tech == Technology.G5.value else tech,
            "active_nav": tech,
            "tech_nav": TECH_NAV,
            "site": analysis.site_name,
            "selected_cells": analysis.selected_cells,
            "selected_cells_count": len(analysis.selected_cells or []),
            "pre_check": analysis.pre_check,
            "full_check": analysis.full_check,
            "precheck_script": (
                generate_precheck_script(
                    tech,
                    site_name=analysis.site_name,
                    cell_names=analysis.selected_cells or [],
                )
                if analysis.pre_check
                else ""
            ),
            "full_check_script": (
                _full_check_script_for(
                    tech,
                    job=analysis.ep_job,
                    site=analysis.site_name,
                    cells=list(analysis.selected_cells or []),
                )
                if analysis.full_check
                else ""
            ),
            "import_returns_url": reverse("precheck:import_returns", kwargs={"technology": tech}) if can_import else "",
            "can_import": can_import,
            "can_mutate": can_mutate,
            "precheck_return": precheck_file,
            "has_precheck_return": precheck_file is not None,
            "full_check_return": full_check_file,
            "has_full_check_return": full_check_file is not None,
            "max_return_mb": MAX_RETURN_UPLOAD_BYTES // (1024 * 1024),
            "upload_precheck_url": reverse("precheck:upload_precheck_return", kwargs={"technology": tech})
            if can_import and analysis.pre_check
            else "",
            "upload_full_check_url": (
                reverse("poscheck:upload_full_check_return") if can_import and analysis.full_check else ""
            ),
            "process_url": reverse("precheck:process", kwargs={"technology": tech}) if can_import else "",
        }

    selection = request.session.get("check_script_selection")
    if not selection:
        return None

    try:
        job = visible_job(request, selection.get("job_id"))
    except (ValidationError, ValueError, TypeError):
        return None
    if not job or job.status != ImportJobStatus.SUCCESS:
        return None

    tech = str(selection.get("technology") or Technology.G5.value).upper()
    pre_check = bool(selection.get("pre_check"))
    full_check = bool(selection.get("full_check"))
    can_import = _can_import_returns(pre_check, full_check, tech)
    return {
        "analysis": None,
        "job": job,
        "technology": tech,
        "tech_label": "5G NR" if tech == Technology.G5.value else tech,
        "active_nav": tech,
        "tech_nav": TECH_NAV,
        "site": selection["site"],
        "selected_cells": selection["cells"],
        "selected_cells_count": len(selection["cells"]),
        "pre_check": pre_check,
        "full_check": full_check,
        "precheck_script": (
            generate_precheck_script(
                tech,
                site_name=selection.get("site") or "",
                cell_names=selection.get("cells") or [],
            )
            if pre_check
            else ""
        ),
        "full_check_script": (
            _full_check_script_for(
                tech,
                job=job,
                site=selection.get("site") or "",
                cells=list(selection.get("cells") or []),
            )
            if full_check
            else ""
        ),
        "import_returns_url": reverse("precheck:import_returns", kwargs={"technology": tech}) if can_import else "",
        "can_import": False,
        "can_mutate": False,
        "precheck_return": None,
        "has_precheck_return": False,
        "full_check_return": None,
        "has_full_check_return": False,
        "max_return_mb": MAX_RETURN_UPLOAD_BYTES // (1024 * 1024),
        "upload_precheck_url": "",
        "upload_full_check_url": "",
        "process_url": "",
    }


@ep_login_required
@require_GET
def scripts(request: HttpRequest, technology: str = "5G") -> HttpResponse:
    context = _saved_script_context(request)
    if not context:
        return redirect(reverse("ep_import:site_cells", kwargs={"technology": technology or Technology.G5.value}))
    return render(request, "ep_import/scripts.html", context)


@ep_login_required
@require_GET
def download_script(request: HttpRequest, technology: str, check_type: str) -> HttpResponse:
    context = _saved_script_context(request)
    if not context:
        return redirect(reverse("ep_import:site_cells", kwargs={"technology": technology or Technology.G5.value}))

    if check_type == "precheck" and context["pre_check"]:
        content = context["precheck_script"]
        filename = f"Claro_RF_Check_PreCheck_{context['technology']}.txt"
    elif check_type == "full-check" and context["full_check"]:
        content = context["full_check_script"]
        filename = f"Claro_RF_Check_FullCheck_{context['technology']}.txt"
    else:
        return _selection_error("The requested check type is not part of the selection.", status=404)

    response = HttpResponse(content, content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@ep_login_required
@require_POST
def upload_ep(request: HttpRequest) -> HttpResponse:
    form = EpUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        errors = form.errors.get_json_data()
        message = next(iter(form.errors.values()))[0] if form.errors else "Invalid upload."
        if _wants_json(request) or getattr(request, "htmx", False):
            return JsonResponse(
                {
                    "type": "Error",
                    "title": "Upload error",
                    "message": str(message),
                    "errors": errors,
                },
                status=400,
            )
        return redirect(reverse("ep_import:site_cells", kwargs={"technology": "5G"}))

    if not _allow_upload(request.user):
        return JsonResponse(
            {
                "type": "Error",
                "title": "Upload limit",
                "message": "Too many uploads. Try again later.",
            },
            status=429,
        )

    uploaded = form.cleaned_data["file"]
    technology = form.cleaned_data.get("technology") or Technology.G5.value
    digest = sha256_file(uploaded)
    job, created = _job_for_upload(request.user, uploaded, digest)
    request.session["ep_import_job_id"] = str(job.id)
    if created or (job.status == ImportJobStatus.PENDING and not job.task_id):
        process_ep_import.delay(str(job.id))
    job.refresh_from_db()

    redirect_url = reverse("ep_import:site_cells", kwargs={"technology": technology}) + f"?job={job.id}"
    if job.status == ImportJobStatus.FAILED:
        message = job.issues[0]["message"] if job.issues else "The file could not be imported."
        if _wants_json(request) or getattr(request, "htmx", False):
            return JsonResponse(
                {
                    "type": "Error",
                    "title": job.error_title or "Import error",
                    "message": message,
                    "job": _job_status_payload(job),
                },
                status=400,
            )
        return redirect(redirect_url)

    if job.status == ImportJobStatus.SUCCESS:
        title, message = "EP imported", "File processed successfully."
    elif created:
        title, message = "Import started", "Processing EP file…"
    else:
        title, message = "Import already started", "This file is already being processed."

    payload = {
        "type": "Success",
        "title": title,
        "message": message,
        "job": _job_status_payload(job),
        "status_url": reverse("ep_import:job_status", kwargs={"job_id": job.id}),
        "redirect_url": redirect_url,
    }

    if getattr(request, "htmx", False):
        response = render(
            request,
            "ep_import/partials/import_result.html",
            _workspace_context(job, technology),
        )
        response["HX-Push-Url"] = redirect_url
        return response

    if _wants_json(request):
        status_code = 200 if job.status == ImportJobStatus.SUCCESS else 202
        return JsonResponse(payload, status=status_code)

    return redirect(redirect_url)


@ep_login_required
@require_GET
def job_status(request: HttpRequest, job_id) -> HttpResponse:
    job = get_authorized_job(request, job_id)
    if _wants_json(request) and not getattr(request, "htmx", False):
        return JsonResponse(_job_status_payload(job))

    technology = request.GET.get("technology", Technology.G5.value)
    ctx = _workspace_context(job, technology)
    # Always return workspace fragment so HTMX polling can replace #ep-workspace safely.
    if job.status in {ImportJobStatus.PENDING, ImportJobStatus.PROCESSING}:
        return render(request, "ep_import/partials/processing_workspace.html", ctx)
    return render(request, "ep_import/partials/import_result.html", ctx)


@ep_login_required
@require_GET
def job_sites(request: HttpRequest, job_id) -> HttpResponse:
    job = get_authorized_job(request, job_id)
    technology = request.GET.get("technology", Technology.G5.value)
    search = (request.GET.get("q") or "").strip()
    page, page_size = _page_params(request)
    sites, sites_total = sites_page(job, technology, search, page, page_size)
    pager = _pager(request, page=page, page_size=page_size, total=sites_total, target="#sites-results")

    if getattr(request, "htmx", False):
        return render(
            request,
            "ep_import/partials/sites_results.html",
            {
                "job": job,
                "technology": technology,
                "sites": sites,
                "sites_total": sites_total,
                "selected_site": request.GET.get("site", ""),
                "search": search,
                "sites_pager": pager,
            },
        )

    return JsonResponse(
        {
            "job_id": str(job.id),
            "technology": technology,
            "sites_total": sites_total,
            "total": sites_total,
            "page": page,
            "page_size": page_size,
            "has_next": pager["has_next"],
            "sites": sites,
        }
    )


@ep_login_required
@require_GET
def job_cells(request: HttpRequest, job_id) -> HttpResponse:
    job = get_authorized_job(request, job_id)
    technology = request.GET.get("technology", Technology.G5.value)
    site = (request.GET.get("site") or "").strip()
    search = (request.GET.get("q") or "").strip()

    page, page_size = _page_params(request)
    qs = EpCell.objects.filter(job=job, technology=technology)
    if site:
        qs = qs.filter(site_name=site)
    if search:
        qs = qs.filter(cell_search(search))

    cells_total = qs.count() if site else 0
    offset = (page - 1) * page_size
    cells = []
    if site:
        for row in qs.order_by("cell_name")[offset : offset + page_size]:
            raw = row.raw or {}
            cells.append(_cell_payload(row, raw))
    pager = _pager(request, page=page, page_size=page_size, total=cells_total, target="#cells-results")

    context = {
        "job": job,
        "technology": technology,
        "site": site,
        "cells": cells,
        "cells_total": cells_total,
        "search": search,
        "cells_pager": pager,
    }
    if getattr(request, "htmx", False):
        target = getattr(getattr(request, "htmx", None), "target", "") or ""
        template = (
            "ep_import/partials/cells_results.html"
            if target == "cells-results"
            else "ep_import/partials/cells_list.html"
        )
        return render(request, template, context)

    return JsonResponse(
        {
            "job_id": str(job.id),
            "technology": technology,
            "site": site,
            "cells_total": cells_total,
            "total": cells_total,
            "page": page,
            "page_size": page_size,
            "has_next": pager["has_next"],
            "cells": cells,
        }
    )


def _job_for_upload(user, uploaded, digest: str) -> tuple[ImportJob, bool]:
    with transaction.atomic():
        existing = (
            ImportJob.objects.select_for_update()
            .filter(
                created_by=user,
                content_sha256=digest,
                status__in=[
                    ImportJobStatus.PENDING,
                    ImportJobStatus.PROCESSING,
                    ImportJobStatus.SUCCESS,
                ],
                expires_at__gt=timezone.now(),
            )
            .order_by("-created_at")
            .first()
        )
        if existing and can_mutate_job(user, existing):
            return existing, False
        job = ImportJob.objects.create(
            created_by=user,
            original_filename=uploaded.name,
            stored_file=uploaded,
            status=ImportJobStatus.PENDING,
            stage="queued",
            content_sha256=digest,
        )
        return job, True


def _allow_upload(user) -> bool:
    limit = int(getattr(settings, "EP_IMPORT_UPLOAD_RATE_LIMIT", 20))
    window = int(getattr(settings, "EP_IMPORT_UPLOAD_RATE_WINDOW", 3600))
    key = f"ep_import:upload:{user.pk}"
    current = cache.get(key, 0)
    if current >= limit:
        return False
    cache.set(key, current + 1, timeout=window)
    return True


def _cell_payload(row: EpCell, raw: dict) -> dict:
    return {
        "id": row.id,
        "cell_name": row.cell_name,
        "band": raw.get("FrequencyBand") or raw.get("CARRIER") or raw.get("*CELL TYPE") or "—",
        "frequency": raw.get("DlNarfcn")
        or raw.get("EARFCN_DL")
        or raw.get("UARFCN DOWNLINK")
        or raw.get("*FREQUENCY OF BCCH")
        or "—",
        "on_air": row.on_air or "",
        "status": _cell_status_label(row.on_air),
    }


def _cell_status_label(on_air: str) -> str:
    if not on_air:
        return "Active"
    value = on_air.strip().upper()
    if value in {"YES", "Y", "ATIVO", "TRUE", "1"}:
        return "Active"
    if value in {"NO", "N", "INATIVO", "FALSE", "0"}:
        return "Inactive"
    return on_air
