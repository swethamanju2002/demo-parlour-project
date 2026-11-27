import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class CourseCategory(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("display_order", "name")
        verbose_name_plural = "course categories"

    def __str__(self):
        return self.name


class Course(TimeStampedModel):
    class Level(models.TextChoices):
        BEGINNER = "beginner", "Beginner"
        INTERMEDIATE = "intermediate", "Intermediate"
        ADVANCED = "advanced", "Advanced"

    category = models.ForeignKey(
        CourseCategory, on_delete=models.PROTECT, related_name="courses"
    )
    title = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True)
    short_description = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    level = models.CharField(max_length=20, choices=Level.choices, default=Level.BEGINNER)
    duration_weeks = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)], default=4
    )
    fee = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0)]
    )
    syllabus = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("category__display_order", "title")
        constraints = [
            models.CheckConstraint(condition=Q(fee__gte=0), name="academy_course_fee_nonnegative"),
            models.CheckConstraint(condition=Q(duration_weeks__gte=1), name="academy_course_duration_positive"),
        ]

    def __str__(self):
        return self.title


class AcademyTrainer(TimeStampedModel):
    """An explicit academy trainer identity; salon StaffProfile is intentionally separate."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="academy_trainer"
    )
    bio = models.TextField(blank=True)
    expertise = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("user__first_name", "user__username")

    def clean(self):
        super().clean()
        if self.user_id and getattr(self.user, "role", None) not in ("staff", "admin"):
            raise ValidationError({"user": "Select an existing staff or admin account as the trainer."})

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class Batch(TimeStampedModel):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        ENROLLING = "enrolling", "Enrolling"
        ONGOING = "ongoing", "Ongoing"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="batches")
    trainer = models.ForeignKey(
        AcademyTrainer, on_delete=models.PROTECT, related_name="batches"
    )
    name = models.CharField(max_length=140)
    code = models.CharField(max_length=30, unique=True)
    start_date = models.DateField()
    end_date = models.DateField()
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    capacity = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)], default=10
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED)
    location = models.CharField(max_length=160, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-start_date", "name")
        constraints = [
            models.CheckConstraint(condition=Q(end_date__gte=models.F("start_date")), name="academy_batch_dates_valid"),
            models.CheckConstraint(condition=Q(capacity__gte=1), name="academy_batch_capacity_positive"),
        ]

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "End date cannot be before start date."})
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError({"end_time": "End time must be later than start time."})

    @property
    def enrolled_count(self):
        return self.enrollments.filter(status=Enrollment.Status.ACTIVE).count()

    @property
    def available_seats(self):
        return max(self.capacity - self.enrolled_count, 0)

    def __str__(self):
        return f"{self.name} ({self.code})"


class Enrollment(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        WITHDRAWN = "withdrawn", "Withdrawn"
        CANCELLED = "cancelled", "Cancelled"

    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="enrollments")
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="academy_enrollments"
    )
    enrolled_on = models.DateField(default=timezone.localdate)
    fee_agreed = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    admission_notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-enrolled_on", "-created_at")
        constraints = [
            models.UniqueConstraint(fields=("batch", "student"), name="academy_unique_batch_student"),
            models.CheckConstraint(condition=Q(fee_agreed__gte=0), name="academy_enrollment_fee_nonnegative"),
        ]

    def clean(self):
        super().clean()
        if self.student_id and getattr(self.student, "role", None) != "customer":
            raise ValidationError({"student": "Only customer accounts can be enrolled as students."})
        if self.batch_id and self.status == self.Status.ACTIVE:
            current = self.batch.enrollments.filter(status=self.Status.ACTIVE).exclude(pk=self.pk).count()
            if current >= self.batch.capacity:
                raise ValidationError({"batch": "This batch has reached its capacity."})

    def __str__(self):
        return f"{self.student} — {self.batch}"


class Attendance(TimeStampedModel):
    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        LATE = "late", "Late"
        EXCUSED = "excused", "Excused"

    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="attendance")
    attendance_date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PRESENT)
    remarks = models.CharField(max_length=255, blank=True)
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="academy_attendance_marked"
    )

    class Meta:
        ordering = ("-attendance_date", "enrollment__student__first_name")
        constraints = [
            models.UniqueConstraint(fields=("enrollment", "attendance_date"), name="academy_unique_daily_attendance")
        ]

    def __str__(self):
        return f"{self.enrollment} — {self.attendance_date}: {self.get_status_display()}"


class CourseModule(TimeStampedModel):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="modules")
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    sequence = models.PositiveSmallIntegerField(default=1)
    estimated_hours = models.PositiveSmallIntegerField(default=1)
    is_required = models.BooleanField(default=True)

    class Meta:
        ordering = ("sequence", "id")
        constraints = [
            models.UniqueConstraint(fields=("course", "sequence"), name="academy_unique_module_sequence")
        ]

    def __str__(self):
        return f"{self.course.title} — {self.title}"


class ModuleProgress(TimeStampedModel):
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="module_progress")
    module = models.ForeignKey(CourseModule, on_delete=models.CASCADE, related_name="student_progress")
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    trainer_notes = models.TextField(blank=True)

    class Meta:
        ordering = ("module__sequence",)
        constraints = [
            models.UniqueConstraint(fields=("enrollment", "module"), name="academy_unique_enrollment_module")
        ]

    def clean(self):
        super().clean()
        if self.enrollment_id and self.module_id:
            if self.enrollment.batch.course_id != self.module.course_id:
                raise ValidationError("The module must belong to the student's enrolled course.")

    def save(self, *args, **kwargs):
        if self.is_completed and not self.completed_at:
            self.completed_at = timezone.now()
        elif not self.is_completed:
            self.completed_at = None
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.enrollment} — {self.module}"


class Assessment(TimeStampedModel):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="assessments")
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    max_score = models.DecimalField(max_digits=7, decimal_places=2, validators=[MinValueValidator(0)])
    pass_score = models.DecimalField(max_digits=7, decimal_places=2, validators=[MinValueValidator(0)])
    is_required_for_certificate = models.BooleanField(default=True)
    assessment_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("assessment_date", "title")
        constraints = [
            models.CheckConstraint(condition=Q(max_score__gte=0), name="academy_assessment_max_nonnegative"),
            models.CheckConstraint(condition=Q(pass_score__gte=0), name="academy_assessment_pass_nonnegative"),
        ]

    def clean(self):
        super().clean()
        if self.pass_score is not None and self.max_score is not None and self.pass_score > self.max_score:
            raise ValidationError({"pass_score": "Pass score cannot exceed maximum score."})

    def __str__(self):
        return f"{self.course.title} — {self.title}"


class AssessmentResult(TimeStampedModel):
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="assessment_results")
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="results")
    score = models.DecimalField(max_digits=7, decimal_places=2, validators=[MinValueValidator(0)])
    feedback = models.TextField(blank=True)
    evaluated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="academy_results_evaluated"
    )
    evaluated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("enrollment", "assessment"), name="academy_unique_assessment_result")
        ]

    def clean(self):
        super().clean()
        if self.enrollment_id and self.assessment_id:
            if self.enrollment.batch.course_id != self.assessment.course_id:
                raise ValidationError("Assessment must belong to the enrolled course.")
        if self.score is not None and self.assessment_id and self.score > self.assessment.max_score:
            raise ValidationError({"score": "Score cannot exceed the assessment maximum."})

    @property
    def passed(self):
        return self.score >= self.assessment.pass_score

    def __str__(self):
        return f"{self.enrollment} — {self.assessment}: {self.score}"


class Certificate(TimeStampedModel):
    enrollment = models.OneToOneField(Enrollment, on_delete=models.PROTECT, related_name="certificate")
    certificate_number = models.CharField(max_length=40, unique=True, blank=True)
    issued_on = models.DateField(default=timezone.localdate)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="academy_certificates_issued"
    )
    verification_code = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ("-issued_on",)

    def save(self, *args, **kwargs):
        if not self.certificate_number:
            self.certificate_number = f"DQA-{timezone.localdate():%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.certificate_number
