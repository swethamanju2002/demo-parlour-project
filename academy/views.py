
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.permissions import salon_admin_required

from .models import (
    Assessment,
    AssessmentResult,
    Attendance,
    Batch,
    Certificate,
    Course,
    CourseModule,
    Enrollment,
    ModuleProgress,
)

from .forms import (
    AdmissionForm,
    AssessmentForm,
    ModuleForm,
    ProgressForm,
    ResultForm,
)

from .services import (
    academy_csv_response,
    certificate_eligibility,
    create_enrollment,
    save_attendance,
)


def p7_page(request, queryset, per_page=15):
    return Paginator(queryset, per_page).get_page(
        request.GET.get("page")
    )


def p7_form(request, form, title, cancel_url):
    return render(
        request,
        "admin_panel/academy/p7_form.html",
        {
            "form": form,
            "page_title": title,
            "heading": title,
            "cancel_url": cancel_url,
        },
    )


# =====================================================
# STEP 3 — STUDENT ADMISSIONS
# =====================================================

@salon_admin_required
def enrollment_list(request):
    qs = Enrollment.objects.select_related(
        "student",
        "batch",
        "batch__course",
    )

    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()

    if search:
        qs = qs.filter(
            Q(student__first_name__icontains=search)
            | Q(student__last_name__icontains=search)
            | Q(student__username__icontains=search)
            | Q(student__email__icontains=search)
            | Q(batch__name__icontains=search)
            | Q(batch__course__title__icontains=search)
        )

    if status in Enrollment.Status.values:
        qs = qs.filter(status=status)

    return render(
        request,
        "admin_panel/academy/enrollments.html",
        {
            "page": p7_page(request, qs),
            "search": search,
            "statuses": Enrollment.Status.choices,
            "selected_status": status,
        },
    )


@salon_admin_required
def enrollment_create(request):
    initial = {}

    course_id = request.GET.get("course")
    if course_id and course_id.isdigit():
        initial["course"] = int(course_id)

    form = AdmissionForm(
        request.POST or None,
        initial=initial,
    )

    if request.method == "POST" and form.is_valid():
        try:
            enrollment = create_enrollment(
                student=form.cleaned_data["student"],
                batch_id=form.cleaned_data["batch"].pk,
                fee_agreed=form.cleaned_data["fee_agreed"],
                enrolled_on=form.cleaned_data["enrolled_on"],
                admission_notes=form.cleaned_data["admission_notes"],
            )

            messages.success(
                request,
                "Student admitted successfully.",
            )

            return redirect(
                "admin_panel:academy_enrollment_detail",
                enrollment_id=enrollment.pk,
            )

        except (ValidationError, IntegrityError) as exc:
            form.add_error(None, str(exc))

    return p7_form(
        request,
        form,
        "New Student Admission",
        "admin_panel:academy_enrollments",
    )


@salon_admin_required
def enrollment_detail(request, enrollment_id):
    enrollment = get_object_or_404(
        Enrollment.objects.select_related(
            "student",
            "batch",
            "batch__course",
            "batch__trainer__user",
        ),
        pk=enrollment_id,
    )

    progress = ModuleProgress.objects.filter(
        enrollment=enrollment,
    ).select_related("module")

    results = AssessmentResult.objects.filter(
        enrollment=enrollment,
    ).select_related("assessment")

    attendance = Attendance.objects.filter(
        enrollment=enrollment,
    ).order_by("-attendance_date")[:30]

    eligible, eligibility_message = certificate_eligibility(
        enrollment
    )

    certificate = Certificate.objects.filter(
        enrollment=enrollment
    ).first()

    return render(
        request,
        "admin_panel/academy/enrollment_detail.html",
        {
            "enrollment": enrollment,
            "progress": progress,
            "results": results,
            "attendance": attendance,
            "certificate_eligible": eligible,
            "eligibility_message": eligibility_message,
            "certificate": certificate,
            "enrollment_statuses": Enrollment.Status.choices,
            "modules": CourseModule.objects.filter(
                course=enrollment.batch.course
            ),
            "assessments": Assessment.objects.filter(
                course=enrollment.batch.course,
                is_active=True,
            ),
        },
    )


