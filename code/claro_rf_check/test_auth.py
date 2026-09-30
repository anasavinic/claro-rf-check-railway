"""HTTP Basic authentication for the temporary public Railway deployment."""

import base64
import binascii
import secrets

from django.conf import settings
from django.http import HttpResponse, HttpResponseServerError


class TestEnvironmentBasicAuthMiddleware:
    """Protect a temporary public deployment with HTTP Basic authentication."""

    exempt_paths = {"/healthz"}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Railway health probes use an internal Host header that is not in
        # ALLOWED_HOSTS. Answer before the rest of the middleware stack so the
        # probe does not depend on host checks or the TLS redirect.
        if request.path in self.exempt_paths:
            return HttpResponse("ok", content_type="text/plain")

        # Stylesheets and scripts contain no client data. Let WhiteNoise serve
        # them without a challenge so the browser can render the login page.
        if request.path.startswith(settings.STATIC_URL):
            return self.get_response(request)

        if not getattr(settings, "CLARO_RF_TEST_AUTH_ENABLED", False):
            return self.get_response(request)

        expected_username = getattr(settings, "CLARO_RF_TEST_AUTH_USERNAME", "")
        expected_password = getattr(settings, "CLARO_RF_TEST_AUTH_PASSWORD", "")
        if not expected_username or not expected_password:
            return HttpResponseServerError("Test access protection is misconfigured.")

        authorization = request.META.get("HTTP_AUTHORIZATION", "")
        supplied_username, supplied_password = self._credentials(authorization)
        if secrets.compare_digest(supplied_username, expected_username) and secrets.compare_digest(
            supplied_password, expected_password
        ):
            return self.get_response(request)

        response = HttpResponse(status=401)
        response["WWW-Authenticate"] = 'Basic realm="Claro RF Check"'
        return response

    @staticmethod
    def _credentials(authorization: str) -> tuple[str, str]:
        scheme, _, encoded = authorization.partition(" ")
        if scheme.lower() != "basic" or not encoded:
            return "", ""
        try:
            decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
        except (UnicodeDecodeError, binascii.Error):
            return "", ""
        username, separator, password = decoded.partition(":")
        return (username, password) if separator else ("", "")
