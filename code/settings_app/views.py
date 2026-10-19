from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.models import Group
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView
from users.permissions import (
    permission_modules_for_roles,
    user_can_create_roles,
    user_can_delete_roles,
    user_can_manage_roles,
    user_can_update_roles,
)

from .forms import RoleForm


class SettingsAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
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


class SettingsView(SettingsAccessMixin, TemplateView):
    template_name = "settings/hub.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_nav"] = "settings"
        context["can_manage_roles"] = True
        context["tech_nav"] = []
        return context


class RoleAdminMixin(SettingsAccessMixin):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_nav"] = "settings"
        context["tech_nav"] = []
        context["can_manage_roles"] = True
        context["can_create_roles"] = user_can_create_roles(self.request.user)
        context["can_update_roles"] = user_can_update_roles(self.request.user)
        context["can_delete_roles"] = user_can_delete_roles(self.request.user)
        return context


class RoleFormMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["permission_modules"] = permission_modules_for_roles()
        if self.object and self.object.pk:
            context["selected_perm_ids"] = set(self.object.permissions.values_list("pk", flat=True))
        else:
            context["selected_perm_ids"] = set()
        if self.request.method == "POST":
            context["selected_perm_ids"] = {int(pk) for pk in self.request.POST.getlist("permissions") if pk.isdigit()}
        return context


class RoleListView(RoleAdminMixin, ListView):
    model = Group
    template_name = "settings/role_list.html"
    partial_template_name = "settings/partials/role_table.html"
    context_object_name = "roles"
    paginate_by = 20

    def get_queryset(self):
        qs = Group.objects.annotate(permissions_count=Count("permissions"), users_count=Count("user")).order_by("name")
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q))
        return qs

    def get_template_names(self):
        if getattr(self.request, "htmx", False):
            return [self.partial_template_name]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_q"] = (self.request.GET.get("q") or "").strip()
        return context


class RoleDetailView(RoleFormMixin, RoleAdminMixin, DetailView):
    model = Group
    template_name = "settings/role_detail.html"
    context_object_name = "object"

    def get_queryset(self):
        return Group.objects.prefetch_related("permissions", "user_set")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected = context["selected_perm_ids"]
        modules = []
        for module in context["permission_modules"]:
            rows = [row for row in module["rows"] if row["perm"].pk in selected]
            if rows:
                modules.append({**module, "rows": rows})
        context["permission_modules"] = modules
        context["permissions_count"] = self.object.permissions.count()
        context["users_count"] = self.object.user_set.count()
        return context


class RoleCreateView(RoleFormMixin, RoleAdminMixin, CreateView):
    model = Group
    form_class = RoleForm
    template_name = "settings/role_form.html"
    success_url = reverse_lazy("settings:roles-list")

    def test_func(self):
        return user_can_create_roles(self.request.user)

    def form_valid(self, form):
        messages.success(self.request, f"Role '{form.instance.name}' created.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["action"] = "Create"
        return context


class RoleUpdateView(RoleFormMixin, RoleAdminMixin, UpdateView):
    model = Group
    form_class = RoleForm
    template_name = "settings/role_form.html"
    success_url = reverse_lazy("settings:roles-list")

    def test_func(self):
        return user_can_update_roles(self.request.user)

    def form_valid(self, form):
        messages.success(self.request, f"Role '{form.instance.name}' updated.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["action"] = "Edit"
        return context


class RoleDeleteView(RoleAdminMixin, DeleteView):
    model = Group
    success_url = reverse_lazy("settings:roles-list")
    template_name = "settings/role_confirm_delete.html"

    def test_func(self):
        return user_can_delete_roles(self.request.user)

    def get(self, request, *args, **kwargs):
        role = self.get_object()
        return render(
            request,
            self.template_name,
            {
                "object": role,
                "active_nav": "settings",
                "tech_nav": [],
                "can_manage_roles": True,
            },
        )

    def form_valid(self, form):
        name = self.object.name
        response = super().form_valid(form)
        messages.success(self.request, f"Role '{name}' deleted.")
        return response
