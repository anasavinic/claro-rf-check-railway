"""Job execution history list (scoped by view_all_jobs)."""

from __future__ import annotations

from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_GET
from django.views.generic import ListView
from users.models import User
from users.permissions import user_can_view_all_jobs

from precheck.models import CheckExecution, CheckExecutionScope, CheckExecutionStatus
from precheck.services.analysis import SESSION_ANALYSIS_KEY
from precheck.services.authorization import visible_executions_queryset

TECH_NAV = [
    ("2G", "2G"),
    ("3G", "3G"),
    ("4G", "4G"),
    ("5G", "5G NR"),
]

TECHNOLOGY_CHOICES = ("2G", "3G", "4G", "5G")


def _safe_redirect_target(url: str, *, technology: str) -> str:
    """Only follow app-relative paths stored on the execution; refuse open redirects."""
    if url.startswith("/") and not url.startswith("//"):
        return url
    return reverse("precheck:result", kwargs={"technology": technology or "5G"})


@login_required
@require_GET
def open_execution(request: HttpRequest, execution_id) -> HttpResponse:
    """Restore the execution's analysis into session, then follow its result URL."""
    execution = visible_executions_queryset(request.user).filter(pk=execution_id).first()
    if execution is None:
        raise Http404("Execution not found.")

    request.session[SESSION_ANALYSIS_KEY] = str(execution.analysis_id)
    target = _safe_redirect_target(
        execution.redirect_url or "",
        technology=execution.analysis.technology,
    )
    return redirect(target)


class HistoryListView(LoginRequiredMixin, ListView):
    model = CheckExecution
    template_name = "precheck/history_list.html"
    partial_template_name = "precheck/partials/history_table.html"
    context_object_name = "executions"
    paginate_by = 20

    def _can_view_all(self) -> bool:
        return user_can_view_all_jobs(self.request.user)

    def _filter_params(self) -> dict[str, str]:
        get = self.request.GET
        return {
            "q": (get.get("q") or "").strip(),
            "status": (get.get("status") or "").strip(),
            "scope": (get.get("scope") or "").strip(),
            "technology": (get.get("technology") or "").strip(),
            "created_by": (get.get("created_by") or "").strip(),
            "date_from": (get.get("date_from") or "").strip(),
            "date_to": (get.get("date_to") or "").strip(),
        }

    def get_queryset(self):
        qs = visible_executions_queryset(self.request.user)
        params = self._filter_params()

        q = params["q"]
        if q:
            qs = qs.filter(
                Q(analysis__site_name__icontains=q)
                | Q(analysis__ep_job__original_filename__icontains=q)
                | Q(created_by__username__icontains=q)
                | Q(created_by__email__icontains=q)
                | Q(created_by__first_name__icontains=q)
                | Q(created_by__last_name__icontains=q)
                | Q(error_title__icontains=q)
            )

        status = params["status"]
        if status in {c.value for c in CheckExecutionStatus}:
            qs = qs.filter(status=status)

        scope = params["scope"]
        if scope in {c.value for c in CheckExecutionScope}:
            qs = qs.filter(scope=scope)

        technology = params["technology"]
        if technology in TECHNOLOGY_CHOICES:
            qs = qs.filter(analysis__technology=technology)

        if self._can_view_all():
            created_by = params["created_by"]
            if created_by.isdigit():
                qs = qs.filter(created_by_id=int(created_by))

        date_from = parse_date(params["date_from"]) if params["date_from"] else None
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)

        date_to = parse_date(params["date_to"]) if params["date_to"] else None
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        return qs

    def get_template_names(self):
        if getattr(self.request, "htmx", False):
            return [self.partial_template_name]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = self._filter_params()
        can_view_all = self._can_view_all()
        context.update(params)
        context["search_q"] = params["q"]
        context["active_nav"] = "history"
        context["tech_nav"] = TECH_NAV
        context["can_view_all_jobs"] = can_view_all
        context["status_choices"] = CheckExecutionStatus.choices
        context["scope_choices"] = CheckExecutionScope.choices
        context["technology_choices"] = [(t, "5G NR" if t == "5G" else t) for t in TECHNOLOGY_CHOICES]
        context["filter_query"] = urlencode({k: v for k, v in params.items() if v})
        if can_view_all:
            context["filter_users"] = (
                User.objects.filter(check_executions__isnull=False)
                .distinct()
                .order_by("first_name", "last_name", "email")
            )
        else:
            context["filter_users"] = User.objects.none()
        return context
