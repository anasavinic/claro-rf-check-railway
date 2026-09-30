from __future__ import annotations

import logging
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_GET

from combined.services.authorization import visible_combined
from combined.services.combined import SESSION_COMBINED_KEY
from precheck.services.authorization import visible_analysis
from reports.services.email import (
    EML_CONTENT_TYPE,
    MSG_CONTENT_TYPE,
    render_email,
    render_msg,
)
from reports.services.errors import ExportError, render_failed
from reports.services.payload import build_combined_export_payload, build_export_payload
from reports.services.xlsx import XLSX_CONTENT_TYPE, render_xlsx, report_basename

logger = logging.getLogger("reports.export")


def _wants_json(request: HttpRequest) -> bool:
    accept = request.headers.get("Accept", "")
    return "application/json" in accept or request.headers.get("X-Requested-With") == "XMLHttpRequest"


def reports_login_required(view):
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


def _content_disposition(filename: str) -> str:
    ascii_name = filename.encode("ascii", "replace").decode("ascii")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


def _file_response(content: bytes, *, filename: str, content_type: str) -> HttpResponse:
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = _content_disposition(filename)
    return response


def _load_payload(request: HttpRequest, analysis_id):
    analysis = visible_analysis(request, analysis_id)
    if analysis is None:
        return None, _json_error("Not found", "Analysis was not found.", status=404)
    try:
        return build_export_payload(analysis), None
    except ExportError as exc:
        message = exc.issues[0].message if exc.issues else str(exc)
        return None, _json_error(exc.title, message, status=400)


@reports_login_required
@require_GET
def export_report(request: HttpRequest, analysis_id) -> HttpResponse:
    payload, error = _load_payload(request, analysis_id)
    if error is not None:
        return error
    try:
        content = render_xlsx(payload)
    except Exception:
        logger.exception("Failed to render Excel report for analysis %s", analysis_id)
        issue = render_failed()
        return _json_error("Export failed", issue.message, status=500)
    return _file_response(
        content,
        filename=f"{report_basename(payload)}.xlsx",
        content_type=XLSX_CONTENT_TYPE,
    )


@reports_login_required
@require_GET
def prepare_email(request: HttpRequest, analysis_id) -> HttpResponse:
    payload, error = _load_payload(request, analysis_id)
    if error is not None:
        return error
    return _email_file(request, payload, analysis_id)


@reports_login_required
@require_GET
def export_combined_report(request: HttpRequest) -> HttpResponse:
    payload, error = _load_combined_payload(request)
    if error is not None:
        return error
    try:
        content = render_xlsx(payload)
    except Exception:
        logger.exception(
            "Failed to render Excel report for combined check %s",
            payload.analysis_id,
        )
        issue = render_failed()
        return _json_error("Export failed", issue.message, status=500)
    return _file_response(
        content,
        filename=f"{report_basename(payload)}.xlsx",
        content_type=XLSX_CONTENT_TYPE,
    )


@reports_login_required
@require_GET
def prepare_combined_email(request: HttpRequest) -> HttpResponse:
    payload, error = _load_combined_payload(request)
    if error is not None:
        return error
    return _email_file(request, payload, payload.analysis_id)


def _load_combined_payload(request: HttpRequest):
    combined = visible_combined(request, request.session.get(SESSION_COMBINED_KEY))
    if combined is None:
        return None, _json_error(
            "Not found",
            "Combined check was not found.",
            status=404,
        )
    try:
        return build_combined_export_payload(combined), None
    except ExportError as exc:
        message = exc.issues[0].message if exc.issues else str(exc)
        return None, _json_error(exc.title, message, status=400)


def _email_file(request: HttpRequest, payload, analysis_id) -> HttpResponse:
    kind = (request.GET.get("format") or "eml").strip().lower()
    formats = {
        "eml": (".eml", EML_CONTENT_TYPE, render_email),
        "msg": (".msg", MSG_CONTENT_TYPE, render_msg),
    }
    spec = formats.get(kind)
    if spec is None:
        return _json_error("Share failed", "Choose an .eml or .msg email file.")
    suffix, content_type, renderer = spec
    from_address = (getattr(request.user, "email", "") or "").strip()
    try:
        content = renderer(payload, from_address=from_address)
    except Exception:
        logger.exception(
            "Failed to render %s email draft for analysis %s",
            kind,
            analysis_id,
        )
        issue = render_failed()
        return _json_error("Share failed", issue.message, status=500)
    return _file_response(
        content,
        filename=f"{report_basename(payload)}{suffix}",
        content_type=content_type,
    )
