
from django.contrib import admin

from .models import Invoice, InvoiceItem, Payment


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    readonly_fields = (
        "service_name",
        "unit_price",
        "duration_minutes",
        "line_total",
    )
    can_delete = False


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    readonly_fields = (
        "amount",
        "method",
        "status",
        "transaction_reference",
        "paid_at",
        "recorded_by",
    )
    can_delete = False


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "invoice_number",
        "customer",
        "booking",
        "issue_date",
        "total_amount",
        "status",
    )
    search_fields = (
        "invoice_number",
        "customer__username",
        "customer__email",
        "booking__public_id",
    )
    list_filter = ("status", "issue_date")
    readonly_fields = (
        "invoice_number",
        "booking",
        "customer",
        "subtotal",
        "discount_amount",
        "tax_amount",
        "total_amount",
        "created_at",
        "updated_at",
    )
    inlines = [InvoiceItemInline, PaymentInline]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "invoice",
        "amount",
        "method",
        "status",
        "paid_at",
        "recorded_by",
    )
    search_fields = (
        "invoice__invoice_number",
        "transaction_reference",
    )
    list_filter = ("method", "status", "paid_at")
    readonly_fields = ("created_at",)
