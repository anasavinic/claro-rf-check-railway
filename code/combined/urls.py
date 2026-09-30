from django.urls import path

from combined import views

app_name = "combined"

urlpatterns = [
    path("check/combined/", views.configure, name="configure"),
    path("check/combined/configure/", views.save_configure, name="save_configure"),
    path("check/combined/sites/", views.sites, name="sites"),
    path("check/combined/generate-scripts/", views.generate_scripts, name="generate_scripts"),
    path("check/combined/scripts/", views.scripts, name="scripts"),
    path(
        "check/combined/scripts/download/<str:check_type>/",
        views.download_script,
        name="download_script",
    ),
    path("check/combined/returns/precheck/", views.upload_precheck, name="upload_precheck"),
    path("check/combined/returns/full-check/", views.upload_full_check, name="upload_full_check"),
    path("check/combined/process/", views.process, name="process"),
    path("check/combined/process/status/", views.process_status, name="process_status"),
    path("check/combined/result/", views.result, name="result"),
    path("check/combined/failure/", views.failure, name="failure"),
]
