"""RBAC seed, role gates, and users UI access."""

import pytest
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.urls import reverse
from users.models import User
from users.permissions import (
    ADMIN,
    MANAGER,
    OPERATOR,
    permissions_for_seed_group,
    user_can_create_roles,
    user_can_delete_roles,
    user_can_manage_roles,
    user_can_update_roles,
)

pytestmark = pytest.mark.django_db


def _grant(user, *codenames, app_label="users"):
    for codename in codenames:
        perm = Permission.objects.get(content_type__app_label=app_label, codename=codename)
        user.user_permissions.add(perm)
    user = User.objects.get(pk=user.pk)
    return user


@pytest.fixture
def operator_user():
    return User.objects.create_user(username="operator", password="pass")  # pragma: allowlist secret


@pytest.fixture
def manager_user():
    user = User.objects.create_user(username="manager", password="pass")  # pragma: allowlist secret
    call_command("seed")
    manager = Group.objects.get(name=MANAGER)
    user.groups.add(manager)
    return User.objects.get(pk=user.pk)


@pytest.fixture
def admin_role_user():
    user = User.objects.create_user(username="admin-role", password="pass")  # pragma: allowlist secret
    call_command("seed")
    admin = Group.objects.get(name=ADMIN)
    user.groups.add(admin)
    return User.objects.get(pk=user.pk)


def test_seed_creates_groups_with_expected_matrix():
    call_command("seed")
    call_command("seed")  # idempotent

    admin = Group.objects.get(name=ADMIN)
    manager = Group.objects.get(name=MANAGER)
    operator = Group.objects.get(name=OPERATOR)

    assert set(admin.permissions.values_list("id", flat=True)) == {p.id for p in permissions_for_seed_group(ADMIN)}
    assert set(manager.permissions.values_list("id", flat=True)) == {p.id for p in permissions_for_seed_group(MANAGER)}
    assert operator.permissions.count() == 0

    manager_codenames = set(
        manager.permissions.filter(content_type__app_label="auth").values_list("codename", flat=True)
    )
    assert "add_group" not in manager_codenames
    assert "change_group" not in manager_codenames
    assert "delete_group" not in manager_codenames
    assert manager.permissions.filter(codename="manage_roles").exists()
    assert manager.permissions.filter(codename="view_all_jobs").exists()
    assert admin.permissions.filter(codename="view_all_jobs").exists()


def test_manager_can_manage_users_but_not_mutate_roles(manager_user, client):
    assert user_can_manage_roles(manager_user)
    assert not user_can_create_roles(manager_user)
    assert not user_can_update_roles(manager_user)
    assert not user_can_delete_roles(manager_user)

    client.force_login(manager_user)
    assert client.get(reverse("settings:roles-list")).status_code == 200
    assert client.get(reverse("settings:roles-create")).status_code == 403
    role = Group.objects.get(name=OPERATOR)
    assert client.get(reverse("settings:roles-update", args=[role.pk])).status_code == 403
    assert client.get(reverse("settings:roles-delete", args=[role.pk])).status_code == 403
    assert client.get(reverse("users:list")).status_code == 200


def test_admin_role_can_create_roles(admin_role_user, client):
    assert user_can_create_roles(admin_role_user)
    assert user_can_update_roles(admin_role_user)
    assert user_can_delete_roles(admin_role_user)

    client.force_login(admin_role_user)
    assert client.get(reverse("settings:roles-create")).status_code == 200


def test_operator_cannot_access_settings(operator_user, client):
    client.force_login(operator_user)
    assert client.get(reverse("settings:page")).status_code == 403
    assert client.get(reverse("users:list")).status_code == 403
    home = client.get(reverse("home:index"))
    assert home.status_code == 200
    assert b"Settings" not in home.content


def test_sidebar_shows_settings_for_manage_roles(admin_role_user, client):
    client.force_login(admin_role_user)
    home = client.get(reverse("home:index"))
    assert home.status_code == 200
    assert b"Settings" in home.content


def test_manager_can_persist_user_groups_and_extra_permissions(manager_user, client):
    call_command("seed")
    target = User.objects.create_user(username="target", password="pass")  # pragma: allowlist secret
    operator = Group.objects.get(name=OPERATOR)
    manager = Group.objects.get(name=MANAGER)
    extra = Permission.objects.get(content_type__app_label="users", codename="view_user")

    client.force_login(manager_user)
    response = client.post(
        reverse("users:update", args=[target.pk]),
        {
            "first_name": "Target",
            "last_name": "User",
            "email": target.email or "target@example.com",
            "is_active": "on",
            "groups": [str(operator.pk), str(manager.pk)],
            "user_permissions": [str(extra.pk)],
        },
    )
    assert response.status_code == 302

    target = User.objects.get(pk=target.pk)
    assert set(target.groups.values_list("name", flat=True)) == {OPERATOR, MANAGER}
    assert set(target.user_permissions.values_list("codename", flat=True)) == {"view_user"}
