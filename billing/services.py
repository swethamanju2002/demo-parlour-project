
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from bookings.models import Booking

from .models import Invoice, InvoiceItem, Payment


@transaction.atomic
def generate_invoice(booking_id, due_date=None, notes="", created_by=None):
    booking = (
        Booking.objects.select_for_update()
        .select_related("customer")
        .prefetch_related("items")
        .get(pk=booking_id)
    )

    if booking.status != Booking.Status.COMPLETED:
        raise ValidationError("Invoices can only be generated for completed bookings.")

    if Invoice.objects.filter(booking=booking).exists():
        raise ValidationError("An invoice already exists for this booking.")

    booking_items = list(booking.items.all())

    if not booking_items:
        raise ValidationError("Cannot generate an invoice without booking items.")

    subtotal = sum(
        (item.unit_price for item in booking_items),
        Decimal("0.00"),
    )

    total = booking.total_price

    invoice = Invoice.objects.create(
        booking=booking,
        customer=booking.customer,
        status=Invoice.Status.ISSUED,
        issue_date=timezone.localdate(),
        due_date=due_date,
        subtotal=subtotal,
        discount_amount=max(subtotal - total, Decimal("0.00")),
        tax_amount=Decimal("0.00"),
        total_amount=total,
        notes=notes,
    )

    InvoiceItem.objects.bulk_create([
        InvoiceItem(
            invoice=invoice,
            service_name=item.service_name,
            unit_price=item.unit_price,
            duration_minutes=item.duration_minutes,
            line_total=item.unit_price,
        )
        for item in booking_items
    ])

    return invoice


@transaction.atomic
def record_payment(
    invoice_id,
    amount,
    method,
    transaction_reference="",
    notes="",
    recorded_by=None,
):
    invoice = Invoice.objects.select_for_update().get(pk=invoice_id)

    if invoice.status != Invoice.Status.ISSUED:
        raise ValidationError("Payments can only be recorded for issued invoices.")

    amount = Decimal(str(amount))

    if amount <= 0:
        raise ValidationError("Payment amount must be greater than zero.")

    if amount > invoice.balance_due:
        raise ValidationError("Payment amount cannot exceed the outstanding balance.")

    if method not in dict(Payment.Method.choices):
        raise ValidationError("Select a valid payment method.")

    return Payment.objects.create(
        invoice=invoice,
        amount=amount,
        method=method,
        status=Payment.Status.COMPLETED,
        transaction_reference=transaction_reference,
        paid_at=timezone.now(),
        recorded_by=recorded_by,
        notes=notes,
    )


@transaction.atomic
def update_payment_status(payment_id, new_status):
    payment = (
        Payment.objects.select_for_update()
        .select_related("invoice")
        .get(pk=payment_id)
    )

    if new_status not in dict(Payment.Status.choices):
        raise ValidationError("Invalid payment status.")

    if payment.status == Payment.Status.REFUNDED:
        raise ValidationError("A refunded payment cannot be changed.")

    if new_status == Payment.Status.COMPLETED:
        other_completed = (
            Payment.objects.filter(
                invoice=payment.invoice,
                status=Payment.Status.COMPLETED,
            )
            .exclude(pk=payment.pk)
        )

        already_paid = sum(
            (item.amount for item in other_completed),
            Decimal("0.00"),
        )

        if already_paid + payment.amount > payment.invoice.total_amount:
            raise ValidationError(
                "This payment would exceed the invoice total."
            )

        if payment.invoice.status != Invoice.Status.ISSUED:
            raise ValidationError("This invoice is not available for payment.")

        payment.paid_at = payment.paid_at or timezone.now()

    payment.status = new_status
    payment.save(update_fields=["status", "paid_at"])

    return payment

@transaction.atomic
def generate_manual_invoice(
    customer,
    services,
    discount_amount=Decimal("0.00"),
    tax_amount=Decimal("0.00"),
    due_date=None,
    notes="",
):
    """Create an invoice without an appointment booking."""

    from services.models import Service

    service_ids = [service.pk for service in services]

    selected_services = list(
        Service.objects.active()
        .filter(pk__in=service_ids)
        .select_related("category")
        .order_by("category__order", "order", "name")
    )

    if not selected_services:
        raise ValidationError("Select at least one active service.")

    if len(selected_services) != len(set(service_ids)):
        raise ValidationError(
            "One or more selected services are no longer active."
        )

    discount_amount = Decimal(str(discount_amount or "0.00"))
    tax_amount = Decimal(str(tax_amount or "0.00"))

    if discount_amount < 0 or tax_amount < 0:
        raise ValidationError("Discount and tax cannot be negative.")

    subtotal = sum(
        (service.price for service in selected_services),
        Decimal("0.00"),
    )

    if discount_amount > subtotal:
        raise ValidationError("Discount cannot exceed the subtotal.")

    total_amount = subtotal - discount_amount + tax_amount

    if total_amount <= 0:
        raise ValidationError("Invoice total must be greater than zero.")

    invoice = Invoice.objects.create(
        booking=None,
        customer=customer,
        status=Invoice.Status.ISSUED,
        issue_date=timezone.localdate(),
        due_date=due_date,
        subtotal=subtotal,
        discount_amount=discount_amount,
        tax_amount=tax_amount,
        total_amount=total_amount,
        notes=notes,
    )

    InvoiceItem.objects.bulk_create([
        InvoiceItem(
            invoice=invoice,
            service_name=service.name,
            unit_price=service.price,
            duration_minutes=service.duration_minutes,
            line_total=service.price,
        )
        for service in selected_services
    ])

    return invoice
