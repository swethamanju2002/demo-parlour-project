from django.urls import path

from . import admin_views

app_name = "admin_panel"

urlpatterns = [path("", admin_views.dashboard, name="dashboard")]
