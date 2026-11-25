
from django.urls import path
from staff import admin_views as staff_admin_views
from . import admin_views, admin_appointments
from accounts import admin_customers
from offers import admin_views as offer_admin_views
from services import admin_views as service_admin_views
from billing import views as billing_views

app_name = "admin_panel"

urlpatterns = [
    # Admin dashboard
    path("", admin_views.dashboard, name="dashboard"),

    # Appointment management
    path(
        "appointments/",
        admin_appointments.appointment_list,
        name="appointments",
    ),
    path(
        "appointments/<str:public_id>/",
        admin_appointments.appointment_detail,
        name="appointment_detail",
    ),
    path(
        "appointments/<str:public_id>/update/",
        admin_appointments.update_appointment,
        name="update_appointment",
    ),

    # Customer management
    path(
        "customers/",
        admin_customers.customer_list,
        name="customers",
    ),
    path(
        "customers/<int:customer_id>/",
        admin_customers.customer_detail,
        name="customer_detail",
    ),
        # Service management
    path(
        "services/",
        service_admin_views.service_list,
        name="services",
    ),
    path(
        "services/create/",
        service_admin_views.service_create,
        name="service_create",
    ),
    path(
        "services/<int:service_id>/edit/",
        service_admin_views.service_edit,
        name="service_edit",
    ),
    path(
        "services/<int:service_id>/toggle/",
        service_admin_views.service_toggle_active,
        name="service_toggle_active",
    ),

    # Category management
    path(
        "categories/",
        service_admin_views.category_list,
        name="categories",
    ),
    path(
        "categories/create/",
        service_admin_views.category_create,
        name="category_create",
    ),
    path(
        "categories/<int:category_id>/edit/",
        service_admin_views.category_edit,
        name="category_edit",
    ),
    path(
        "categories/<int:category_id>/toggle/",
        service_admin_views.category_toggle_active,
        name="category_toggle_active",
    ),
        # ==========================================
    # STAFF MANAGEMENT
    # ==========================================

    path(
        "staff/",
        staff_admin_views.staff_list,
        name="staff",
    ),
    path(
        "staff/create/",
        staff_admin_views.staff_create,
        name="staff_create",
    ),
    path(
        "staff/<int:staff_id>/",
        staff_admin_views.staff_detail,
        name="staff_detail",
    ),
    path(
        "staff/<int:staff_id>/edit/",
        staff_admin_views.staff_edit,
        name="staff_edit",
    ),
    path(
        "staff/<int:staff_id>/toggle/",
        staff_admin_views.staff_toggle_active,
        name="staff_toggle_active",
    ),

    # Staff schedules
    path(
        "staff/<int:staff_id>/schedules/create/",
        staff_admin_views.schedule_create,
        name="schedule_create",
    ),
    path(
        "staff/<int:staff_id>/schedules/<int:schedule_id>/edit/",
        staff_admin_views.schedule_edit,
        name="schedule_edit",
    ),
    path(
        "staff/<int:staff_id>/schedules/<int:schedule_id>/delete/",
        staff_admin_views.schedule_delete,
        name="schedule_delete",
    ),

    # Staff leave
    path(
        "staff/<int:staff_id>/leaves/create/",
        staff_admin_views.leave_create,
        name="leave_create",
    ),
    path(
        "staff/<int:staff_id>/leaves/<int:leave_id>/edit/",
        staff_admin_views.leave_edit,
        name="leave_edit",
    ),
    path(
        "staff/<int:staff_id>/leaves/<int:leave_id>/approval/",
        staff_admin_views.leave_toggle_approval,
        name="leave_toggle_approval",
    ),
    path(
        "staff/<int:staff_id>/leaves/<int:leave_id>/delete/",
        staff_admin_views.leave_delete,
        name="leave_delete",
    ),
    # Offer Management
    path(
        "offers/",
        offer_admin_views.offer_list,
        name="offers",
    ),
    path(
        "offers/create/",
        offer_admin_views.offer_create,
        name="offer_create",
    ),
    path(
        "offers/<int:offer_id>/",
        offer_admin_views.offer_detail,
        name="offer_detail",
    ),
    path(
        "offers/<int:offer_id>/edit/",
        offer_admin_views.offer_edit,
        name="offer_edit",
    ),
    path(
        "offers/<int:offer_id>/toggle/",
        offer_admin_views.offer_toggle_active,
        name="offer_toggle_active",
    ),
    
    path("billing/", billing_views.billing_dashboard, name="billing"),
    path("billing/reports/", billing_views.financial_reports, name="billing_reports"),
    path("billing/generate/<int:booking_id>/", billing_views.invoice_generate, name="invoice_generate"),
    path("billing/invoice/<int:invoice_id>/", billing_views.invoice_detail, name="invoice_detail"),
    path("billing/invoice/<int:invoice_id>/update/", billing_views.invoice_update, name="invoice_update"),
    path("billing/invoice/<int:invoice_id>/payment/", billing_views.payment_create, name="payment_create"),
    path("billing/payment/<int:payment_id>/status/", billing_views.payment_status_update, name="payment_status_update"),
    path(
    "billing/create/",
    billing_views.manual_invoice_create,
    name="manual_invoice_create",
),
    
    ]