@salon_admin_required
@require_POST
def enrollment_status_update(request, enrollment_id):
    with transaction.atomic():
        enrollment = get_object_or_404(
            Enrollment.objects.select_for_update(),
            pk=enrollment_id,
        )

        new_status = request.POST.get("status")

        if new_status not in Enrollment.Status.values:
            messages.error(request, "Invalid enrollment status.")
            return redirect(
                "admin_panel:academy_enrollment_detail",
                enrollment_id=enrollment.pk,
            )

        if new_status == Enrollment.Status.ACTIVE:
            batch = Batch.objects.select_for_update().get(
                pk=enrollment.batch_id
            )

            active_count = Enrollment.objects.filter(
                batch=batch,
                status=Enrollment.Status.ACTIVE,
            ).exclude(pk=enrollment.pk).count()

            if active_count >= batch.capacity:
                messages.error(
                    request,
                    "Cannot reactivate: batch capacity is full.",
                )
                return redirect(
                    "admin_panel:academy_enrollment_detail",
                    enrollment_id=enrollment.pk,
                )

        enrollment.status = new_status
        enrollment.save(update_fields=("status", "updated_at"))

    messages.success(request, "Enrollment status updated.")

    return redirect(
        "admin_panel:academy_enrollment_detail",
        enrollment_id=enrollment.pk,
    )


# =====================================================
# STEP 4 — ATTENDANCE
# =====================================================

@salon_admin_required
def attendance_list(request):
    qs = Attendance.objects.select_related(
        "enrollment__student",
        "enrollment__batch",
        "enrollment__batch__course",
        "marked_by",
    )

    date_value = request.GET.get("date", "").strip()
    batch_id = request.GET.get("batch", "").strip()

    if date_value:
        qs = qs.filter(attendance_date=date_value)

    if batch_id.isdigit():
        qs = qs.filter(enrollment__batch_id=int(batch_id))

    batches = Batch.objects.select_related("course").order_by(
        "-start_date"
    )

    return render(
        request,
        "admin_panel/academy/attendance.html",
        {
            "page": p7_page(request, qs),
            "date_value": date_value,
            "batches": batches,
            "selected_batch": batch_id,
        },
    )


@salon_admin_required
def attendance_mark(request, batch_id):
    batch = get_object_or_404(
        Batch.objects.select_related("course"),
        pk=batch_id,
    )

    enrollments = Enrollment.objects.filter(
        batch=batch,
        status=Enrollment.Status.ACTIVE,
    ).select_related("student").order_by(
        "student__first_name",
        "student__username",
    )

    if request.method == "POST":
        date_value = request.POST.get("attendance_date")

        try:
            attendance_date = timezone.datetime.strptime(
                date_value,
                "%Y-%m-%d",
            ).date()
        except (ValueError, TypeError):
            messages.error(request, "Select a valid attendance date.")
            return redirect(
                "admin_panel:academy_attendance_mark",
                batch_id=batch.pk,
            )

        marked = 0

        for enrollment in enrollments:
            status = request.POST.get(
                f"status_{enrollment.pk}"
            )

            if status not in Attendance.Status.values:
                continue

            try:
                save_attendance(
                    enrollment=enrollment,
                    attendance_date=attendance_date,
                    status=status,
                    remarks=request.POST.get(
                        f"remarks_{enrollment.pk}",
                        "",
                    ),
                    marked_by=request.user,
                )
                marked += 1

            except ValidationError as exc:
                messages.error(request, str(exc))

        messages.success(
            request,
            f"Attendance saved for {marked} students.",
        )

        return redirect("admin_panel:academy_attendance")

    return render(
        request,
        "admin_panel/academy/attendance_mark.html",
        {
            "batch": batch,
            "enrollments": enrollments,
            "today": timezone.localdate(),
            "statuses": Attendance.Status.choices,
        },
    )


