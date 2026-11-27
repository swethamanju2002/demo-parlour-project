from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .forms import ExpenseForm
from .models import Expense, ExpenseCategory


User = get_user_model()


class ExpenseManagementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="expenseadmin",
            email="expenseadmin@example.com",
            password="TestPassword123!",
            role="ADMIN",
        )

        self.category = ExpenseCategory.objects.create(
            name="Utilities",
            slug="utilities",
        )

    def test_expense_model_creation(self):
        expense = Expense.objects.create(
            category=self.category,
            title="Electricity bill",
            amount=Decimal("2500.00"),
            expense_date=date.today(),
            payment_status=Expense.PaymentStatus.PAID,
            payment_method=Expense.PaymentMethod.UPI,
            created_by=self.admin,
        )

        self.assertEqual(expense.amount, Decimal("2500.00"))
        self.assertEqual(expense.category.name, "Utilities")

    def test_expense_form_requires_payment_method_when_paid(self):
        form = ExpenseForm(data={
            "category": self.category.pk,
            "title": "Water bill",
            "amount": "500.00",
            "expense_date": date.today().isoformat(),
            "payment_status": "paid",
            "payment_method": "",
            "paid_to": "",
            "reference_number": "",
            "notes": "",
        })

        self.assertFalse(form.is_valid())
        self.assertIn("payment_method", form.errors)

    def test_expense_form_rejects_method_for_pending(self):
        form = ExpenseForm(data={
            "category": self.category.pk,
            "title": "Internet bill",
            "amount": "1000.00",
            "expense_date": date.today().isoformat(),
            "payment_status": "pending",
            "payment_method": "upi",
            "paid_to": "",
            "reference_number": "",
            "notes": "",
        })

        self.assertFalse(form.is_valid())
        self.assertIn("payment_method", form.errors)

    def test_inactive_category_is_not_available_for_new_expense(self):
        self.category.is_active = False
        self.category.save()

        form = ExpenseForm()
        self.assertFalse(
            form.fields["category"].queryset.filter(
                pk=self.category.pk
            ).exists()
        )