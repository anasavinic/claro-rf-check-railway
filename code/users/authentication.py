"""Use the same SSO identity policy for DRF and Django pages."""

from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY
from rest_framework.authentication import SessionAuthentication


class CoreConnectSessionAuthentication(SessionAuthentication):
    def authenticate(self, request):
        user = getattr(request._request, "user", None)
        session = getattr(request._request, "session", {})
        if (
            user is not None
            and user.is_authenticated
            and session.get(BACKEND_SESSION_KEY) == settings.CORE_CONNECT_SSO_AUTH_BACKEND
        ):
            self.enforce_csrf(request)
            return user, None
        return super().authenticate(request)
