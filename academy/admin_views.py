from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.permissions import salon_admin_required
from accounts.models import User
from .forms import BatchForm, CourseCategoryForm, CourseForm, TrainerForm
from .models import AcademyTrainer, Assessment, Attendance, Batch, Certificate, Course, CourseCategory, Enrollment


def _page(request, queryset, per_page=12):
    return Paginator(queryset, per_page).get_page(request.GET.get("page"))


@salon_admin_required
def academy_dashboard(request):
    context = {
        "category_count": CourseCategory.objects.filter(is_active=True).count(),
        "course_count": Course.objects.filter(is_active=True).count(),
        "trainer_count": AcademyTrainer.objects.filter(is_active=True).count(),
        "active_batches": Batch.objects.filter(status__in=(Batch.Status.ENROLLING, Batch.Status.ONGOING)).count(),
        "student_count": Enrollment.objects.filter(status=Enrollment.Status.ACTIVE).values("student_id").distinct().count(),
        "enrollment_count": Enrollment.objects.filter(status=Enrollment.Status.ACTIVE).count(),
        "certificate_count": Certificate.objects.count(),
        "recent_batches": Batch.objects.select_related("course", "trainer__user").order_by("-created_at")[:6],
        "recent_enrollments": Enrollment.objects.select_related("student", "batch", "batch__course").order_by("-created_at")[:6],
    }
    return render(request, "admin_panel/academy/dashboard.html", context)


@salon_admin_required
def category_list(request):
    qs = CourseCategory.objects.annotate(course_count=Count("courses")).order_by("display_order", "name")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
    return render(request, "admin_panel/academy/category_list.html", {"page": _page(request, qs), "search": q})


@salon_admin_required
def category_create(request):
    return _form_page(request, CourseCategoryForm, None, "Create course category", "admin_panel:academy_categories")


@salon_admin_required
def category_edit(request, category_id):
    obj = get_object_or_404(CourseCategory, pk=category_id)
    return _form_page(request, CourseCategoryForm, obj, "Edit course category", "admin_panel:academy_categories")


@salon_admin_required
@require_POST
def category_toggle(request, category_id):
    obj = get_object_or_404(CourseCategory, pk=category_id)
    obj.is_active = not obj.is_active
    obj.save(update_fields=("is_active", "updated_at"))
    messages.success(request, f"{obj.name} is now {'active' if obj.is_active else 'inactive'}.")
    return redirect("admin_panel:academy_categories")


@salon_admin_required
def course_list(request):
    qs = Course.objects.select_related("category").annotate(batch_count=Count("batches")).order_by("title")
    q = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(short_description__icontains=q))
    if category.isdigit():
        qs = qs.filter(category_id=int(category))
    return render(request, "admin_panel/academy/course_list.html", {
        "page": _page(request, qs), "search": q, "categories": CourseCategory.objects.filter(is_active=True),
        "selected_category": category,
    })


@salon_admin_required
def course_create(request):
    return _form_page(request, CourseForm, None, "Create course", "admin_panel:academy_courses")


@salon_admin_required
def course_edit(request, course_id):
    obj = get_object_or_404(Course, pk=course_id)
    return _form_page(request, CourseForm, obj, "Edit course", "admin_panel:academy_courses")


@salon_admin_required
@require_POST
def course_toggle(request, course_id):
    obj = get_object_or_404(Course, pk=course_id)
    obj.is_active = not obj.is_active
    obj.save(update_fields=("is_active", "updated_at"))
    messages.success(request, f"{obj.title} is now {'active' if obj.is_active else 'inactive'}.")
    return redirect("admin_panel:academy_courses")


@salon_admin_required
def trainer_list(request):
    qs = AcademyTrainer.objects.select_related("user").order_by("user__first_name", "user__username")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q)
                       | Q(user__username__icontains=q) | Q(expertise__icontains=q))
    return render(request, "admin_panel/academy/trainer_list.html", {"page": _page(request, qs), "search": q})


@salon_admin_required
def trainer_create(request):
    return _form_page(request, TrainerForm, None, "Add academy trainer", "admin_panel:academy_trainers")


@salon_admin_required
def trainer_edit(request, trainer_id):
    obj = get_object_or_404(AcademyTrainer, pk=trainer_id)
    return _form_page(request, TrainerForm, obj, "Edit academy trainer", "admin_panel:academy_trainers")


@salon_admin_required
@require_POST
def trainer_toggle(request, trainer_id):
    obj = get_object_or_404(AcademyTrainer, pk=trainer_id)
    obj.is_active = not obj.is_active
    obj.save(update_fields=("is_active", "updated_at"))
    messages.success(request, f"{obj} is now {'active' if obj.is_active else 'inactive'}.")
    return redirect("admin_panel:academy_trainers")


@salon_admin_required
def batch_list(request):
    qs = Batch.objects.select_related("course", "trainer__user").annotate(
        active_enrollments=Count("enrollments", filter=Q(enrollments__status=Enrollment.Status.ACTIVE))
    ).order_by("-start_date", "name")
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q) | Q(course__title__icontains=q))
    if status in Batch.Status.values:
        qs = qs.filter(status=status)
    return render(request, "admin_panel/academy/batch_list.html", {
        "page": _page(request, qs), "search": q, "selected_status": status, "statuses": Batch.Status.choices,
    })


@salon_admin_required
def batch_create(request):
    return _form_page(request, BatchForm, None, "Create batch", "admin_panel:academy_batches")


@salon_admin_required
def batch_edit(request, batch_id):
    obj = get_object_or_404(Batch, pk=batch_id)
    return _form_page(request, BatchForm, obj, "Edit batch", "admin_panel:academy_batches")


@salon_admin_required
@require_POST
def batch_toggle(request, batch_id):
    obj = get_object_or_404(Batch, pk=batch_id)
    allowed = {
        Batch.Status.PLANNED: Batch.Status.ENROLLING,
        Batch.Status.ENROLLING: Batch.Status.ONGOING,
        Batch.Status.ONGOING: Batch.Status.COMPLETED,
        Batch.Status.COMPLETED: Batch.Status.COMPLETED,
        Batch.Status.CANCELLED: Batch.Status.CANCELLED,
    }
    obj.status = allowed[obj.status]
    obj.save(update_fields=("status", "updated_at"))
    messages.success(request, f"{obj.name} status updated to {obj.get_status_display()}.")
    return redirect("admin_panel:academy_batches")


def _form_page(request, form_class, instance, title, success_url):
    form = form_class(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        messages.success(request, f"{title.removeprefix('Create ').removeprefix('Edit ')} saved successfully.")
        return redirect(success_url)
    return render(request, "admin_panel/academy/form.html", {
        "form": form, "page_title": title, "cancel_url": success_url,
    })
