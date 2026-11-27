import csv
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.permissions import salon_admin_required

from .forms import ExpenseCategoryForm, ExpenseForm
from .models import Expense, ExpenseCategory


def _filtered_expenses(request):
    expenses = Expense.objects.select_related("category", "created_by")

    start = request.GET.get("start_date", "").strip()
    end = request.GET.get("end_date", "").strip()
    category = request.GET.get("category", "").strip()
    status = request.GET.get("status", "").strip()

    if start:
        try:
            expenses = expenses.filter(expense_date__gte=date.fromisoformat(start))
        except ValueError:
            start = ""

    if end:
        try:
            expenses = expenses.filter(expense_date__lte=date.fromisoformat(end))
        except ValueError:
            end = ""

    if category.isdigit():
        expenses = expenses.filter(category_id=int(category))

    if status in Expense.PaymentStatus.values:
        expenses = expenses.filter(payment_status=status)

    return expenses, {
        "start_date": start,
        "end_date": end,
        "selected_category": category,
        "selected_status": status,
    }


@salon_admin_required
def dashboard(request):
    today = timezone.localdate()
    month_start = today.replace(day=1)

    expenses = Expense.objects.select_related("category")
    month_expenses = expenses.filter(expense_date__gte=month_start)

    context = {
        "today_total": expenses.filter(
            expense_date=today,
            payment_status=Expense.PaymentStatus.PAID,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00"),
        "month_total": month_expenses.filter(
            payment_status=Expense.PaymentStatus.PAID,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00"),
        "pending_total": expenses.filter(
            payment_status=Expense.PaymentStatus.PENDING,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00"),
        "recent_expenses": expenses[:8],
    }
    return render(request, "admin_panel/expenses/dashboard.html", context)


@salon_admin_required
def expense_list(request):
    expenses, filters = _filtered_expenses(request)

    context = {
        "expenses": Paginator(expenses, 20).get_page(request.GET.get("page")),
        "categories": ExpenseCategory.objects.filter(is_active=True),
        **filters,
    }
    return render(request, "admin_panel/expenses/expense_list.html", context)


@salon_admin_required
def expense_create(request):
    form = ExpenseForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        expense = form.save(commit=False)
        expense.created_by = request.user
        expense.save()
        messages.success(request, "Expense recorded successfully.")
        return redirect("admin_panel:expense_list")

    return render(request, "admin_panel/expenses/form.html", {
        "form": form,
        "page_title": "Add Expense",
    })


@salon_admin_required
def expense_edit(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    form = ExpenseForm(request.POST or None, instance=expense)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Expense updated successfully.")
        return redirect("admin_panel:expense_list")

    return render(request, "admin_panel/expenses/form.html", {
        "form": form,
        "page_title": "Edit Expense",
        "expense": expense,
    })


@salon_admin_required
@require_POST
def expense_delete(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    expense.delete()
    messages.success(request, "Expense deleted successfully.")
    return redirect("admin_panel:expense_list")


@salon_admin_required
def category_list(request):
    categories = ExpenseCategory.objects.all()
    return render(request, "admin_panel/expenses/category_list.html", {
        "categories": categories,
    })


@salon_admin_required
def category_create(request):
    form = ExpenseCategoryForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Expense category created.")
        return redirect("admin_panel:expense_categories")

    return render(request, "admin_panel/expenses/form.html", {
        "form": form,
        "page_title": "Add Expense Category",
    })


@salon_admin_required
def category_edit(request, pk):
    category = get_object_or_404(ExpenseCategory, pk=pk)
    form = ExpenseCategoryForm(request.POST or None, instance=category)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Expense category updated.")
        return redirect("admin_panel:expense_categories")

    return render(request, "admin_panel/expenses/form.html", {
        "form": form,
        "page_title": "Edit Expense Category",
    })


@salon_admin_required
@require_POST
def category_delete(request, pk):
    category = get_object_or_404(ExpenseCategory, pk=pk)

    if category.expenses.exists():
        messages.error(
            request,
            "This category has expenses. Deactivate it instead of deleting it.",
        )
    else:
        category.delete()
        messages.success(request, "Expense category deleted.")

    return redirect("admin_panel:expense_categories")


@salon_admin_required
def monthly_report(request):
    year_value = request.GET.get("year", str(timezone.localdate().year))

    try:
        year = int(year_value)
        if not 2000 <= year <= 2100:
            raise ValueError
    except ValueError:
        year = timezone.localdate().year

    rows = []
    for month in range(1, 13):
        total = Expense.objects.filter(
            expense_date__year=year,
            expense_date__month=month,
            payment_status=Expense.PaymentStatus.PAID,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        pending = Expense.objects.filter(
            expense_date__year=year,
            expense_date__month=month,
            payment_status=Expense.PaymentStatus.PENDING,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        rows.append({
            "month": date(year, month, 1).strftime("%B"),
            "paid": total,
            "pending": pending,
        })

    return render(request, "admin_panel/expenses/monthly_report.html", {
        "year": year,
        "rows": rows,
        "years": range(timezone.localdate().year - 4, timezone.localdate().year + 1),
    })


@salon_admin_required
def expense_export(request):
    expenses, _ = _filtered_expenses(request)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="expenses.csv"'

    writer = csv.writer(response)
    writer.writerow([
        "Date", "Title", "Category", "Amount", "Payment Status",
        "Payment Method", "Paid To", "Reference", "Notes",
    ])

    for expense in expenses:
        writer.writerow([
            expense.expense_date,
            expense.title,
            expense.category.name,
            expense.amount,
            expense.get_payment_status_display(),
            expense.get_payment_method_display(),
            expense.paid_to,
            expense.reference_number,
            expense.notes,
        ])

    return response