
from django.urls import path

from . import views

app_name = "billing"

urlpatterns = [
    path("", views.billing_dashboard, name="dashboard"),
    path("reports/", views.financial_reports, name="reports"),
    path("generate/<int:booking_id>/", views.invoice_generate, name="generate"),
    path("invoice/<int:invoice_id>/", views.invoice_detail, name="invoice_detail"),
    path("invoice/<int:invoice_id>/update/", views.invoice_update, name="invoice_update"),
    path("invoice/<int:invoice_id>/payment/", views.payment_create, name="payment_create"),
    path("payment/<int:payment_id>/status/", views.payment_status_update, name="payment_status_update"),
    path("client/", views.customer_billing, name="customer_billing"),
    path("client/invoice/<int:invoice_id>/", views.customer_invoice_detail, name="customer_invoice_detail"),
]
