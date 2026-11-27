from django.contrib import admin

from .models import Expense, ExpenseCategory


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "category",
        "amount",
        "expense_date",
        "payment_status",
        "payment_method",
    )
    list_filter = (
        "payment_status",
        "payment_method",
        "category",
        "expense_date",
    )
    search_fields = (
        "title",
        "paid_to",
        "reference_number",
    )
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "expense_date"