# =====================================================
# STEP 5 — COURSE MODULES AND LEARNING PROGRESS
# =====================================================

@salon_admin_required
def module_list(request):
    qs = CourseModule.objects.select_related("course")

    course_id = request.GET.get("course", "").strip()

    if course_id.isdigit():
        qs = qs.filter(course_id=int(course_id))

    return render(
        request,
        "admin_panel/academy/modules.html",
        {
            "page": p7_page(request, qs),
            "courses": Course.objects.all(),
        },
    )


@salon_admin_required
def module_create(request):
    form = ModuleForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Course module created.")
        return redirect("admin_panel:academy_modules")

    return p7_form(
        request,
        form,
        "Create Course Module",
        "admin_panel:academy_modules",
    )


@salon_admin_required
def module_edit(request, module_id):
    module = get_object_or_404(CourseModule, pk=module_id)

    form = ModuleForm(
        request.POST or None,
        instance=module,
    )

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Course module updated.")
        return redirect("admin_panel:academy_modules")

    return p7_form(
        request,
        form,
        "Edit Course Module",
        "admin_panel:academy_modules",
    )


@salon_admin_required
def progress_update(request, enrollment_id, module_id):
    enrollment = get_object_or_404(
        Enrollment.objects.select_related("batch__course"),
        pk=enrollment_id,
    )

    module = get_object_or_404(
        CourseModule,
        pk=module_id,
        course=enrollment.batch.course,
    )

    progress, created = ModuleProgress.objects.get_or_create(
        enrollment=enrollment,
        module=module,
    )

    form = ProgressForm(
        request.POST or None,
        instance=progress,
    )

    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.full_clean()
        obj.save()

        messages.success(
            request,
            "Learning progress updated.",
        )

        return redirect(
            "admin_panel:academy_enrollment_detail",
            enrollment_id=enrollment.pk,
        )

    # progress_update
    return p7_form(
        request,
        form,
        f"Update Progress — {module.title}",
        "admin_panel:academy_modules",
    )


# =====================================================
# STEP 5 — ASSESSMENTS AND RESULTS
# =====================================================

@salon_admin_required
def assessment_list(request):
    qs = Assessment.objects.select_related("course")

    course_id = request.GET.get("course", "").strip()

    if course_id.isdigit():
        qs = qs.filter(course_id=int(course_id))

    return render(
        request,
        "admin_panel/academy/assessments.html",
        {
            "page": p7_page(request, qs),
            "courses": Course.objects.all(),
        },
    )


@salon_admin_required
def assessment_create(request):
    form = AssessmentForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Assessment created.")
        return redirect("admin_panel:academy_assessments")

    return p7_form(
        request,
        form,
        "Create Assessment",
        "admin_panel:academy_assessments",
    )


@salon_admin_required
def assessment_edit(request, assessment_id):
    assessment = get_object_or_404(
        Assessment,
        pk=assessment_id,
    )

    form = AssessmentForm(
        request.POST or None,
        instance=assessment,
    )

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Assessment updated.")
        return redirect("admin_panel:academy_assessments")

    return p7_form(
        request,
        form,
        "Edit Assessment",
        "admin_panel:academy_assessments",
    )


