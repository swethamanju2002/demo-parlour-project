from django.contrib import admin

from .models import Product, ProductCategory, Purchase, PurchaseItem, StockMovement, Supplier


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "order", "is_active")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "contact_person", "phone", "is_active")
    search_fields = ("name", "contact_person", "phone")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "category", "quantity_on_hand", "reorder_level", "selling_price", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("name", "sku")
    readonly_fields = ("quantity_on_hand",)   # stock changes go through inventory.services only


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("created_at", "product", "movement_type", "reason", "change", "quantity_after", "created_by")
    list_filter = ("movement_type", "reason")
    search_fields = ("product__name", "product__sku", "reference")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    extra = 0
    can_delete = False
    readonly_fields = ("product", "product_name", "quantity", "unit_cost", "line_total")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    """View-only: purchases are created and received through the admin panel so stock stays consistent."""
    list_display = ("purchase_number", "supplier", "purchase_date", "status", "total_amount")
    list_filter = ("status",)
    search_fields = ("purchase_number", "invoice_number", "supplier__name")
    inlines = [PurchaseItemInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
