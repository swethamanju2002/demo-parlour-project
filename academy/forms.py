from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from .models import AcademyTrainer, Batch, Course, CourseCategory

User = get_user_model()


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (existing + " adm-input").strip()


class CourseCategoryForm(StyledModelForm):
    class Meta:
        model = CourseCategory
        fields = ("name", "slug", "description", "display_order", "is_active")
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class CourseForm(StyledModelForm):
    class Meta:
        model = Course
        fields = (
            "category", "title", "slug", "short_description", "description",
            "level", "duration_weeks", "fee", "syllabus", "is_active",
        )
        widgets = {
            "short_description": forms.TextInput(attrs={"maxlength": 255}),
            "description": forms.Textarea(attrs={"rows": 4}),
            "syllabus": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = CourseCategory.objects.filter(is_active=True)


class TrainerForm(StyledModelForm):
    user = forms.ModelChoiceField(
        queryset=User.objects.filter(role__in=("staff", "admin"), is_active=True).order_by("first_name", "username"),
        help_text="Select an existing staff or administrator account.",
    )

    class Meta:
        model = AcademyTrainer
        fields = ("user", "expertise", "bio", "is_active")
        widgets = {"bio": forms.Textarea(attrs={"rows": 4})}


class BatchForm(StyledModelForm):
    class Meta:
        model = Batch
        fields = (
            "course", "trainer", "name", "code", "start_date", "end_date",
            "start_time", "end_time", "capacity", "status", "location", "notes",
        )
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["course"].queryset = Course.objects.filter(is_active=True)
        self.fields["trainer"].queryset = AcademyTrainer.objects.filter(is_active=True).select_related("user")

    def clean(self):
        cleaned = super().clean()
        start_date, end_date = cleaned.get("start_date"), cleaned.get("end_date")
        start_time, end_time = cleaned.get("start_time"), cleaned.get("end_time")
        if start_date and end_date and end_date < start_date:
            self.add_error("end_date", "End date cannot be before start date.")
        if start_time and end_time and start_time >= end_time:
            self.add_error("end_time", "End time must be later than start time.")
        return cleaned

from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import (
    Assessment,
    AssessmentResult,
    Attendance,
    Batch,
    Course,
    CourseModule,
    Enrollment,
    ModuleProgress,
)

User = get_user_model()


def style_form(form):
    for field in form.fields.values():
        old_class = field.widget.attrs.get("class", "")
        field.widget.attrs["class"] = (old_class + " adm-input").strip()



class AdmissionForm(forms.Form):
    student = forms.ModelChoiceField(
        queryset=User.objects.filter(
            role="customer",
            is_active=True,
        ).order_by("first_name", "username")
    )

    course = forms.ModelChoiceField(
        queryset=Course.objects.filter(is_active=True)
    )

    batch = forms.ModelChoiceField(
        queryset=Batch.objects.filter(
            course__is_active=True,
            status=Batch.Status.ENROLLING,
        ).order_by("start_date", "name")
    )

    enrolled_on = forms.DateField(
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    fee_agreed = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0,
        required=False,
    )

    admission_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        style_form(self)

        course_id = (
            self.data.get("course")
            or self.initial.get("course")
        )

        if course_id:
            self.fields["batch"].queryset = Batch.objects.filter(
                course_id=course_id,
                course__is_active=True,
                status=Batch.Status.ENROLLING,
            ).order_by("start_date", "name")

        if course_id and not self.is_bound:
            try:
                course = Course.objects.get(
                    pk=course_id,
                    is_active=True,
                )
                self.initial["fee_agreed"] = course.fee
            except Course.DoesNotExist:
                pass

    def clean(self):
        cleaned = super().clean()

        course = cleaned.get("course")
        batch = cleaned.get("batch")

        if course and cleaned.get("fee_agreed") is None:
            cleaned["fee_agreed"] = course.fee

        if course and batch:
            if batch.course_id != course.id:
                self.add_error(
                    "batch",
                    "Please select a batch belonging to the selected course."
                )

            elif batch.status != Batch.Status.ENROLLING:
                self.add_error(
                    "batch",
                    "This batch is not currently open for admissions."
                )

        return cleaned

class ModuleForm(forms.ModelForm):
    class Meta:
        model = CourseModule
        fields = (
            "course",
            "title",
            "description",
            "sequence",
            "estimated_hours",
            "is_required",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_form(self)


class ProgressForm(forms.ModelForm):
    class Meta:
        model = ModuleProgress
        fields = ("is_completed", "trainer_notes")
        widgets = {
            "trainer_notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_form(self)


class AssessmentForm(forms.ModelForm):
    class Meta:
        model = Assessment
        fields = (
            "course",
            "title",
            "description",
            "max_score",
            "pass_score",
            "is_required_for_certificate",
            "assessment_date",
            "is_active",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "assessment_date": forms.DateInput(
                attrs={"type": "date"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_form(self)

    def clean(self):
        cleaned = super().clean()

        maximum = cleaned.get("max_score")
        passing = cleaned.get("pass_score")

        if maximum is not None and passing is not None:
            if passing > maximum:
                self.add_error(
                    "pass_score",
                    "Pass score cannot exceed maximum score.",
                )

        return cleaned


class ResultForm(forms.ModelForm):
    class Meta:
        model = AssessmentResult
        fields = ("score", "feedback")
        widgets = {
            "feedback": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_form(self)
