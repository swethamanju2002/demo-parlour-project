from django.contrib import admin
from .models import (
    AcademyTrainer, Assessment, AssessmentResult, Attendance, Batch, Certificate,
    Course, CourseCategory, CourseModule, Enrollment, ModuleProgress,
)


@admin.register(CourseCategory)
class CourseCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "display_order")
    list_filter = ("is_active",)
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "level", "duration_weeks", "fee", "is_active")
    list_filter = ("category", "level", "is_active")
    search_fields = ("title", "description")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(AcademyTrainer)
class AcademyTrainerAdmin(admin.ModelAdmin):
    list_display = ("user", "expertise", "is_active")
    list_filter = ("is_active",)
    search_fields = ("user__first_name", "user__last_name", "user__username", "expertise")


class EnrollmentInline(admin.TabularInline):
    model = Enrollment
    extra = 0
    autocomplete_fields = ("student",)


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "course", "trainer", "start_date", "end_date", "capacity", "status")
    list_filter = ("status", "course", "start_date")
    search_fields = ("name", "code", "course__title")
    inlines = (EnrollmentInline,)


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "batch", "enrolled_on", "fee_agreed", "status")
    list_filter = ("status", "batch__course", "enrolled_on")
    search_fields = ("student__first_name", "student__last_name", "student__username", "batch__name")
    autocomplete_fields = ("student", "batch")


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "attendance_date", "status", "marked_by")
    list_filter = ("attendance_date", "status", "enrollment__batch")
    search_fields = ("enrollment__student__username", "enrollment__student__first_name")


@admin.register(CourseModule)
class CourseModuleAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "sequence", "estimated_hours", "is_required")
    list_filter = ("course", "is_required")


@admin.register(ModuleProgress)
class ModuleProgressAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "module", "is_completed", "completed_at")
    list_filter = ("is_completed", "module__course")


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "max_score", "pass_score", "is_required_for_certificate", "is_active")
    list_filter = ("course", "is_active", "is_required_for_certificate")


@admin.register(AssessmentResult)
class AssessmentResultAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "assessment", "score", "evaluated_by", "evaluated_at")
    list_filter = ("assessment__course", "evaluated_at")


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ("certificate_number", "enrollment", "issued_on", "issued_by")
    search_fields = ("certificate_number", "enrollment__student__username")
    readonly_fields = ("verification_code",)
