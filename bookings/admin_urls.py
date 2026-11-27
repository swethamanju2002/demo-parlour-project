
from django.urls import path
from staff import admin_views as staff_admin_views
from . import admin_views, admin_appointments
from accounts import admin_customers
from offers import admin_views as offer_admin_views
from services import admin_views as service_admin_views
from billing import views as billing_views
from academy import admin_views as views
from academy import views as p7
from business_analytics import views as analytics_views

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
    name="manual_invoice_create"),
    
    path("academy/", views.academy_dashboard, name="academy_dashboard"),
    path("academy/categories/", views.category_list, name="academy_categories"),
    path("academy/categories/create/", views.category_create, name="academy_category_create"),
    path("academy/categories/<int:category_id>/edit/", views.category_edit, name="academy_category_edit"),
    path("academy/categories/<int:category_id>/toggle/", views.category_toggle, name="academy_category_toggle"),
    path("academy/courses/", views.course_list, name="academy_courses"),
    path("academy/courses/create/", views.course_create, name="academy_course_create"),
    path("academy/courses/<int:course_id>/edit/", views.course_edit, name="academy_course_edit"),
    path("academy/courses/<int:course_id>/toggle/", views.course_toggle, name="academy_course_toggle"),
    path("academy/trainers/", views.trainer_list, name="academy_trainers"),
    path("academy/trainers/create/", views.trainer_create, name="academy_trainer_create"),
    path("academy/trainers/<int:trainer_id>/edit/", views.trainer_edit, name="academy_trainer_edit"),
    path("academy/trainers/<int:trainer_id>/toggle/", views.trainer_toggle, name="academy_trainer_toggle"),
    path("academy/batches/", views.batch_list, name="academy_batches"),
    path("academy/batches/create/", views.batch_create, name="academy_batch_create"),
    path("academy/batches/<int:batch_id>/edit/", views.batch_edit, name="academy_batch_edit"),
    path("academy/batches/<int:batch_id>/advance/", views.batch_toggle, name="academy_batch_advance"),
    
    # ==========================================
    # PHASE 7 — STUDENT ADMISSIONS
    # ==========================================

    path(
        "academy/enrollments/",
        p7.enrollment_list,
        name="academy_enrollments",
    ),
    path(
        "academy/enrollments/create/",
        p7.enrollment_create,
        name="academy_admission_create",
    ),
    path(
        "academy/enrollments/<int:enrollment_id>/",
        p7.enrollment_detail,
        name="academy_enrollment_detail",
    ),
    path(
        "academy/enrollments/<int:enrollment_id>/status/",
        p7.enrollment_status_update,
        name="academy_enrollment_status",
    ),
    path(
        "academy/enrollments/export/",
        p7.enrollment_export,
        name="academy_enrollment_export",
    ),

    # ==========================================
    # STEP 4 — ATTENDANCE
    # ==========================================

    path(
        "academy/attendance/",
        p7.attendance_list,
        name="academy_attendance",
    ),
    path(
        "academy/attendance/batch/<int:batch_id>/",
        p7.attendance_mark,
        name="academy_attendance_mark",
    ),

    # ==========================================
    # STEP 5 — COURSE MODULES
    # ==========================================

    path(
        "academy/modules/",
        p7.module_list,
        name="academy_modules",
    ),
    path(
        "academy/modules/create/",
        p7.module_create,
        name="academy_module_create",
    ),
    path(
        "academy/modules/<int:module_id>/edit/",
        p7.module_edit,
        name="academy_module_edit",
    ),
    path(
        "academy/enrollments/<int:enrollment_id>/modules/<int:module_id>/progress/",
        p7.progress_update,
        name="academy_progress_update",
    ),

    # ==========================================
    # STEP 5 — ASSESSMENTS AND RESULTS
    # ==========================================

    path(
        "academy/assessments/",
        p7.assessment_list,
        name="academy_assessments",
    ),
    path(
        "academy/assessments/create/",
        p7.assessment_create,
        name="academy_assessment_create",
    ),
    path(
        "academy/assessments/<int:assessment_id>/edit/",
        p7.assessment_edit,
        name="academy_assessment_edit",
    ),
    path(
        "academy/enrollments/<int:enrollment_id>/assessments/<int:assessment_id>/result/",
        p7.result_create,
        name="academy_result_create",
    ),

    # ==========================================
    # STEP 6 — CERTIFICATES
    # ==========================================

    path(
        "academy/certificates/",
        p7.certificate_list,
        name="academy_certificates",
    ),
    path(
        "academy/enrollments/<int:enrollment_id>/certificate/issue/",
        p7.certificate_issue,
        name="academy_certificate_issue",
    ),
    path(
        "academy/certificates/verify/<uuid:verification_code>/",
        p7.certificate_verify,
        name="academy_certificate_verify",
    ),

    # ==========================================
    # STEP 6 — REPORTS
    # ==========================================

    path(
        "academy/reports/",
        p7.reports,
        name="academy_reports",
    ),
    # Phase 9 — Business Analytics
    path(
        "analytics/",
        analytics_views.dashboard,
        name="analytics_dashboard",
    ),
    path(
        "analytics/export/",
        analytics_views.export_report,
        name="analytics_export",
    ),

    ]
from inventory.admin_urls import urlpatterns as inventory_urlpatterns
from expenses.admin_urls import urlpatterns as expense_urlpatterns

urlpatterns += inventory_urlpatterns
urlpatterns += expense_urlpatterns