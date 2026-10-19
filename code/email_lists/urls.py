from django.urls import path

from email_lists import views

app_name = "email_lists"

urlpatterns = [
    path("email-lists/", views.index, name="index"),
    path("email-lists/panel/", views.panel, name="panel"),
    path("email-lists/guide/", views.guide, name="guide"),
    path("email-lists/import/", views.import_csv, name="import_csv"),
    path("email-lists/<int:list_id>/export/", views.export_csv, name="export"),
    path(
        "email-lists/<int:list_id>/addresses/<int:address_id>/delete/",
        views.remove_address,
        name="remove",
    ),
    path("email-lists/<int:list_id>/delete/", views.delete_list, name="delete"),
]
