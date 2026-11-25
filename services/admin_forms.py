
from django import forms
from django.db.models import Q
from .models import Service, ServiceCategory


class ServiceCategoryAdminForm(forms.ModelForm):
    class Meta:
        model = ServiceCategory
        fields = [
            "name",
            "slug",
            "tagline",
            "description",
            "image",
            "order",
            "is_active",
        ]

        widgets = {
            "name": forms.TextInput(attrs={
                "placeholder": "e.g. Hair Treatments",
            }),
            "slug": forms.TextInput(attrs={
                "placeholder": "e.g. hair-treatments",
            }),
            "tagline": forms.TextInput(attrs={
                "placeholder": "A short category tagline",
            }),
            "description": forms.Textarea(attrs={
                "rows": 4,
                "placeholder": "Describe this service category...",
            }),
            "image": forms.ClearableFileInput(),
            "order": forms.NumberInput(attrs={
                "min": 0,
            }),
        }


class ServiceAdminForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = [
            "category",
            "name",
            "slug",
            "description",
            "price",
            "duration_minutes",
            "image",
            "is_featured",
            "is_popular",
            "is_bookable",
            "is_active",
            "order",
        ]

        widgets = {
            "category": forms.Select(),
            "name": forms.TextInput(attrs={
                "placeholder": "e.g. Luxury Hair Spa",
            }),
            "slug": forms.TextInput(attrs={
                "placeholder": "e.g. luxury-hair-spa",
            }),
            "description": forms.Textarea(attrs={
                "rows": 5,
                "placeholder": "Describe the service and its benefits...",
            }),
            "price": forms.NumberInput(attrs={
                "min": "0",
                "step": "0.01",
                "placeholder": "0.00",
            }),
            "duration_minutes": forms.NumberInput(attrs={
                "min": 1,
                "placeholder": "Duration in minutes",
            }),
            "image": forms.ClearableFileInput(),
            "order": forms.NumberInput(attrs={
                "min": 0,
            }),
        }

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

            categories = ServiceCategory.objects.filter(is_active=True)

            # Keep the existing category available when editing a service,
            # even if that category has been deactivated.
            if self.instance and self.instance.pk:
                categories = ServiceCategory.objects.filter(
                    Q(is_active=True) | Q(pk=self.instance.category_id)
                )

            self.fields["category"].queryset = categories.order_by(
                "order", "name"
            )

    def clean_price(self):
        price = self.cleaned_data["price"]

        if price < 0:
            raise forms.ValidationError("Price cannot be negative.")

        return price

    def clean_duration_minutes(self):
        duration = self.cleaned_data["duration_minutes"]

        if duration <= 0:
            raise forms.ValidationError(
                "Service duration must be greater than zero."
            )

        return duration
