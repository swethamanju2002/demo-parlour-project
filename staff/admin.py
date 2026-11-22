from django.contrib import admin

from .models import StaffLeave, StaffProfile, StaffSchedule


class ScheduleInline(admin.TabularInline):
    model = StaffSchedule
    extra = 0


class LeaveInline(admin.TabularInline):
    model = StaffLeave
    extra = 0


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "title", "is_active", "is_featured", "order")
    list_filter = ("is_active",)
    filter_horizontal = ("services",)
    inlines = [ScheduleInline, LeaveInline]
