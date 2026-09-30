from django.urls import path

from ep_import import views

app_name = "ep_import"

urlpatterns = [
    path(
        "check/<tech:technology>/sites/",
        views.site_cells,
        name="site_cells",
    ),
    path("check/generate-scripts/", views.generate_scripts, name="generate_scripts"),
    path("check/<tech:technology>/scripts/", views.scripts, name="scripts"),
    path(
        "check/<tech:technology>/scripts/download/<str:check_type>/",
        views.download_script,
        name="download_script",
    ),
    path("ep/upload/", views.upload_ep, name="upload"),
    path("ep/jobs/<uuid:job_id>/", views.job_status, name="job_status"),
    path("ep/jobs/<uuid:job_id>/sites/", views.job_sites, name="job_sites"),
    path("ep/jobs/<uuid:job_id>/cells/", views.job_cells, name="job_cells"),
]
