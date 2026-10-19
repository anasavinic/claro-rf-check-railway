from django.urls import path

from . import views

app_name = "settings"

urlpatterns = [
    path("", views.SettingsView.as_view(), name="page"),
    path("roles/", views.RoleListView.as_view(), name="roles-list"),
    path("roles/create/", views.RoleCreateView.as_view(), name="roles-create"),
    path("roles/<int:pk>/", views.RoleDetailView.as_view(), name="roles-detail"),
    path("roles/<int:pk>/edit/", views.RoleUpdateView.as_view(), name="roles-update"),
    path("roles/<int:pk>/delete/", views.RoleDeleteView.as_view(), name="roles-delete"),
]
