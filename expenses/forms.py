from django import forms

from .models import Expense, ExpenseCategory


class ExpenseCategoryForm(forms.ModelForm):
    class Meta:
        model = ExpenseCategory
        fields = ["name", "description", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "adm-input",
                "placeholder": "Category name",
            }),
            "description": forms.Textarea(attrs={
                "class": "adm-input",
                "rows": 3,
            }),
            "is_active": forms.CheckboxInput(),
        }


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = [
            "category",
            "title",
            "amount",
            "expense_date",
            "payment_status",
            "payment_method",
            "paid_to",
            "reference_number",
            "notes",
        ]
        widgets = {
            "category": forms.Select(attrs={"class": "adm-input"}),
            "title": forms.TextInput(attrs={
                "class": "adm-input",
                "placeholder": "e.g. Electricity bill",
            }),
            "amount": forms.NumberInput(attrs={
                "class": "adm-input",
                "step": "0.01",
                "min": "0.01",
            }),
            "expense_date": forms.DateInput(attrs={
                "class": "adm-input",
                "type": "date",
            }),
            "payment_status": forms.Select(attrs={"class": "adm-input"}),
            "payment_method": forms.Select(attrs={"class": "adm-input"}),
            "paid_to": forms.TextInput(attrs={"class": "adm-input"}),
            "reference_number": forms.TextInput(attrs={"class": "adm-input"}),
            "notes": forms.Textarea(attrs={
                "class": "adm-input",
                "rows": 3,
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = ExpenseCategory.objects.filter(
            is_active=True
        )

        if self.instance.pk and not self.instance.category.is_active:
            self.fields["category"].queryset = (
                ExpenseCategory.objects.filter(
                    pk=self.instance.category_id
                ) | ExpenseCategory.objects.filter(is_active=True)
            ).distinct()

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get("payment_status")
        method = cleaned.get("payment_method")

        if status == Expense.PaymentStatus.PENDING and method:
            self.add_error(
                "payment_method",
                "Select a payment method only after the expense is paid.",
            )

        if status == Expense.PaymentStatus.PAID and not method:
            self.add_error(
                "payment_method",
                "Select the payment method for a paid expense.",
            )

        return cleaned