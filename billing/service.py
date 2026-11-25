
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from bookings.models import Booking
from .models import Invoice, InvoiceItem, Payment


@transaction.atomic
def generate_invoice(booking_id, *, due_date=None, notes="", created_by=None):
    booking = Booking.objects.select_for_update().get(pk=booking_id)

    if booking.status != Booking.Status.COMPLETED:
        raise ValidationError("An invoice can only be generated for a completed booking.")

    existing = Invoice.objects.filter(booking=booking).first()
    if existing:
        return existing, False

    booking_items = list(booking.items.all())

    if not booking_items:
        raise ValidationError("This booking has no service items to invoice.")

    # Preserve the booking's final price. Never use current service prices.
    subtotal = booking.total_price or Decimal("0.00")

    if subtotal < Decimal("0.00"):
        raise ValidationError("The booking total cannot be negative.")

    invoice = Invoice.objects.create(
        booking=booking,
        customer=booking.customer,
        due_date=due_date,
        notes=notes,
        subtotal=subtotal,
        discount_amount=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        total_amount=subtotal,
    )

    for item in booking_items:
        InvoiceItem.objects.create(
            invoice=invoice,
            service_name=item.service_name,
            unit_price=item.unit_price,
            duration_minutes=item.duration_minutes,
            line_total=item.unit_price,
        )

    return invoice, True


@transaction.atomic
def record_payment(
    invoice_id,
    *,
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

    if amount <= Decimal("0.00"):
        raise ValidationError("Payment amount must be greater than zero.")

    paid = invoice.payments.filter(
        status=Payment.Status.COMPLETED
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    balance = max(invoice.total_amount - paid, Decimal("0.00"))

    if amount > balance:
        raise ValidationError(
            f"Payment exceeds the outstanding balance of ₹{balance:.2f}."
        )

    return Payment.objects.create(
        invoice=invoice,
        amount=amount,
        method=method,
        status=Payment.Status.COMPLETED,
        transaction_reference=transaction_reference,
        notes=notes,
        recorded_by=recorded_by,
    )


@transaction.atomic
def update_payment_status(payment_id, new_status):
    payment = Payment.objects.select_for_update().select_related("invoice").get(
        pk=payment_id
    )

    allowed = {
        Payment.Status.PENDING,
        Payment.Status.COMPLETED,
        Payment.Status.FAILED,
        Payment.Status.REFUNDED,
    }

    if new_status not in allowed:
        raise ValidationError("Invalid payment status.")

    if payment.status == Payment.Status.REFUNDED:
        raise ValidationError("A refunded payment cannot be changed.")

    if new_status == Payment.Status.COMPLETED:
        invoice = Invoice.objects.select_for_update().get(pk=payment.invoice_id)

        other_paid = invoice.payments.filter(
            status=Payment.Status.COMPLETED
        ).exclude(pk=payment.pk).aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0.00")

        if other_paid + payment.amount > invoice.total_amount:
            raise ValidationError(
                "This payment would exceed the invoice balance."
            )

    payment.status = new_status
    payment.save(update_fields=["status"])
    return payment
