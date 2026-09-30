from core_connect_sso.contrib.django.views import LoginView, LogoutView
from django.urls import path

from users.views import CallbackView

urlpatterns = [
    path("login/", LoginView.as_view(), name="core_connect_sso_login"),
    path("callback/", CallbackView.as_view(), name="core_connect_sso_callback"),
    path("logout/", LogoutView.as_view(), name="core_connect_sso_logout"),
]
