from django.urls import path

from . import client_views

app_name = "client"

urlpatterns = [path("", client_views.dashboard, name="dashboard")]
