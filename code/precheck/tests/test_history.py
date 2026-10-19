"""History list visibility scoped by precheck.view_all_jobs."""

import pytest
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.urls import reverse
from users.models import User
from users.permissions import ADMIN, MANAGER, OPERATOR, VIEW_ALL_JOBS_PERM

from ep_import.models import ImportJob, ImportJobStatus
from precheck.models import (
    CheckAnalysis,
    CheckAnalysisStatus,
    CheckExecution,
    CheckExecutionScope,
    CheckExecutionStatus,
)
from precheck.services.analysis import SESSION_ANALYSIS_KEY

pytestmark = pytest.mark.django_db


def _grant(user, *codenames, app_label="precheck"):
    for codename in codenames:
        perm = Permission.objects.get(content_type__app_label=app_label, codename=codename)
        user.user_permissions.add(perm)
    return User.objects.get(pk=user.pk)


def _execution(*, owner, site="SITE_A", technology="5G", status=CheckExecutionStatus.SUCCESS):
    job = ImportJob.objects.create(
        original_filename=f"{site}.xlsx",
        stored_file="ep_imports/test.xlsx",
        status=ImportJobStatus.SUCCESS,
        created_by=owner,
    )
    analysis = CheckAnalysis.objects.create(
        created_by=owner,
        ep_job=job,
        technology=technology,
        site_name=site,
        selected_cells=["CELL_001"],
        pre_check=True,
        full_check=False,
        status=CheckAnalysisStatus.COMPLETED,
    )
    return CheckExecution.objects.create(
        analysis=analysis,
        created_by=owner,
        scope=CheckExecutionScope.PRECHECK,
        status=status,
        redirect_url="/check/5G/result/",
    )


@pytest.fixture
def owner():
    return User.objects.create_user(
        username="owner",
        password="pass",  # pragma: allowlist secret
        email="owner@example.com",
    )


@pytest.fixture
def other():
    return User.objects.create_user(
        username="other",
        password="pass",  # pragma: allowlist secret
        email="other@example.com",
    )


@pytest.fixture
def manager_with_view_all():
    user = User.objects.create_user(username="mgr", password="pass")  # pragma: allowlist secret
    call_command("seed")
    user.groups.add(Group.objects.get(name=MANAGER))
    return User.objects.get(pk=user.pk)


def test_operator_sees_only_own_executions(client, owner, other):
    mine = _execution(owner=owner, site="MINE")
    _execution(owner=other, site="THEIRS")

    client.force_login(owner)
    response = client.get(reverse("precheck:history"))
    assert response.status_code == 200
    assert b"MINE" in response.content
    assert b"THEIRS" not in response.content
    assert response.context["can_view_all_jobs"] is False
    assert mine in response.context["executions"]


def test_view_all_jobs_sees_everyone_and_user_filter(client, owner, other):
    _execution(owner=owner, site="MINE")
    _execution(owner=other, site="THEIRS")
    viewer = _grant(
        User.objects.create_user(username="viewer", password="pass"),  # pragma: allowlist secret
        "view_all_jobs",
    )

    client.force_login(viewer)
    response = client.get(reverse("precheck:history"))
    assert response.status_code == 200
    assert response.context["can_view_all_jobs"] is True
    assert b"MINE" in response.content
    assert b"THEIRS" in response.content
    assert b"User" in response.content

    filtered = client.get(reverse("precheck:history"), {"created_by": str(other.pk)})
    assert filtered.status_code == 200
    assert b"THEIRS" in filtered.content
    assert b"MINE" not in filtered.content


def test_created_by_filter_ignored_without_perm(client, owner, other):
    _execution(owner=owner, site="MINE")
    _execution(owner=other, site="THEIRS")

    client.force_login(owner)
    response = client.get(reverse("precheck:history"), {"created_by": str(other.pk)})
    assert response.status_code == 200
    assert b"MINE" in response.content
    assert b"THEIRS" not in response.content


