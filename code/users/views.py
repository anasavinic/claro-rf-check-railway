"""SSO callback adaptations and RBAC user management views."""

from __future__ import annotations

import logging

from core_connect_sso import CoreConnectSSOError
from core_connect_sso.contrib.django.views import CallbackView as SDKCallbackView
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import HttpResponseBadRequest
from django.urls import reverse_lazy
from django.views.generic import DetailView, ListView, UpdateView

from users.forms import UserRbacForm
from users.models import User
from users.permissions import permission_modules_for_roles, user_can_manage_roles

logger = logging.getLogger(__name__)


class CallbackView(SDKCallbackView):
    def get(self, request):
        try:
            return super().get(request)
        except CoreConnectSSOError as exc:
            logger.warning("SSO user mapping failed: %s", type(exc).__name__)
            response = HttpResponseBadRequest("Unable to establish SSO identity", content_type="text/plain")
            response["Cache-Control"] = "no-store"
            response["Referrer-Policy"] = "no-referrer"
            return response


class UserRbacAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return user_can_manage_roles(self.request.user)

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect_to_login(
                self.request.get_full_path(),
                self.get_login_url(),
                self.get_redirect_field_name(),
            )
        raise PermissionDenied

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_nav"] = "settings"
        context["tech_nav"] = []
        context["can_manage_roles"] = True
        return context


class UserRbacFormMixin:
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["can_edit_rbac"] = user_can_manage_roles(self.request.user)
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        can_edit = user_can_manage_roles(self.request.user)
        context["can_edit_rbac"] = can_edit
        context["permission_modules"] = permission_modules_for_roles() if can_edit else []
        obj = getattr(self, "object", None)
        if can_edit and obj is not None and obj.pk:
            context["selected_perm_ids"] = {p.pk for p in obj.user_permissions.all()}
            context["selected_group_ids"] = {g.pk for g in obj.groups.all()}
        else:
            form = context.get("form")
            if form is not None and form.is_bound:
                context["selected_perm_ids"] = {
                    int(pk) for pk in form.data.getlist("user_permissions") if str(pk).isdigit()
                }
                context["selected_group_ids"] = {int(pk) for pk in form.data.getlist("groups") if str(pk).isdigit()}
            else:
                context["selected_perm_ids"] = set()
                context["selected_group_ids"] = set()
        return context


class UserListView(UserRbacAccessMixin, ListView):
    model = User
    template_name = "users/user_list.html"
    partial_template_name = "users/partials/user_table.html"
    context_object_name = "users"
    paginate_by = 20

    def get_queryset(self):
        qs = (
            User.objects.annotate(groups_count=Count("groups"))
            .prefetch_related("groups")
            .order_by("first_name", "last_name", "email")
        )
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(email__icontains=q)
                | Q(username__icontains=q)
            )
        return qs

    def get_template_names(self):
        if getattr(self.request, "htmx", False):
            return [self.partial_template_name]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_q"] = (self.request.GET.get("q") or "").strip()
        return context


class UserDetailView(UserRbacAccessMixin, DetailView):
    model = User
    template_name = "users/user_detail.html"
    context_object_name = "object"

    def get_queryset(self):
        return User.objects.prefetch_related("groups", "user_permissions")


class UserUpdateView(UserRbacFormMixin, UserRbacAccessMixin, UpdateView):
    model = User
    form_class = UserRbacForm
    template_name = "users/user_form.html"
    success_url = reverse_lazy("users:list")

    def get_queryset(self):
        return User.objects.prefetch_related("groups", "user_permissions")

    def form_valid(self, form):
        messages.success(self.request, f"User '{form.instance.display_name()}' updated.")
        return super().form_valid(form)
