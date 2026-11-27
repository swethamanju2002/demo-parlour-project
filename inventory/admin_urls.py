"""Inventory admin routes. Appended to bookings/admin_urls.py so everything stays in the `admin_panel` namespace."""
from django.urls import path

from . import admin_views as v
from . import reports as r

urlpatterns = [
    path("inventory/", r.dashboard, name="inventory_dashboard"),
    path("inventory/products/", v.product_list, name="inventory_products"),
    path("inventory/products/create/", v.product_create, name="inventory_product_create"),
    path("inventory/products/<int:product_id>/edit/", v.product_edit, name="inventory_product_edit"),
    path("inventory/products/<int:product_id>/toggle/", v.product_toggle_active, name="inventory_product_toggle"),
    path("inventory/products/<int:product_id>/", v.product_detail, name="inventory_product_detail"),
    path("inventory/products/<int:product_id>/stock-in/", v.stock_in, name="inventory_stock_in"),
    path("inventory/products/<int:product_id>/stock-out/", v.stock_out, name="inventory_stock_out"),
    path("inventory/products/<int:product_id>/adjust/", v.stock_adjust, name="inventory_stock_adjust"),
    path("inventory/movements/", v.movement_list, name="inventory_movements"),
    path("inventory/categories/", v.category_list, name="inventory_categories"),
    path("inventory/categories/create/", v.category_create, name="inventory_category_create"),
    path("inventory/categories/<int:category_id>/edit/", v.category_edit, name="inventory_category_edit"),
    path("inventory/categories/<int:category_id>/toggle/", v.category_toggle_active, name="inventory_category_toggle"),
    path("inventory/suppliers/", v.supplier_list, name="inventory_suppliers"),
    path("inventory/suppliers/create/", v.supplier_create, name="inventory_supplier_create"),
    path("inventory/suppliers/<int:supplier_id>/edit/", v.supplier_edit, name="inventory_supplier_edit"),
    path("inventory/suppliers/<int:supplier_id>/toggle/", v.supplier_toggle_active, name="inventory_supplier_toggle"),
    path("inventory/purchases/", v.purchase_list, name="inventory_purchases"),
    path("inventory/purchases/create/", v.purchase_create, name="inventory_purchase_create"),
    path("inventory/purchases/<int:purchase_id>/", v.purchase_detail, name="inventory_purchase_detail"),
    path("inventory/purchases/<int:purchase_id>/edit/", v.purchase_edit, name="inventory_purchase_edit"),
    path("inventory/purchases/<int:purchase_id>/order/", v.purchase_order, name="inventory_purchase_order"),
    path("inventory/purchases/<int:purchase_id>/receive/", v.purchase_receive, name="inventory_purchase_receive"),
    path("inventory/purchases/<int:purchase_id>/cancel/", v.purchase_cancel, name="inventory_purchase_cancel"),
    path("inventory/reports/", r.reports_index, name="inventory_reports"),
    path("inventory/reports/stock/", r.report_stock, name="inventory_report_stock"),
    path("inventory/reports/low-stock/", r.report_low_stock, name="inventory_report_low_stock"),
    path("inventory/reports/out-of-stock/", r.report_out_of_stock, name="inventory_report_out_of_stock"),
    path("inventory/reports/movements/", r.report_movements, name="inventory_report_movements"),
    path("inventory/reports/purchases/", r.report_purchases, name="inventory_report_purchases"),
    path("inventory/reports/product-history/", r.report_product_history, name="inventory_report_product_history"),
]
