"""Inventory admin routes. Appended to bookings/admin_urls.py so everything stays in the `admin_panel` namespace."""
from django.urls import path

from . import admin_views as v

urlpatterns = [
    path("inventory/", v.product_list, name="inventory_products"),
    path("inventory/products/create/", v.product_create, name="inventory_product_create"),
    path("inventory/products/<int:product_id>/edit/", v.product_edit, name="inventory_product_edit"),
    path("inventory/products/<int:product_id>/toggle/", v.product_toggle_active, name="inventory_product_toggle"),
    path("inventory/categories/", v.category_list, name="inventory_categories"),
    path("inventory/categories/create/", v.category_create, name="inventory_category_create"),
    path("inventory/categories/<int:category_id>/edit/", v.category_edit, name="inventory_category_edit"),
    path("inventory/categories/<int:category_id>/toggle/", v.category_toggle_active, name="inventory_category_toggle"),
]
