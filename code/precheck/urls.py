from django.urls import path

from precheck import views
from precheck.history_views import HistoryListView, open_execution

app_name = "precheck"

urlpatterns = [
    path("check/history/", HistoryListView.as_view(), name="history"),
    path("check/history/<uuid:execution_id>/", open_execution, name="history_open"),
    path("check/<tech:technology>/returns/", views.import_returns, name="import_returns"),
    path(
        "check/<tech:technology>/returns/precheck/",
        views.upload_precheck_return,
        name="upload_precheck_return",
    ),
    path("check/<tech:technology>/process/", views.process, name="process"),
    path(
        "check/executions/<uuid:execution_id>/",
        views.execution_status,
        name="execution_status",
    ),
    path("check/<tech:technology>/result/", views.result, name="result"),
    path("check/<tech:technology>/failure/", views.failure, name="failure"),
]
