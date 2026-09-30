"""Consumer regressions against the installed SDK, without a live IdP."""

import time
from dataclasses import replace
from unittest.mock import Mock, patch

import jwt
import pytest
from core_connect_sso import CoreConnectClient, CoreConnectSSOError, Identity, TokenSet
from core_connect_sso.contrib.django.views import (
    SESSION_ACCESS_TOKEN_KEY,
    SESSION_REFRESH_TOKEN_KEY,
    SESSION_STATE_KEY,
    SESSION_VERIFIER_KEY,
)
from core_connect_sso.dev import DEFAULT_DEV_SUB, DEV_CODE
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import BACKEND_SESSION_KEY, SESSION_KEY, authenticate, get_user_model
from django.db import IntegrityError, transaction
from django.test import Client, RequestFactory
from django.urls import path
from rest_framework.response import Response
from rest_framework.views import APIView
from users.backends import CoreConnectBackend
from users.sso import map_core_connect_identity, username_from_identity

pytestmark = pytest.mark.django_db
User = get_user_model()
LOGIN = "/claro-rf/sso/login/"
CALLBACK = "/claro-rf/sso/callback/"
LOGOUT = "/claro-rf/sso/logout/"


class SessionProbe(APIView):
    def get(self, request):
        return Response({"user": request.user.pk})

    def post(self, request):
        return Response({"user": request.user.pk})


# Test-only API: the scaffold has DRF defaults but no business API endpoints yet.
urlpatterns = [path("probe/", SessionProbe.as_view())]


@pytest.fixture
def identity():
    raw = {
        "ver": 1,
        "iss": settings.CORE_CONNECT_SSO_ISSUER,
        "sub": "alice-id",
        "email": "alice@example.com",
        "name": "Alice Example",
        "org_ids": [],
        "roles": ["Admin"],
    }
    return Identity(
        ver=1,
        issuer=raw["iss"],
        sub=raw["sub"],
        email=raw["email"],
        name=raw["name"],
        org_ids=[],
        roles=raw["roles"],
        raw=raw,
    )


@pytest.fixture
def mapping_request():
    request = RequestFactory().get(CALLBACK)
    request.session = {}
    return request


@pytest.fixture
def bound_user(identity, mapping_request):
    return map_core_connect_identity(identity, mapping_request)


@pytest.fixture
def complete_login():
    def complete(client):
        response = client.get(LOGIN)
        assert response.status_code == 302
        state = client.session[SESSION_STATE_KEY]
        return client.get(CALLBACK, {"code": DEV_CODE, "state": state})

    return complete


def test_provisioning_is_idempotent_and_does_not_assign_roles(identity, mapping_request):
    first = map_core_connect_identity(identity, mapping_request)
    second = map_core_connect_identity(identity, mapping_request)
    assert first.pk == second.pk
    assert User.objects.count() == 1
    assert first.username == username_from_identity(identity.issuer, identity.sub)
    assert first.email == identity.email
    assert not first.has_usable_password()
    assert not first.is_staff and not first.is_superuser
    assert not first.groups.exists() and not first.user_permissions.exists()
    assert "sso_just_provisioned" not in mapping_request.session


def test_same_subject_in_distinct_issuers_does_not_collide(identity, mapping_request, bound_user):
    other = map_core_connect_identity(replace(identity, issuer="https://other.example"), mapping_request)
    assert other.pk != bound_user.pk
    assert other.username != bound_user.username


def test_email_never_links_an_unbound_or_different_sso_user(identity, mapping_request, bound_user):
    local = User.objects.create_user(username="local", email=identity.email)
    other = map_core_connect_identity(replace(identity, sub="other-id"), mapping_request)
    assert len({local.pk, bound_user.pk, other.pk}) == 3
    local.refresh_from_db()
    assert local.core_connect_sub is None


def test_profile_changes_and_removals_are_synchronized(identity, mapping_request, bound_user):
    bound_user.avatar_url = "https://core.example/old-avatar"
    bound_user.set_password("old-local-password")
    bound_user.save()
    result = map_core_connect_identity(replace(identity, email="new@example.com", name="Alice"), mapping_request)
    result.refresh_from_db()
    assert result.email == "new@example.com"
    assert result.first_name == "Alice" and result.last_name == ""
    assert result.avatar_url == ""
    assert not result.has_usable_password()
    result = map_core_connect_identity(replace(identity, email="", name=""), mapping_request)
    assert result.email == result.first_name == result.last_name == ""


