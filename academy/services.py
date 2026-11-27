
import csv
from io import StringIO

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpResponse

from .models import (
    Assessment,
    AssessmentResult,
    Attendance,
    Batch,
    CourseModule,
    Enrollment,
    ModuleProgress,
)


@transaction.atomic
def create_enrollment(
    *,
    student,
    batch_id,
    fee_agreed,
    enrolled_on,
    admission_notes="",
):
    try:
        batch = (
            Batch.objects.select_for_update()
            .select_related("course")
            .get(pk=batch_id)
        )
    except Batch.DoesNotExist:
        raise ValidationError("The selected batch does not exist.")

    if getattr(student, "role", None) != "customer" or not student.is_active:
        raise ValidationError("Select an active customer account.")

    if not batch.course.is_active:
        raise ValidationError("The selected course is inactive.")

    if batch.status != Batch.Status.ENROLLING:
        raise ValidationError("This batch is not accepting admissions.")

    if Enrollment.objects.filter(batch=batch, student=student).exists():
        raise ValidationError("This student is already enrolled in this batch.")

    active_count = Enrollment.objects.filter(
        batch=batch,
        status=Enrollment.Status.ACTIVE,
    ).count()

    if active_count >= batch.capacity:
        raise ValidationError("This batch has reached its enrollment capacity.")

    enrollment = Enrollment(
        student=student,
        batch=batch,
        fee_agreed=fee_agreed,
        enrolled_on=enrolled_on,
        admission_notes=admission_notes,
        status=Enrollment.Status.ACTIVE,
    )

    enrollment.full_clean()

    # Use a savepoint so a duplicate-key failure does not break
    # the surrounding atomic transaction.
    try:
        with transaction.atomic():
            enrollment.save()
    except IntegrityError:
        raise ValidationError(
            "This student is already enrolled in the selected batch."
        )

    return enrollment


@transaction.atomic
def save_attendance(
    *,
    enrollment,
    attendance_date,
    status,
    remarks="",
    marked_by,
):
    if enrollment.status != Enrollment.Status.ACTIVE:
        raise ValidationError(
            "Attendance can only be marked for active enrollments."
        )

    attendance, _ = Attendance.objects.update_or_create(
        enrollment=enrollment,
        attendance_date=attendance_date,
        defaults={
            "status": status,
            "remarks": remarks,
            "marked_by": marked_by,
        },
    )
    return attendance


def certificate_eligibility(enrollment):
    if enrollment.status != Enrollment.Status.COMPLETED:
        return False, "Enrollment must be completed first."

    required_modules = CourseModule.objects.filter(
        course=enrollment.batch.course,
        is_required=True,
    )

    for module in required_modules:
        completed = ModuleProgress.objects.filter(
            enrollment=enrollment,
            module=module,
            is_completed=True,
        ).exists()

        if not completed:
            return False, f"Complete module: {module.title}"

    required_assessments = Assessment.objects.filter(
        course=enrollment.batch.course,
        is_active=True,
        is_required_for_certificate=True,
    )

    for assessment in required_assessments:
        result = AssessmentResult.objects.filter(
            enrollment=enrollment,
            assessment=assessment,
        ).first()

        if not result or result.score < assessment.pass_score:
            return False, (
                f"Required assessment not passed: {assessment.title}"
            )

    return True, "Student is eligible for a certificate."


def academy_csv_response(filename, headers, rows):
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)

    response = HttpResponse(
        output.getvalue(),
        content_type="text/csv; charset=utf-8",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="{filename}"'
    )
    return response