def test_manager_seed_includes_view_all_jobs(manager_with_view_all, client):
    assert manager_with_view_all.has_perm(VIEW_ALL_JOBS_PERM)
    client.force_login(manager_with_view_all)
    assert client.get(reverse("precheck:history")).status_code == 200


def test_operator_seed_excludes_view_all_jobs():
    call_command("seed")
    operator = User.objects.create_user(username="op2", password="pass")  # pragma: allowlist secret
    operator.groups.add(Group.objects.get(name=OPERATOR))
    operator = User.objects.get(pk=operator.pk)
    assert not operator.has_perm(VIEW_ALL_JOBS_PERM)

    admin = User.objects.create_user(username="adm2", password="pass")  # pragma: allowlist secret
    admin.groups.add(Group.objects.get(name=ADMIN))
    admin = User.objects.get(pk=admin.pk)
    assert admin.has_perm(VIEW_ALL_JOBS_PERM)


def test_history_in_sidebar_for_authenticated(client, owner):
    client.force_login(owner)
    response = client.get(reverse("precheck:history"))
    assert response.status_code == 200
    assert b">History<" in response.content
    assert reverse("precheck:history").encode() in response.content


def test_anonymous_redirected(client):
    response = client.get(reverse("precheck:history"))
    assert response.status_code == 302


def test_status_filter(client, owner):
    _execution(owner=owner, site="OK", status=CheckExecutionStatus.SUCCESS)
    _execution(owner=owner, site="BAD", status=CheckExecutionStatus.FAILED)

    client.force_login(owner)
    response = client.get(reverse("precheck:history"), {"status": "failed"})
    assert b"BAD" in response.content
    assert b"OK" not in response.content


def test_history_open_sets_session_for_owner(client, owner):
    execution = _execution(owner=owner, site="MINE")
    other_analysis_id = _execution(owner=owner, site="LATER").analysis_id

    client.force_login(owner)
    # Simulate a newer active analysis in session (common after another run).
    session = client.session
    session[SESSION_ANALYSIS_KEY] = str(other_analysis_id)
    session.save()

    response = client.get(reverse("precheck:history_open", args=[execution.pk]))
    assert response.status_code == 302
    assert response["Location"] == execution.redirect_url
    assert client.session[SESSION_ANALYSIS_KEY] == str(execution.analysis_id)


def test_history_open_view_all_jobs_can_open_others(client, owner, other):
    theirs = _execution(owner=other, site="THEIRS")
    viewer = _grant(
        User.objects.create_user(username="viewer2", password="pass"),  # pragma: allowlist secret
        "view_all_jobs",
    )

    client.force_login(viewer)
    response = client.get(reverse("precheck:history_open", args=[theirs.pk]))
    assert response.status_code == 302
    assert response["Location"] == theirs.redirect_url
    assert client.session[SESSION_ANALYSIS_KEY] == str(theirs.analysis_id)


def test_history_open_denied_without_view_all_jobs(client, owner, other):
    theirs = _execution(owner=other, site="THEIRS")

    client.force_login(owner)
    response = client.get(reverse("precheck:history_open", args=[theirs.pk]))
    assert response.status_code == 404


def test_history_open_rejects_external_redirect_url(client, owner):
    execution = _execution(owner=owner, site="MINE")
    execution.redirect_url = "https://evil.example/phish"
    execution.save(update_fields=["redirect_url"])

    client.force_login(owner)
    response = client.get(reverse("precheck:history_open", args=[execution.pk]))
    assert response.status_code == 302
    assert response["Location"] == reverse("precheck:result", kwargs={"technology": "5G"})
    assert client.session[SESSION_ANALYSIS_KEY] == str(execution.analysis_id)


def test_history_table_links_via_history_open(client, owner):
    execution = _execution(owner=owner, site="MINE")

    client.force_login(owner)
    response = client.get(reverse("precheck:history"))
    open_url = reverse("precheck:history_open", args=[execution.pk]).encode()
    assert open_url in response.content
    assert execution.redirect_url.encode() not in response.content
