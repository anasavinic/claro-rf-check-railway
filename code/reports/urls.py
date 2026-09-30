from django.urls import path

from reports import views

app_name = "reports"

urlpatterns = [
    path("check/reports/<uuid:analysis_id>/export/", views.export_report, name="export"),
    path("check/reports/<uuid:analysis_id>/email/", views.prepare_email, name="email"),
    path("check/combined/reports/export/", views.export_combined_report, name="combined_export"),
    path("check/combined/reports/email/", views.prepare_combined_email, name="combined_email"),
]
