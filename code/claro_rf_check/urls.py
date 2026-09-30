from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, register_converter

from claro_rf_check.converters import TechnologyConverter
from claro_rf_check.health import HealthzView, ReadyzView

register_converter(TechnologyConverter, "tech")

handler404 = "home.views.custom_404"

claro_rf_patterns = [
    # SSO (Core Connect)
    path("sso/", include("users.urls")),
]

urlpatterns = [
    path("healthz", HealthzView.as_view(), name="healthz"),
    path("readyz", ReadyzView.as_view(), name="readyz"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("admin/", admin.site.urls),
    path("claro-rf/", include(claro_rf_patterns)),
    path("", include("precheck.urls")),
    path("", include("poscheck.urls")),
    path("", include("reports.urls")),
    path("", include("ep_import.urls")),
    path("", include("combined.urls")),
    path("", include("home.urls")),
]

if settings.DEBUG and "django_browser_reload" in settings.INSTALLED_APPS:
    urlpatterns += [path("__reload__/", include("django_browser_reload.urls"))]
    if "debug_toolbar" in settings.INSTALLED_APPS:
        urlpatterns += [path("__debug__/", include("debug_toolbar.urls"))]

# Media is local only in DEBUG. Production serves the private bucket, not this app.
# Static files are served by WhiteNoise, not django.views.static.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