def test_profile_updates_picture_and_bounds_names(identity, mapping_request):
    raw = dict(identity.raw, picture="https://core.example/avatar")
    user = map_core_connect_identity(replace(identity, name="A" * 200 + " " + "B" * 200, raw=raw), mapping_request)
    assert user.avatar_url == raw["picture"]
    assert len(user.first_name) == len(user.last_name) == 150


@pytest.mark.parametrize(
    "field,value",
    [
        ("issuer", None),
        ("issuer", " "),
        ("sub", None),
        ("sub", " "),
        ("issuer", "x" * 256),
        ("sub", "x" * 65),
        ("email", "x" * 255),
    ],
)
def test_invalid_identity_is_rejected_before_persistence(identity, mapping_request, field, value):
    with pytest.raises(CoreConnectSSOError):
        map_core_connect_identity(replace(identity, **{field: value}), mapping_request)
    assert not User.objects.exists()


def test_database_identity_constraint(bound_user):
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create(
            username="duplicate",
            core_connect_issuer=bound_user.core_connect_issuer,
            core_connect_sub=bound_user.core_connect_sub,
        )
    assert User.objects.count() == 1


def test_create_race_recovers_via_savepoint_and_syncs_winner(identity, mapping_request, bound_user):
    # Simulate a stale first read, then use the real database uniqueness error.
    with patch("users.sso._get_by_issuer_sub", side_effect=[None, bound_user]):
        user = map_core_connect_identity(replace(identity, name="Updated Name"), mapping_request)
    assert user.pk == bound_user.pk
    user.refresh_from_db()
    assert user.first_name == "Updated"
    assert User.objects.count() == 1


def test_username_conflict_does_not_link_an_unrelated_user(identity, mapping_request):
    User.objects.create_user(username=username_from_identity(identity.issuer, identity.sub))
    with pytest.raises(CoreConnectSSOError):
        map_core_connect_identity(identity, mapping_request)
    assert User.objects.count() == 1
    assert User.objects.get().core_connect_sub is None


def test_full_dev_login_persists_session_and_reuses_user(client, complete_login):
    assert complete_login(client).url == "/"
    assert client.session[BACKEND_SESSION_KEY] == settings.CORE_CONNECT_SSO_AUTH_BACKEND
    assert SESSION_ACCESS_TOKEN_KEY in client.session
    assert SESSION_REFRESH_TOKEN_KEY in client.session
    assert SESSION_STATE_KEY not in client.session and SESSION_VERIFIER_KEY not in client.session
    assert client.get("/").status_code == 200
    assert complete_login(client).url == "/"
    assert User.objects.count() == 1


def test_locally_inactive_user_stays_authenticated_after_callback(client, complete_login):
    existing = User.objects.create_user(
        username="inactive",
        core_connect_issuer=settings.CORE_CONNECT_SSO_ISSUER,
        core_connect_sub=DEFAULT_DEV_SUB,
        is_active=False,
    )
    assert complete_login(client).status_code == 302
    response = client.get("/")
    assert response.status_code == 200
    assert response.wsgi_request.user.pk == existing.pk
    existing.refresh_from_db()
    assert existing.is_active is False


def test_sso_backend_does_not_authenticate_local_credentials(bound_user):
    dummy_password = "local-password"  # pragma: allowlist secret -- synthetic test credential
    assert CoreConnectBackend().authenticate(None, username=bound_user.username, password=dummy_password) is None
    local = User.objects.create_user(username="local", password=dummy_password, is_active=False)
    assert CoreConnectBackend().get_user(local.pk) is None
    assert authenticate(username=local.username, password=dummy_password) is None


def test_drf_uses_the_same_sso_policy_and_keeps_csrf(settings, bound_user):
    settings.ROOT_URLCONF = __name__
    bound_user.is_active = False
    bound_user.save(update_fields=["is_active"])
    client = Client(enforce_csrf_checks=True)
    assert client.get("/probe/").status_code == 403
    client.force_login(bound_user, backend=settings.CORE_CONNECT_SSO_AUTH_BACKEND)
    _set_tokens(client, access=_stored_token(time.time() + 3600))
    response = client.get("/probe/")
    assert response.status_code == 200 and response.json()["user"] == bound_user.pk
    assert client.post("/probe/").status_code == 403
    csrf = "a" * 32
    client.cookies[settings.CSRF_COOKIE_NAME] = csrf
    assert client.post("/probe/", HTTP_X_CSRFTOKEN=csrf).status_code == 200
    _set_tokens(client, access=_stored_token(1))
    assert client.get("/probe/").status_code == 403


