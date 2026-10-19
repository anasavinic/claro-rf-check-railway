"""
RBAC helpers: plain Django Group + Permission checks.

Groups are data (Roles UI / seed). This module does not hard-code role names
except for seed constants and gate helpers used by views.
"""

from __future__ import annotations

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

# Apps whose permissions appear in the Roles / Extra permissions UI.
RBAC_APPS = frozenset(
    {
        "auth",
        "users",
        "ep_import",
        "precheck",
        "poscheck",
        "reports",
    }
)

MANAGE_ROLES_PERM = "users.manage_roles"
VIEW_ALL_JOBS_PERM = "precheck.view_all_jobs"
ADD_GROUP_PERM = "auth.add_group"
CHANGE_GROUP_PERM = "auth.change_group"
DELETE_GROUP_PERM = "auth.delete_group"

# Seeded group names (stable labels for Roles UI / SSO default).
ADMIN = "Admin"
MANAGER = "Manager"
OPERATOR = "Operator"
SEED_GROUP_NAMES = (ADMIN, MANAGER, OPERATOR)

_MANAGER_EXCLUDED_CODENAMES = frozenset({"add_group", "change_group", "delete_group"})


def user_has_perm(user, perm: str) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    return user.has_perm(perm)


def user_can_manage_roles(user) -> bool:
    return user_has_perm(user, MANAGE_ROLES_PERM)


def user_can_view_all_jobs(user) -> bool:
    return user_has_perm(user, VIEW_ALL_JOBS_PERM)


def user_can_create_roles(user) -> bool:
    return user_can_manage_roles(user) and user_has_perm(user, ADD_GROUP_PERM)


def user_can_update_roles(user) -> bool:
    return user_can_manage_roles(user) and user_has_perm(user, CHANGE_GROUP_PERM)


def user_can_delete_roles(user) -> bool:
    return user_can_manage_roles(user) and user_has_perm(user, DELETE_GROUP_PERM)


def assignable_permissions_queryset():
    return (
        Permission.objects.filter(content_type__app_label__in=RBAC_APPS)
        .select_related("content_type")
        .order_by("content_type__app_label", "content_type__model", "codename")
    )


def permission_display_label(perm, model: str) -> str:
    suffix = f"_{model}"
    if perm.codename.endswith(suffix):
        return perm.codename[: -len(suffix)].replace("_", " ")
    return perm.name


def permission_modules_for_roles():
    perms = list(assignable_permissions_queryset())
    by_content_type: dict[int, list] = {}
    content_types: dict[int, ContentType] = {}
    for perm in perms:
        ct = perm.content_type
        by_content_type.setdefault(ct.id, []).append(perm)
        content_types.setdefault(ct.id, ct)

    modules = []
    for ct_id in sorted(content_types, key=lambda cid: (content_types[cid].app_label, content_types[cid].model)):
        ct = content_types[ct_id]
        model_perms = by_content_type.get(ct_id, [])
        if not model_perms:
            continue
        rows = [{"perm": p, "label": permission_display_label(p, ct.model)} for p in model_perms]
        try:
            label = ct.model_class()._meta.verbose_name_plural.title()
        except Exception:
            label = ct.model.replace("_", " ").title()
        modules.append({"label": label, "model": ct.model, "app_label": ct.app_label, "rows": rows})
    return modules


def permissions_for_seed_group(name: str) -> list[Permission]:
    """Resolve Permission rows for a seeded group (Admin / Manager / Operator)."""
    qs = assignable_permissions_queryset()
    if name == ADMIN:
        return list(qs)
    if name == MANAGER:
        return list(qs.exclude(content_type__app_label="auth", codename__in=_MANAGER_EXCLUDED_CODENAMES))
    if name == OPERATOR:
        return []
    raise ValueError(f"Unknown seed group: {name!r}")
