
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from academy.models import (
    AcademyTrainer,
    Assessment,
    AssessmentResult,
    Attendance,
    Batch,
    Course,
    CourseCategory,
    CourseModule,
    Enrollment,
    ModuleProgress,
)
from academy.services import (
    academy_csv_response,
    certificate_eligibility,
    create_enrollment,
    save_attendance,
)


class AcademyServiceTests(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username="service-admin",
            email="service-admin@example.com",
            password="TestPass123!",
            role=User.Role.ADMIN,
        )

        self.student = User.objects.create_user(
            username="service-student",
            email="service-student@example.com",
            password="TestPass123!",
            role=User.Role.CUSTOMER,
        )

        self.student2 = User.objects.create_user(
            username="service-student2",
            email="service-student2@example.com",
            password="TestPass123!",
            role=User.Role.CUSTOMER,
        )

        self.trainer_user = User.objects.create_user(
            username="service-trainer",
            email="service-trainer@example.com",
            password="TestPass123!",
            role=User.Role.STAFF,
        )

        self.trainer = AcademyTrainer.objects.create(
            user=self.trainer_user,
            expertise="Beauty and skincare",
        )

        self.category = CourseCategory.objects.create(
            name="Beauty Skills",
            slug="beauty-skills",
        )

        self.course = Course.objects.create(
            category=self.category,
            title="Professional Makeup",
            slug="professional-makeup",
            fee=Decimal("15000.00"),
            duration_weeks=8,
        )

        today = timezone.localdate()

        self.batch = Batch.objects.create(
            course=self.course,
            trainer=self.trainer,
            name="November Makeup Batch",
            code="MAKEUP-NOV-01",
            start_date=today,
            end_date=today + timedelta(days=56),
            capacity=2,
            status=Batch.Status.ENROLLING,
        )

    def admit(self, student=None, batch=None):
        return create_enrollment(
            student=student or self.student,
            batch_id=(batch or self.batch).pk,
            fee_agreed=Decimal("15000.00"),
            enrolled_on=timezone.localdate(),
        )

    def test_create_enrollment_successfully(self):
        enrollment = self.admit()

        self.assertEqual(enrollment.student, self.student)
        self.assertEqual(enrollment.batch, self.batch)
        self.assertEqual(enrollment.status, Enrollment.Status.ACTIVE)
        self.assertEqual(self.batch.enrolled_count, 1)

    def test_duplicate_enrollment_is_rejected(self):
        self.admit()

        with self.assertRaises(ValidationError):
            self.admit()

    def test_full_batch_rejects_new_enrollment(self):
        self.admit(self.student)

        # Fill the remaining seat.
        self.admit(self.student2)

        third_student = User.objects.create_user(
            username="service-student3",
            email="service-student3@example.com",
            password="TestPass123!",
            role=User.Role.CUSTOMER,
        )

        with self.assertRaises(ValidationError):
            self.admit(third_student)

    def test_inactive_student_is_rejected(self):
        self.student.is_active = False
        self.student.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError):
            self.admit()

    def test_non_customer_cannot_be_enrolled(self):
        with self.assertRaises(ValidationError):
            self.admit(self.trainer_user)

    def test_non_enrolling_batch_rejects_admission(self):
        self.batch.status = Batch.Status.PLANNED
        self.batch.save(update_fields=["status"])

        with self.assertRaises(ValidationError):
            self.admit()

    def test_missing_batch_is_rejected(self):
        with self.assertRaises(ValidationError):
            create_enrollment(
                student=self.student,
                batch_id=999999,
                fee_agreed=Decimal("15000.00"),
                enrolled_on=timezone.localdate(),
            )

    def test_attendance_is_created_and_updated(self):
        enrollment = self.admit()
        today = timezone.localdate()

        attendance = save_attendance(
            enrollment=enrollment,
            attendance_date=today,
            status=Attendance.Status.PRESENT,
            remarks="Attended class",
            marked_by=self.admin,
        )

        self.assertEqual(attendance.status, Attendance.Status.PRESENT)

        updated = save_attendance(
            enrollment=enrollment,
            attendance_date=today,
            status=Attendance.Status.LATE,
            remarks="Arrived late",
            marked_by=self.admin,
        )

        self.assertEqual(updated.pk, attendance.pk)
        self.assertEqual(updated.status, Attendance.Status.LATE)
        self.assertEqual(
            Attendance.objects.filter(
                enrollment=enrollment,
                attendance_date=today,
            ).count(),
            1,
        )

    def test_attendance_rejected_for_inactive_enrollment(self):
        enrollment = self.admit()
        enrollment.status = Enrollment.Status.WITHDRAWN
        enrollment.save(update_fields=["status"])

        with self.assertRaises(ValidationError):
            save_attendance(
                enrollment=enrollment,
                attendance_date=timezone.localdate(),
                status=Attendance.Status.PRESENT,
                marked_by=self.admin,
            )

    def test_certificate_requires_completed_enrollment(self):
        enrollment = self.admit()

        eligible, message = certificate_eligibility(enrollment)

        self.assertFalse(eligible)
        self.assertIn("completed", message.lower())

    def test_certificate_requires_required_modules(self):
        enrollment = self.admit()
        enrollment.status = Enrollment.Status.COMPLETED
        enrollment.save(update_fields=["status"])

        module = CourseModule.objects.create(
            course=self.course,
            title="Skin Preparation",
            sequence=1,
            is_required=True,
        )

        eligible, message = certificate_eligibility(enrollment)

        self.assertFalse(eligible)
        self.assertIn(module.title, message)

    def test_certificate_requires_passing_required_assessments(self):
        enrollment = self.admit()
        enrollment.status = Enrollment.Status.COMPLETED
        enrollment.save(update_fields=["status"])

        module = CourseModule.objects.create(
            course=self.course,
            title="Skin Preparation",
            sequence=1,
            is_required=True,
        )

        ModuleProgress.objects.create(
            enrollment=enrollment,
            module=module,
            is_completed=True,
        )

        assessment = Assessment.objects.create(
            course=self.course,
            title="Makeup Practical",
            max_score=Decimal("100.00"),
            pass_score=Decimal("50.00"),
            is_required_for_certificate=True,
        )

        eligible, message = certificate_eligibility(enrollment)

        self.assertFalse(eligible)
        self.assertIn(assessment.title, message)

        AssessmentResult.objects.create(
            enrollment=enrollment,
            assessment=assessment,
            score=Decimal("45.00"),
            evaluated_by=self.admin,
        )

        eligible, message = certificate_eligibility(enrollment)

        self.assertFalse(eligible)
        self.assertIn(assessment.title, message)

    def test_certificate_eligibility_when_all_requirements_are_met(self):
        enrollment = self.admit()
        enrollment.status = Enrollment.Status.COMPLETED
        enrollment.save(update_fields=["status"])

        module = CourseModule.objects.create(
            course=self.course,
            title="Skin Preparation",
            sequence=1,
            is_required=True,
        )

        ModuleProgress.objects.create(
            enrollment=enrollment,
            module=module,
            is_completed=True,
        )

        assessment = Assessment.objects.create(
            course=self.course,
            title="Makeup Practical",
            max_score=Decimal("100.00"),
            pass_score=Decimal("50.00"),
            is_required_for_certificate=True,
        )

        AssessmentResult.objects.create(
            enrollment=enrollment,
            assessment=assessment,
            score=Decimal("80.00"),
            evaluated_by=self.admin,
        )

        eligible, message = certificate_eligibility(enrollment)

        self.assertTrue(eligible)
        self.assertIn("eligible", message.lower())

    def test_csv_response_contains_headers_and_rows(self):
        response = academy_csv_response(
            "academy-test.csv",
            ["Student", "Course"],
            [["Swetha", "Professional Makeup"]],
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn(
            'attachment; filename="academy-test.csv"',
            response["Content-Disposition"],
        )

        content = response.content.decode("utf-8")
        self.assertIn("Student,Course", content)
        self.assertIn("Swetha,Professional Makeup", content)
