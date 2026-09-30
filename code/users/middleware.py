"""Keep SSO sessions bounded by the tokens issued by Core Connect."""

import time

from core_connect_sso.contrib.django.middleware import IdentityRefreshMiddleware as SDKIdentityRefreshMiddleware
from core_connect_sso.contrib.django.views import SESSION_ACCESS_TOKEN_KEY, SESSION_REFRESH_TOKEN_KEY
from core_connect_sso.contrib.identity_refresh import jwt_exp
from django.contrib.auth import logout


class IdentityRefreshMiddleware(SDKIdentityRefreshMiddleware):
    def _maybe_refresh(self, request):
        user = getattr(request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and user.core_connect_issuer
            and user.core_connect_sub
            and not request.session.get(SESSION_REFRESH_TOKEN_KEY)
        ):
            expires = jwt_exp(request.session.get(SESSION_ACCESS_TOKEN_KEY))
            if expires is None or expires <= time.time():
                logout(request)
                return
        super()._maybe_refresh(request)
