"""Restore SDK-authenticated sessions without a local activation gate."""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend


class CoreConnectBackend(BaseBackend):
    def get_user(self, user_id):
        user = get_user_model().objects.filter(pk=user_id).first()
        if user is not None and user.core_connect_issuer and user.core_connect_sub:
            return user
        return None