@salon_admin_required
def result_create(request, enrollment_id, assessment_id):
    enrollment = get_object_or_404(
        Enrollment.objects.select_related("batch__course"),
        pk=enrollment_id,
    )

    assessment = get_object_or_404(
        Assessment,
        pk=assessment_id,
        course=enrollment.batch.course,
        is_active=True,
    )

    result = AssessmentResult.objects.filter(
        enrollment=enrollment,
        assessment=assessment,
    ).first()

    form = ResultForm(
        request.POST or None,
        instance=result,
    )

    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.enrollment = enrollment
        obj.assessment = assessment
        obj.evaluated_by = request.user
        obj.evaluated_at = timezone.now()

        try:
            obj.full_clean()
            obj.save()

            messages.success(
                request,
                "Assessment result saved.",
            )

            return redirect(
                "admin_panel:academy_enrollment_detail",
                enrollment_id=enrollment.pk,
            )

        except ValidationError as exc:
            form.add_error(None, str(exc))

    # result_create
    return p7_form(
        request,
        form,
        f"Result — {assessment.title}",
        "admin_panel:academy_assessments",
    )


# =====================================================
# STEP 6 — CERTIFICATES
# =====================================================

@salon_admin_required
def certificate_list(request):
    qs = Certificate.objects.select_related(
        "enrollment__student",
        "enrollment__batch__course",
        "issued_by",
    )

    return render(
        request,
        "admin_panel/academy/certificates.html",
        {"page": p7_page(request, qs)},
    )


@salon_admin_required
@require_POST
def certificate_issue(request, enrollment_id):
    enrollment = get_object_or_404(
        Enrollment.objects.select_related("batch__course"),
        pk=enrollment_id,
    )

    eligible, reason = certificate_eligibility(enrollment)

    if not eligible:
        messages.error(request, reason)
        return redirect(
            "admin_panel:academy_enrollment_detail",
            enrollment_id=enrollment.pk,
        )

    certificate, created = Certificate.objects.get_or_create(
        enrollment=enrollment,
        defaults={
            "issued_by": request.user,
            "remarks": "Issued after eligibility verification.",
        },
    )

    if created:
        messages.success(
            request,
            f"Certificate {certificate.certificate_number} issued.",
        )
    else:
        messages.info(
            request,
            "A certificate already exists for this enrollment.",
        )

    return redirect("admin_panel:academy_certificates")


@salon_admin_required
def certificate_verify(request, verification_code):
    certificate = get_object_or_404(
        Certificate.objects.select_related(
            "enrollment__student",
            "enrollment__batch__course",
        ),
        verification_code=verification_code,
    )

    return render(
        request,
        "admin_panel/academy/certificate_verify.html",
        {"certificate": certificate},
    )


# =====================================================
# STEP 6 — REPORTS AND CSV EXPORT
# =====================================================

@salon_admin_required
def reports(request):
    qs = Enrollment.objects.all()

    context = {
        "total_enrollments": qs.count(),
        "active_enrollments": qs.filter(
            status=Enrollment.Status.ACTIVE
        ).count(),
        "completed_enrollments": qs.filter(
            status=Enrollment.Status.COMPLETED
        ).count(),
        "withdrawn_enrollments": qs.filter(
            status=Enrollment.Status.WITHDRAWN
        ).count(),
        "certificates": Certificate.objects.count(),
        "attendance_records": Attendance.objects.count(),
    }

    return render(
        request,
        "admin_panel/academy/reports.html",
        context,
    )


@salon_admin_required
def enrollment_export(request):
    qs = Enrollment.objects.select_related(
        "student",
        "batch__course",
    ).order_by("-enrolled_on")

    status = request.GET.get("status", "")

    if status in Enrollment.Status.values:
        qs = qs.filter(status=status)

    rows = []

    for enrollment in qs:
        rows.append((
            enrollment.student.get_full_name()
            or enrollment.student.username,
            enrollment.student.email,
            enrollment.batch.course.title,
            enrollment.batch.name,
            enrollment.enrolled_on,
            enrollment.fee_agreed,
            enrollment.get_status_display(),
        ))

    return academy_csv_response(
        "academy-enrollments.csv",
        (
            "Student",
            "Email",
            "Course",
            "Batch",
            "Admission Date",
            "Agreed Fee",
            "Status",
        ),
        rows,
    )
