from django.urls import path

from users.views import UserDetailView, UserListView, UserUpdateView

app_name = "users"

urlpatterns = [
    path("", UserListView.as_view(), name="list"),
    path("<int:pk>/", UserDetailView.as_view(), name="detail"),
    path("<int:pk>/update/", UserUpdateView.as_view(), name="update"),
]
