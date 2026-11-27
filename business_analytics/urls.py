from django.urls import path
from . import views

app_name = "business_analytics"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("export/", views.export_report, name="export"),
]