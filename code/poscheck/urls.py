from django.urls import path

from poscheck import views

app_name = "poscheck"

urlpatterns = [
    path("check/returns/full-check/", views.upload_full_check_return, name="upload_full_check_return"),
    path("check/full-check/process/", views.process, name="process"),
    path("check/full-check/result/", views.result, name="result"),
    path("check/full-check/failure/", views.failure, name="failure"),
]