def test_admin_cannot_edit_bound_identity_or_activation(bound_user):
    registered = admin.site._registry[User]
    request = RequestFactory().get("/admin/")
    assert {"core_connect_issuer", "core_connect_sub", "is_active"} <= set(
        registered.get_readonly_fields(request, bound_user)
    )
    assert "is_active" not in registered.get_readonly_fields(request, User(username="local"))


@pytest.mark.parametrize("failure", ["wrong_state", "missing_state", "missing_code", "missing_verifier", "oauth_error"])
def test_callback_rejects_invalid_or_failed_oauth_flow(client, failure):
    client.get(LOGIN)
    session = client.session
    params = {"code": DEV_CODE, "state": session[SESSION_STATE_KEY]}
    if failure == "wrong_state":
        params["state"] = "wrong"
    elif failure == "missing_state":
        del params["state"]
    elif failure == "missing_code":
        del params["code"]
    elif failure == "missing_verifier":
        del session[SESSION_VERIFIER_KEY]
        session.save()
    else:
        params["error"] = "access_denied"
    response = client.get(CALLBACK, params)
    assert response.status_code == 400
    assert not User.objects.exists()
    assert SESSION_KEY not in client.session
    assert SESSION_STATE_KEY not in client.session


def test_callback_state_is_single_use(client, complete_login):
    client.get(LOGIN)
    params = {"code": DEV_CODE, "state": client.session[SESSION_STATE_KEY]}
    assert client.get(CALLBACK, params).status_code == 302
    assert client.get(CALLBACK, params).status_code == 400
    assert User.objects.count() == 1


@pytest.mark.parametrize("next_url", ["https://other.example/", "//other.example/"])
def test_login_rejects_external_next(client, next_url):
    client.get(LOGIN, {"next": next_url})
    response = client.get(CALLBACK, {"code": DEV_CODE, "state": client.session[SESSION_STATE_KEY]})
    assert response.url == "/"


def test_logout_requires_post_and_csrf_and_clears_session(complete_login):
    client = Client(enforce_csrf_checks=True)
    complete_login(client)
    assert client.get(LOGOUT).status_code == 405
    assert client.post(LOGOUT).status_code == 403
    assert SESSION_KEY in client.session
    client.get("/")
    csrf = client.cookies[settings.CSRF_COOKIE_NAME].value
    tokens = (client.session[SESSION_ACCESS_TOKEN_KEY], client.session[SESSION_REFRESH_TOKEN_KEY])
    sdk_client = Mock()
    sdk_client.revoke.side_effect = CoreConnectSSOError("IdP unavailable")
    with patch("core_connect_sso.contrib.django.views.get_client", return_value=sdk_client):
        response = client.post(LOGOUT, HTTP_X_CSRFTOKEN=csrf)
    assert response.url == LOGIN
    sdk_client.revoke.assert_any_call(tokens[0], token_type_hint="access_token")
    sdk_client.revoke.assert_any_call(tokens[1], token_type_hint="refresh_token")
    assert SESSION_KEY not in client.session
    assert SESSION_ACCESS_TOKEN_KEY not in client.session and SESSION_REFRESH_TOKEN_KEY not in client.session
    assert client.get("/").status_code == 302


def _set_tokens(client, *, access, refresh=None):
    session = client.session
    session[SESSION_ACCESS_TOKEN_KEY] = access
    if refresh:
        session[SESSION_REFRESH_TOKEN_KEY] = refresh
    else:
        session.pop(SESSION_REFRESH_TOKEN_KEY, None)
    session.save()


def _stored_token(expires):
    # Only for lifetime checks on a server-side session, never callback verification.
    return jwt.encode({"exp": expires}, key="", algorithm="none")


@pytest.mark.parametrize("access", [None, "malformed", _stored_token(1)])
def test_missing_or_expired_token_without_refresh_ends_sso_session(client, bound_user, access):
    client.force_login(bound_user, backend=settings.CORE_CONNECT_SSO_AUTH_BACKEND)
    _set_tokens(client, access=access)
    assert client.get("/").status_code == 302
    assert SESSION_KEY not in client.session


def test_valid_access_without_refresh_remains_valid_until_expiry(client, bound_user):
    client.force_login(bound_user, backend=settings.CORE_CONNECT_SSO_AUTH_BACKEND)
    _set_tokens(client, access=_stored_token(time.time() + 3600))
    with patch("core_connect_sso.contrib.django.middleware.get_client") as get_client:
        assert client.get("/").status_code == 200
    get_client.assert_not_called()


