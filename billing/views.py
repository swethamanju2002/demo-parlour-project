
from datetime import date
from decimal import Decimal
from .models import Invoice
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from accounts.permissions import salon_admin_required
from bookings.models import Booking
from .forms import InvoiceAdminForm, PaymentForm, ManualInvoiceForm
from .models import Invoice, Payment
import uuid

from django.contrib.auth import get_user_model
from django.db import transaction
from .services import (
    generate_invoice,
    generate_manual_invoice,
    record_payment,
    update_payment_status,
)
User = get_user_model()
def _invoice_queryset():
    return Invoice.objects.select_related(
        "booking",
        "customer",
        "booking__staff",
    ).prefetch_related("items", "payments")


@salon_admin_required
def billing_dashboard(request):
    invoices = _invoice_queryset()

    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    payment_status = request.GET.get("payment_status", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()

    if query:
        invoices = invoices.filter(
            Q(invoice_number__icontains=query)
            | Q(customer__username__icontains=query)
            | Q(customer__first_name__icontains=query)
            | Q(customer__last_name__icontains=query)
            | Q(customer__email__icontains=query)
            | Q(booking__public_id__icontains=query)
        )

    if status in dict(Invoice.Status.choices):
        invoices = invoices.filter(status=status)

    if date_from:
        invoices = invoices.filter(issue_date__gte=date_from)

    if date_to:
        invoices = invoices.filter(issue_date__lte=date_to)

    paginator = Paginator(invoices, 12)
    page_obj = paginator.get_page(request.GET.get("page"))

    all_invoices = _invoice_queryset()

    issued = all_invoices.filter(status=Invoice.Status.ISSUED)
    total_invoiced = issued.aggregate(
        total=Sum("total_amount")
    )["total"] or Decimal("0.00")

    completed_payments = Payment.objects.filter(
        status=Payment.Status.COMPLETED
    )
    total_collected = completed_payments.aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")

    outstanding = sum(
        (invoice.balance_due for invoice in issued),
        Decimal("0.00"),
    )
    uninvoiced_bookings = Booking.objects.filter(
    status=Booking.Status.COMPLETED
    ).select_related(
        "customer",
        "staff",
    ).prefetch_related("items").filter(
        invoice__isnull=True
    ).order_by("-start")[:20]

    context = {
        "page_obj": page_obj,
        "invoices": page_obj.object_list,
        "query": query,
        "selected_status": status,
        "selected_payment_status": payment_status,
        "date_from": date_from,
        "date_to": date_to,
        "total_invoiced": total_invoiced,
        "total_collected": total_collected,
        "outstanding": outstanding,
        "uninvoiced_bookings": uninvoiced_bookings,
        "invoice_count": issued.count(),
    }

    if payment_status in {"paid", "partial", "unpaid"}:
        context["invoices"] = [
            invoice for invoice in page_obj.object_list
            if invoice.payment_status == payment_status
        ]

    return render(request, "admin_panel/billing.html", context)


@salon_admin_required
def manual_invoice_create(request):
    if request.method == "POST":
        form = ManualInvoiceForm(request.POST)

        if form.is_valid():
            try:
                with transaction.atomic():
                    if request.POST.get("customer_type") == "new":
                        customer_name = form.cleaned_data["new_customer_name"].strip()
                        customer_email = (
                            form.cleaned_data.get("new_customer_email") or ""
                        ).strip()

                        unique_id = uuid.uuid4().hex

                        if not customer_email:
                            customer_email = f"walkin_{unique_id}@dq-aesthetic.local"

                        customer = User(
                            username=f"walkin_{unique_id}",
                            email=customer_email,
                            first_name=customer_name,
                            phone=form.cleaned_data["new_customer_phone"],
                            role=User.Role.CUSTOMER,
                            is_active=True,
                        )
                        customer.set_unusable_password()
                        customer.save()

                    else:
                        customer = form.cleaned_data.get("customer")

                        if not customer:
                            form.add_error(
                                "customer",
                                "Please select an existing customer.",
                            )
                            raise ValidationError(
                                "Please select a customer."
                            )

                    invoice = generate_manual_invoice(
                        customer=customer,
                        services=form.cleaned_data["services"],
                        discount_amount=(
                            form.cleaned_data["discount_amount"]
                            or Decimal("0.00")
                        ),
                        tax_amount=(
                            form.cleaned_data["tax_amount"]
                            or Decimal("0.00")
                        ),
                        due_date=form.cleaned_data["due_date"],
                        notes=form.cleaned_data["notes"],
                    )

                messages.success(
                    request,
                    f"Invoice {invoice.invoice_number} created successfully.",
                )
                return redirect(
                    "admin_panel:invoice_detail",
                    invoice_id=invoice.pk,
                )

            except ValidationError as exc:
                if not form.non_field_errors():
                    form.add_error(None, "; ".join(exc.messages))

        messages.error(request, "Please correct the errors below.")

    else:
        form = ManualInvoiceForm()

    return render(
        request,
        "admin_panel/manual_invoice_form.html",
        {"form": form},
    )

@salon_admin_required
def invoice_generate(request, booking_id):
    if request.method != "POST":
        return redirect("admin_panel:appointments")

    booking = get_object_or_404(Booking, pk=booking_id)

    form = InvoiceAdminForm(request.POST)

    if not form.is_valid():
        messages.error(request, "Please check the invoice details.")
        return redirect("admin_panel:billing")
    try:
        invoice = generate_invoice(
            booking_id=booking_id,
            due_date=form.cleaned_data.get("due_date"),
            notes=form.cleaned_data.get("notes", ""),
            created_by=request.user,
        )

        messages.success(request, "Invoice generated successfully.")

    except ValidationError as exc:
        # If an invoice was already created for this booking,
        # open that invoice instead of trying to create another.
        existing_invoice = Invoice.objects.filter(
            booking_id=booking_id
        ).first()

        if existing_invoice:
            messages.info(request, "An invoice already exists for this booking.")
            return redirect(
                "admin_panel:invoice_detail",
                invoice_id=existing_invoice.pk,
            )

        messages.error(request, "; ".join(exc.messages))
        return redirect("admin_panel:billing")

    return redirect(
        "admin_panel:invoice_detail",
        invoice_id=invoice.pk,
    )
    if created:
        messages.success(request, "Invoice generated successfully.")
        return redirect("admin_panel:invoice_detail", invoice_id=invoice.pk)
    else:
        messages.info(request, f"An invoice already exists: {invoice.invoice_number}")

    return redirect("admin_panel:invoice_detail", invoice_id=invoice.pk)


@salon_admin_required
def invoice_detail(request, invoice_id):
    invoice = get_object_or_404(_invoice_queryset(), pk=invoice_id)

    payment_form = PaymentForm(invoice=invoice)

    context = {
        "invoice": invoice,
        "payment_form": payment_form,
        "payments": invoice.payments.select_related("recorded_by").all(),
        "invoice_form": InvoiceAdminForm(instance=invoice),
        "payment_status_choices": Payment.Status.choices,
    }

    return render(request, "admin_panel/invoice_detail.html", context)


@salon_admin_required
@require_POST
def payment_create(request, invoice_id):
    invoice = get_object_or_404(Invoice, pk=invoice_id)
    form = PaymentForm(request.POST, invoice=invoice)

    if not form.is_valid():
        messages.error(
            request,
            " ".join(
                error for errors in form.errors.values()
                for error in errors
            ),
        )
        return redirect("admin_panel:invoice_detail", invoice_id=invoice.pk)

    try:
        payment = record_payment(
            invoice.pk,
            amount=form.cleaned_data["amount"],
            method=form.cleaned_data["method"],
            transaction_reference=form.cleaned_data["transaction_reference"],
            notes=form.cleaned_data["notes"],
            recorded_by=request.user,
        )
    except (ValidationError, ValueError) as exc:
        messages.error(request, "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc))
        return redirect("admin_panel:invoice_detail", invoice_id=invoice.pk)

    messages.success(request, f"Payment of ₹{payment.amount:.2f} recorded.")
    return redirect("admin_panel:invoice_detail", invoice_id=invoice.pk)


@salon_admin_required
@require_POST
def payment_status_update(request, payment_id):
    payment = get_object_or_404(Payment, pk=payment_id)
    new_status = request.POST.get("status", "")

    try:
        update_payment_status(payment.pk, new_status)
        messages.success(request, "Payment status updated.")
    except (ValidationError, ValueError) as exc:
        messages.error(request, "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc))

    return redirect("admin_panel:invoice_detail", invoice_id=payment.invoice_id)


@salon_admin_required
@require_POST
def invoice_update(request, invoice_id):
    invoice = get_object_or_404(Invoice, pk=invoice_id)
    form = InvoiceAdminForm(request.POST, instance=invoice)

    if form.is_valid():
        form.save()
        messages.success(request, "Invoice details updated.")
    else:
        messages.error(request, "Please correct the invoice details.")

    return redirect("admin_panel:invoice_detail", invoice_id=invoice.pk)


@salon_admin_required
def financial_reports(request):
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()

    payments = Payment.objects.filter(status=Payment.Status.COMPLETED)
    invoices = Invoice.objects.filter(status=Invoice.Status.ISSUED)

    if date_from:
        payments = payments.filter(paid_at__date__gte=date_from)
        invoices = invoices.filter(issue_date__gte=date_from)

    if date_to:
        payments = payments.filter(paid_at__date__lte=date_to)
        invoices = invoices.filter(issue_date__lte=date_to)

    collected = payments.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    invoiced = invoices.aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")

    method_rows = list(
        payments.values("method").annotate(
            total=Sum("amount"),
            count=Count("id"),
        ).order_by("method")
    )

    for row in method_rows:
        row["label"] = dict(Payment.Method.choices).get(
            row["method"], row["method"]
        )

    context = {
        "date_from": date_from,
        "date_to": date_to,
        "collected": collected,
        "invoiced": invoiced,
        "method_rows": method_rows,
        "payment_count": payments.count(),
        "payments": payments.select_related(
            "invoice", "invoice__customer"
        )[:100],
    }

    return render(request, "admin_panel/financial_reports.html", context)


def customer_billing(request):
    if not request.user.is_authenticated:
        return redirect("accounts:login")

    invoices = _invoice_queryset().filter(
        customer=request.user
    )

    return render(
        request,
        "client/billing.html",
        {"invoices": invoices},
    )


def customer_invoice_detail(request, invoice_id):
    if not request.user.is_authenticated:
        return redirect("accounts:login")

    invoice = get_object_or_404(
        _invoice_queryset(),
        pk=invoice_id,
        customer=request.user,
    )

    return render(
        request,
        "client/invoice_detail.html",
        {"invoice": invoice},
    )
