from django.contrib import admin

from .models import Service, ServiceCategory


@admin.register(ServiceCategory)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "order", "is_active")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "duration_minutes", "is_bookable", "is_active")
    list_filter = ("category", "is_active", "is_featured", "is_popular")
    search_fields = ("name",)
