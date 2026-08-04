from django.urls import path

from license_client import views

app_name = "license_client"

urlpatterns = [
    path("__license__/status", views.status, name="status"),
]
