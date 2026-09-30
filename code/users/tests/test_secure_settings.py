import os
import subprocess
import sys

import pytest
from django.core.exceptions import ImproperlyConfigured

from claro_rf_check.settings.secure import apply_secure_settings


@pytest.fixture
def config(monkeypatch):
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", "rf.example.com")
    monkeypatch.delenv("CORE_CONNECT_SSO_DEV", raising=False)
    monkeypatch.delenv("DJANGO_TRUST_PROXY_SSL_HEADER", raising=False)
    monkeypatch.delenv("CSRF_TRUSTED_ORIGINS", raising=False)
    return {
        "CORE_CONNECT_SSO_ENVIRONMENT": "staging",
        "CORE_CONNECT_SSO_ISSUER": "https://core.example.com",
        "CORE_CONNECT_SSO_CLIENT_ID": "claro-rf",
        "CORE_CONNECT_SSO_REDIRECT_URI": "https://rf.example.com/claro-rf/sso/callback/",
        "CORE_CONNECT_SSO_INTERNAL_ISSUER": "https://internal.example.com",
        "CORE_CONNECT_SSO_ALLOW_INSECURE_TRANSPORT": True,
        "CORE_CONNECT_SSO_REFRESH_FAILURE_ACTION": "keep_local_session",
        "SESSION_COOKIE_SAMESITE": "Lax",
    }


def test_secure_settings_force_cookies_https_and_logout(config):
    apply_secure_settings(config)
    assert config["SESSION_COOKIE_SECURE"] and config["SESSION_COOKIE_HTTPONLY"]
    assert config["CSRF_COOKIE_SECURE"] and config["SECURE_SSL_REDIRECT"]
    assert config["CORE_CONNECT_SSO_ALLOW_INSECURE_TRANSPORT"] is False
    assert config["CORE_CONNECT_SSO_REFRESH_FAILURE_ACTION"] == "logout"
    assert "SECURE_PROXY_SSL_HEADER" not in config


@pytest.mark.parametrize(
    "name", ["CORE_CONNECT_SSO_ISSUER", "CORE_CONNECT_SSO_REDIRECT_URI", "CORE_CONNECT_SSO_INTERNAL_ISSUER"]
)
@pytest.mark.parametrize(
    "url",
    [
        "http://core.example.com",
        "https://user:password@core.example.com",  # pragma: allowlist secret -- synthetic rejection-test URL
        "https://:password@core.example.com",
        "https://core.example.com:bad",
    ],
)
def test_invalid_transport_urls_are_rejected(config, name, url):
    config[name] = url
    with pytest.raises(ImproperlyConfigured, match=name):
        apply_secure_settings(config)


@pytest.mark.parametrize(
    "name", ["CORE_CONNECT_SSO_ISSUER", "CORE_CONNECT_SSO_CLIENT_ID", "CORE_CONNECT_SSO_REDIRECT_URI"]
)
def test_missing_required_settings_are_rejected(config, name):
    config[name] = " "
    with pytest.raises(ImproperlyConfigured, match=name):
        apply_secure_settings(config)


@pytest.mark.parametrize("environment", ["", "development", "dev"])
def test_non_secure_environments_are_rejected(config, environment):
    config["CORE_CONNECT_SSO_ENVIRONMENT"] = environment
    with pytest.raises(ImproperlyConfigured, match="CORE_CONNECT_SSO_ENVIRONMENT"):
        apply_secure_settings(config)


def test_prod_alias_is_normalized(config):
    config["CORE_CONNECT_SSO_ENVIRONMENT"] = " PROD "
    apply_secure_settings(config)
    assert config["CORE_CONNECT_SSO_ENVIRONMENT"] == "production"


def test_mock_sso_is_rejected(config, monkeypatch):
    monkeypatch.setenv("CORE_CONNECT_SSO_DEV", "true")
    with pytest.raises(ImproperlyConfigured, match="CORE_CONNECT_SSO_DEV"):
        apply_secure_settings(config)


@pytest.mark.parametrize("hosts", ["", "*", ".example.com", "other.example.com"])
def test_redirect_requires_an_explicit_allowed_host(config, monkeypatch, hosts):
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", hosts)
    with pytest.raises(ImproperlyConfigured, match="DJANGO_ALLOWED_HOSTS"):
        apply_secure_settings(config)


@pytest.mark.parametrize(
    "path", ["/wrong/callback/", "/claro-rf/sso/callback/?next=x", "/claro-rf/sso/callback/#fragment"]
)
def test_redirect_must_reach_the_actual_callback(config, path):
    config["CORE_CONNECT_SSO_REDIRECT_URI"] = "https://rf.example.com" + path
    with pytest.raises(ImproperlyConfigured, match="CORE_CONNECT_SSO_REDIRECT_URI"):
        apply_secure_settings(config)


def test_insecure_samesite_is_rejected(config):
    config["SESSION_COOKIE_SAMESITE"] = "None"
    with pytest.raises(ImproperlyConfigured, match="SESSION_COOKIE_SAMESITE"):
        apply_secure_settings(config)


def test_trusted_tls_proxy_is_explicit(config, monkeypatch):
    monkeypatch.setenv("DJANGO_TRUST_PROXY_SSL_HEADER", "true")
    apply_secure_settings(config)
    assert config["SECURE_PROXY_SSL_HEADER"] == ("HTTP_X_FORWARDED_PROTO", "https")


@pytest.mark.parametrize("module", ["staging", "production"])
def test_real_settings_modules_apply_secure_policy(config, monkeypatch, module):
    for name, value in config.items():
        if name.startswith("CORE_CONNECT_SSO_"):
            monkeypatch.setenv(name, str(value))
    if module == "production":
        monkeypatch.setenv("CORE_CONNECT_SSO_ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "ci-settings-module-secret")  # pragma: allowlist secret
    monkeypatch.setenv("USE_OBS_MEDIA", "True")
    monkeypatch.setenv("OBS_BUCKET_NAME", "claro-rf-check")
    monkeypatch.setenv("OBS_ENDPOINT", "https://obs.example.com")
    monkeypatch.setenv("OBS_ACCESS_KEY", "ak")
    monkeypatch.setenv("OBS_SECRET_KEY", "sk")  # pragma: allowlist secret
    monkeypatch.setenv("ALLOWED_HOSTS", "rf.example.com")
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", "rf.example.com")
    monkeypatch.setenv("CSRF_TRUSTED_ORIGINS", "https://rf.example.com")
    # A new interpreter ensures base.py reads this environment, not pytest's cached settings.
    env = dict(os.environ, PYTHONPATH="code")
    source = (
        f"import claro_rf_check.settings.{module} as s; "
        "assert not s.DEBUG; assert s.SESSION_COOKIE_SECURE; "
        "assert not s.CORE_CONNECT_SSO_ALLOW_INSECURE_TRANSPORT; "
        "assert s.CORE_CONNECT_SSO_REFRESH_FAILURE_ACTION == 'logout'"
    )
    result = subprocess.run([sys.executable, "-c", source], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
