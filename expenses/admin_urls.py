from django.urls import path

from . import admin_views as views

urlpatterns = [
    path("expenses/", views.dashboard, name="expense_dashboard"),
    path("expenses/list/", views.expense_list, name="expense_list"),
    path("expenses/add/", views.expense_create, name="expense_create"),
    path("expenses/<int:pk>/edit/", views.expense_edit, name="expense_edit"),
    path("expenses/<int:pk>/delete/", views.expense_delete, name="expense_delete"),

    path("expenses/categories/", views.category_list, name="expense_categories"),
    path("expenses/categories/add/", views.category_create, name="expense_category_create"),
    path("expenses/categories/<int:pk>/edit/", views.category_edit, name="expense_category_edit"),
    path("expenses/categories/<int:pk>/delete/", views.category_delete, name="expense_category_delete"),

    path("expenses/reports/monthly/", views.monthly_report, name="expense_monthly_report"),
    path("expenses/export/", views.expense_export, name="expense_export"),
]