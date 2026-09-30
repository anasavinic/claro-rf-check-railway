import pytest
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from claro_rf_check.middleware import SecurityHeadersMiddleware
from claro_rf_check.settings.hardening import require_csrf_origins, require_explicit_hosts, require_object_storage


def test_production_rejects_empty_or_wildcard_hosts():
    with pytest.raises(ImproperlyConfigured):
        require_explicit_hosts("")
    with pytest.raises(ImproperlyConfigured):
        require_explicit_hosts("*")
    assert require_explicit_hosts("app.example.com") == ["app.example.com"]


def test_production_requires_csrf_origins_and_object_storage():
    with pytest.raises(ImproperlyConfigured):
        require_csrf_origins("")
    with pytest.raises(ImproperlyConfigured):
        require_object_storage(False)
    assert require_csrf_origins("https://app.example.com") == ["https://app.example.com"]


def test_security_headers_are_omitted_without_a_policy():
    middleware = SecurityHeadersMiddleware(lambda request: HttpResponse("ok"))
    response = middleware(RequestFactory().get("/"))
    assert "Content-Security-Policy" not in response
    assert "Permissions-Policy" not in response


@override_settings(
    CONTENT_SECURITY_POLICY="default-src 'self'",
    PERMISSIONS_POLICY="camera=()",
)
def test_security_headers_are_set_from_settings():
    middleware = SecurityHeadersMiddleware(lambda request: HttpResponse("ok"))
    response = middleware(RequestFactory().get("/"))
    assert response["Content-Security-Policy"] == "default-src 'self'"
    assert "unsafe-inline" not in response["Content-Security-Policy"]
    assert response["Permissions-Policy"] == "camera=()"
