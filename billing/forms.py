
from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.core.validators import RegexValidator

from services.models import Service
from .models import Invoice, Payment


User = get_user_model()


class InvoiceAdminForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ["due_date", "notes"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = [
            "amount",
            "method",
            "transaction_reference",
            "notes",
        ]
        widgets = {
            "amount": forms.NumberInput(attrs={
                "step": "0.01",
                "min": "0.01",
                "placeholder": "Enter payment amount",
            }),
            "transaction_reference": forms.TextInput(attrs={
                "placeholder": "UPI / card / bank reference (optional)",
            }),
            "notes": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": "Payment notes (optional)",
            }),
        }

    def __init__(self, *args, invoice=None, **kwargs):
        self.invoice = invoice
        super().__init__(*args, **kwargs)

    def clean_amount(self):
        amount = self.cleaned_data["amount"]

        if amount <= Decimal("0.00"):
            raise forms.ValidationError("Enter an amount greater than zero.")

        if self.invoice and amount > self.invoice.balance_due:
            raise forms.ValidationError(
                f"Amount cannot exceed the outstanding balance "
                f"of Rs. {self.invoice.balance_due:.2f}."
            )

        return amount


class ManualInvoiceForm(forms.Form):
    customer = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        empty_label="Choose an existing customer",
    )

    new_customer_name = forms.CharField(
        required=False,
        max_length=150,
        label="Customer name",
        widget=forms.TextInput(attrs={
            "placeholder": "Enter customer's full name",
            "autocomplete": "name",
        }),
    )

    new_customer_phone = forms.CharField(
        required=False,
        max_length=15,
        label="Phone number",
        validators=[
            RegexValidator(
                r"^[0-9+\- ]{8,15}$",
                "Enter a valid phone number.",
            )
        ],
        widget=forms.TextInput(attrs={
            "placeholder": "Enter phone number",
            "autocomplete": "tel",
        }),
    )

    new_customer_email = forms.EmailField(
        required=False,
        label="Email address",
        widget=forms.EmailInput(attrs={
            "placeholder": "Email address (optional)",
            "autocomplete": "email",
        }),
    )

    services = forms.ModelMultipleChoiceField(
        queryset=Service.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        help_text="Search and select the services provided.",
    )

    discount_amount = forms.DecimalField(
        required=False,
        initial=Decimal("0.00"),
        min_value=Decimal("0.00"),
        decimal_places=2,
        max_digits=10,
        widget=forms.NumberInput(attrs={
            "step": "0.01",
            "min": "0",
            "placeholder": "0.00",
        }),
    )

    tax_amount = forms.DecimalField(
        required=False,
        initial=Decimal("0.00"),
        min_value=Decimal("0.00"),
        decimal_places=2,
        max_digits=10,
        widget=forms.NumberInput(attrs={
            "step": "0.01",
            "min": "0",
            "placeholder": "0.00",
        }),
    )

    due_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "rows": 3,
            "placeholder": "Additional bill notes (optional)",
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["customer"].queryset = User.objects.filter(
            is_active=True,
            role=User.Role.CUSTOMER,
        ).order_by("first_name", "last_name", "username")

        self.fields["services"].queryset = (
            Service.objects.active()
            .select_related("category")
            .order_by("category__order", "order", "name")
        )

        self.fields["services"].choices = [
            (
                service.pk,
                f"{service.name} — Rs. {service.price:.2f}",
            )
            for service in self.fields["services"].queryset
        ]

    def clean(self):
        cleaned_data = super().clean()

        customer = cleaned_data.get("customer")
        customer_name = (cleaned_data.get("new_customer_name") or "").strip()
        customer_phone = (cleaned_data.get("new_customer_phone") or "").strip()
        customer_email = (cleaned_data.get("new_customer_email") or "").strip()

        if not customer:
            if not customer_name:
                self.add_error(
                    "new_customer_name",
                    "Enter the walk-in customer's name.",
                )

            if not customer_phone:
                self.add_error(
                    "new_customer_phone",
                    "Enter the walk-in customer's phone number.",
                )

            if customer_email and User.objects.filter(
                email__iexact=customer_email
            ).exists():
                self.add_error(
                    "new_customer_email",
                    "An account with this email already exists. Select that customer instead.",
                )

        services = cleaned_data.get("services")
        discount = cleaned_data.get("discount_amount") or Decimal("0.00")
        tax = cleaned_data.get("tax_amount") or Decimal("0.00")

        if services is not None:
            selected_services = list(services)

            if not selected_services:
                self.add_error("services", "Select at least one service.")

            subtotal = sum(
                (service.price for service in selected_services),
                Decimal("0.00"),
            )

            if discount > subtotal:
                self.add_error(
                    "discount_amount",
                    "Discount cannot exceed the subtotal.",
                )

            total = subtotal - discount + tax

            if total <= Decimal("0.00"):
                self.add_error(
                    "tax_amount",
                    "The final invoice total must be greater than zero.",
                )

        return cleaned_data
