
from django import forms
from django.db.models import Q

from services.models import Service
from .models import StaffProfile, StaffSchedule, StaffLeave


class StaffProfileAdminForm(forms.ModelForm):
    class Meta:
        model = StaffProfile
        fields = [
            "name",
            "title",
            "bio",
            "photo",
            "years_experience",
            "services",
            "is_featured",
            "is_active",
            "order",
        ]

        widgets = {
            "name": forms.TextInput(
                attrs={"placeholder": "e.g. Priya"}
            ),
            "title": forms.TextInput(
                attrs={"placeholder": "e.g. Senior Hair Stylist"}
            ),
            "bio": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": "Write a professional beautician profile...",
                }
            ),
            "years_experience": forms.NumberInput(
                attrs={"min": 0, "placeholder": "Years of experience"}
            ),
            "services": forms.CheckboxSelectMultiple(),
            "order": forms.NumberInput(attrs={"min": 0}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        services = Service.objects.filter(is_active=True)

        # Preserve already assigned services when editing a staff profile,
        # even if one of those services has subsequently been deactivated.
        if self.instance and self.instance.pk:
            services = Service.objects.filter(
                Q(is_active=True)
                | Q(staff_members=self.instance)
            ).distinct()

        self.fields["services"].queryset = services.order_by(
            "category__order",
            "category__name",
            "order",
            "name",
        )

    def clean_years_experience(self):
        years = self.cleaned_data["years_experience"]

        if years < 0:
            raise forms.ValidationError(
                "Experience cannot be negative."
            )

        return years


class StaffScheduleAdminForm(forms.ModelForm):
    class Meta:
        model = StaffSchedule
        fields = [
            "weekday",
            "start_time",
            "end_time",
        ]

        widgets = {
            "weekday": forms.Select(),
            "start_time": forms.TimeInput(
                format="%H:%M",
                attrs={"type": "time"},
            ),
            "end_time": forms.TimeInput(
                format="%H:%M",
                attrs={"type": "time"},
            ),
        }

    def clean(self):
        cleaned_data = super().clean()

        start_time = cleaned_data.get("start_time")
        end_time = cleaned_data.get("end_time")

        if start_time and end_time and end_time <= start_time:
            raise forms.ValidationError(
                "End time must be later than start time."
            )

        return cleaned_data


class StaffLeaveAdminForm(forms.ModelForm):
    class Meta:
        model = StaffLeave
        fields = [
            "start",
            "end",
            "reason",
            "is_approved",
        ]

        widgets = {
            "start": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"type": "datetime-local"},
            ),
            "end": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"type": "datetime-local"},
            ),
            "reason": forms.TextInput(
                attrs={
                    "placeholder": "e.g. Personal leave, annual leave"
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["start"].input_formats = [
            "%Y-%m-%dT%H:%M"
        ]
        self.fields["end"].input_formats = [
            "%Y-%m-%dT%H:%M"
        ]

    def clean(self):
        cleaned_data = super().clean()

        start = cleaned_data.get("start")
        end = cleaned_data.get("end")

        if start and end and end <= start:
            raise forms.ValidationError(
                "Leave end date and time must be later than the start."
            )

        return cleaned_data