def test_refresh_rotates_tokens_and_syncs_profile(client, bound_user, identity):
    client.force_login(bound_user, backend=settings.CORE_CONNECT_SSO_AUTH_BACKEND)
    _set_tokens(client, access=_stored_token(1), refresh="old-refresh")
    new_access = _stored_token(time.time() + 3600)
    sdk_client = Mock()
    sdk_client.refresh.return_value = TokenSet(access_token=new_access, refresh_token="new-refresh")
    sdk_client.verify_access_token.return_value = replace(identity, name="New Name", email="new@example.com")
    with patch("core_connect_sso.contrib.django.middleware.get_client", return_value=sdk_client):
        assert client.get("/").status_code == 200
    sdk_client.refresh.assert_called_once_with("old-refresh")
    sdk_client.verify_access_token.assert_called_once_with(new_access)
    assert client.session[SESSION_ACCESS_TOKEN_KEY] == new_access
    assert client.session[SESSION_REFRESH_TOKEN_KEY] == "new-refresh"
    bound_user.refresh_from_db()
    assert bound_user.first_name == "New" and bound_user.email == "new@example.com"


@pytest.mark.parametrize("failure", ["refresh", "verify_access_token"])
def test_idp_rejection_or_invalid_refreshed_token_logs_out(client, bound_user, failure):
    client.force_login(bound_user, backend=settings.CORE_CONNECT_SSO_AUTH_BACKEND)
    _set_tokens(client, access=_stored_token(1), refresh="old-refresh")
    sdk_client = Mock()
    sdk_client.refresh.return_value = TokenSet(access_token="new-access", refresh_token="new-refresh")
    getattr(sdk_client, failure).side_effect = CoreConnectSSOError("invalid_grant: inactive or revoked")
    with patch("core_connect_sso.contrib.django.middleware.get_client", return_value=sdk_client):
        assert client.get("/").status_code == 302
    assert SESSION_KEY not in client.session
    assert SESSION_ACCESS_TOKEN_KEY not in client.session and SESSION_REFRESH_TOKEN_KEY not in client.session


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.mark.parametrize("failure", [None, "signature", "iss", "aud", "exp", "ver", "sub", "long_sub"])
def test_callback_uses_real_sdk_jwt_verification(client, identity, signing_key, failure):
    # Mock only IdP transport; exercise the real SDK signature/claims verifier.
    client.get(LOGIN)
    verifier = client.session[SESSION_VERIFIER_KEY]
    claims = dict(
        identity.raw, aud=settings.CORE_CONNECT_SSO_CLIENT_ID, iat=int(time.time()), exp=int(time.time()) + 3600
    )
    signing = signing_key
    if failure == "signature":
        signing = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    elif failure in {"iss", "aud"}:
        claims[failure] = "https://wrong.example"
    elif failure == "exp":
        claims["exp"] = 1
    elif failure == "ver":
        claims["ver"] = 999
    elif failure == "sub":
        del claims["sub"]
    elif failure == "long_sub":
        claims["sub"] = "x" * 65
    token = jwt.encode(claims, signing, algorithm="RS256", headers={"kid": "consumer-test-key"})
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key(), as_dict=True)
    transport = Mock()
    transport.get_jwks.return_value = {"keys": [dict(jwk, kid="consumer-test-key", alg="RS256")]}
    transport.fetch_token.return_value = {"access_token": token, "refresh_token": "refresh"}
    sdk_client = CoreConnectClient(
        issuer=identity.issuer,
        client_id=settings.CORE_CONNECT_SSO_CLIENT_ID,
        redirect_uri=settings.CORE_CONNECT_SSO_REDIRECT_URI,
        transport=transport,
        dev_mode=False,
        environment="development",
    )
    with patch("core_connect_sso.contrib.django.views.get_client", return_value=sdk_client):
        response = client.get(CALLBACK, {"code": "authorization-code", "state": client.session[SESSION_STATE_KEY]})
    transport.fetch_token.assert_called_once_with(code="authorization-code", code_verifier=verifier)
    if failure:
        assert response.status_code == 400
        assert response["Cache-Control"] == "no-store"
        assert not User.objects.exists()
        assert SESSION_KEY not in client.session
    else:
        assert response.url == "/"
        assert User.objects.get().core_connect_sub == identity.sub
        assert client.get("/").status_code == 200
