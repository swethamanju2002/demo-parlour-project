
from django import forms
from django.db.models import Q

from services.models import Service
from .models import Offer


class OfferAdminForm(forms.ModelForm):

    class Meta:
        model = Offer

        fields = [
            "title",
            "summary",
            "description",
            "discount_type",
            "discount_value",
            "services",
            "coupon_code",
            "is_package",
            "valid_from",
            "valid_to",
            "terms",
            "banner",
            "is_active",
        ]

        widgets = {
            "title": forms.TextInput(attrs={
                "placeholder": "e.g. Festive Glow Offer",
            }),

            "summary": forms.TextInput(attrs={
                "placeholder": "Short promotional description",
            }),

            "description": forms.Textarea(attrs={
                "rows": 4,
                "placeholder": "Describe the offer...",
            }),

            "discount_type": forms.Select(),

            "discount_value": forms.NumberInput(attrs={
                "step": "0.01",
                "min": "0.01",
                "placeholder": "Enter discount value",
            }),

            "services": forms.CheckboxSelectMultiple(),

            "coupon_code": forms.TextInput(attrs={
                "placeholder": "e.g. GLOW20",
            }),

            "valid_from": forms.DateInput(attrs={
                "type": "date",
            }),

            "valid_to": forms.DateInput(attrs={
                "type": "date",
            }),

            "terms": forms.Textarea(attrs={
                "rows": 4,
                "placeholder": "Enter offer terms and conditions...",
            }),

            "banner": forms.ClearableFileInput(),

            "is_package": forms.CheckboxInput(),

            "is_active": forms.CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        services = Service.objects.filter(
            is_active=True
        )

        # Preserve already assigned inactive services while editing.
        if self.instance and self.instance.pk:
            services = Service.objects.filter(
                Q(is_active=True)
                | Q(offers=self.instance)
            ).distinct()

        self.fields["services"].queryset = services.order_by(
            "category__order",
            "category__name",
            "order",
            "name",
        )

        self.fields["services"].help_text = (
            "Select specific services for this offer. "
            "Leave all unchecked to apply the offer to every service."
        )

        self.fields["coupon_code"].required = False
        self.fields["description"].required = False
        self.fields["terms"].required = False
        self.fields["banner"].required = False

    def clean_coupon_code(self):
        coupon_code = self.cleaned_data.get("coupon_code", "")
        return coupon_code.strip().upper()

    def clean(self):
        cleaned_data = super().clean()

        discount_type = cleaned_data.get("discount_type")
        discount_value = cleaned_data.get("discount_value")
        valid_from = cleaned_data.get("valid_from")
        valid_to = cleaned_data.get("valid_to")

        if (
            discount_type == Offer.DiscountType.PERCENT
            and discount_value is not None
            and discount_value > 100
        ):
            self.add_error(
                "discount_value",
                "Percentage discount cannot exceed 100%.",
            )

        if (
            valid_from
            and valid_to
            and valid_to < valid_from
        ):
            self.add_error(
                "valid_to",
                "The end date cannot be before the start date.",
            )

        return cleaned_data
