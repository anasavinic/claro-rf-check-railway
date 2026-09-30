"""Small application adaptations around the SDK's OAuth flow."""

import logging

from core_connect_sso import CoreConnectSSOError
from core_connect_sso.contrib.django.views import CallbackView as SDKCallbackView
from django.http import HttpResponseBadRequest

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
