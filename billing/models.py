
from decimal import Decimal
import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone


class Invoice(models.Model):
    """A financial document generated for a salon booking."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ISSUED = "issued", "Issued"
        VOID = "void", "Void"

    booking = models.OneToOneField(
    "bookings.Booking",
    on_delete=models.PROTECT,
    related_name="invoice",
    null=True,
    blank=True,
)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="invoices",
    )

    invoice_number = models.CharField(
        max_length=30,
        unique=True,
        editable=False,
    )

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.ISSUED,
    )

    issue_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(null=True, blank=True)

    # Financial snapshots. These must not change when service prices change.
    subtotal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    tax_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-issue_date", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(subtotal__gte=0),
                name="invoice_subtotal_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(discount_amount__gte=0),
                name="invoice_discount_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(tax_amount__gte=0),
                name="invoice_tax_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(total_amount__gte=0),
                name="invoice_total_nonnegative",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            date_part = timezone.localdate().strftime("%Y%m%d")
            self.invoice_number = (
                f"DQA-{date_part}-{uuid.uuid4().hex[:6].upper()}"
            )

        super().save(*args, **kwargs)

    @property
    def paid_amount(self):
        """Total successfully recorded payments."""
        result = self.payments.filter(
            status=Payment.Status.COMPLETED
        ).aggregate(total=Sum("amount"))

        return result["total"] or Decimal("0.00")

    @property
    def balance_due(self):
        """Outstanding amount, never below zero."""
        return max(
            self.total_amount - self.paid_amount,
            Decimal("0.00"),
        )

    @property
    def payment_status(self):
        """Payment status derived from successful payment records."""
        if self.paid_amount >= self.total_amount:
            return "paid"

        if self.paid_amount > Decimal("0.00"):
            return "partial"

        return "unpaid"

    def __str__(self):
        return self.invoice_number


class InvoiceItem(models.Model):
    """Service details copied into an invoice as permanent snapshots."""

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="items",
    )

    service_name = models.CharField(max_length=120)

    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    duration_minutes = models.PositiveSmallIntegerField()

    line_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(unit_price__gte=0),
                name="invoice_item_price_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(line_total__gte=0),
                name="invoice_item_total_nonnegative",
            ),
        ]

    def __str__(self):
        return f"{self.service_name} - {self.invoice.invoice_number}"


class Payment(models.Model):
    """A payment transaction recorded against an invoice."""

    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        UPI = "upi", "UPI"
        CARD = "card", "Card"
        BANK_TRANSFER = "bank_transfer", "Bank Transfer"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        related_name="payments",
    )

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    method = models.CharField(
        max_length=20,
        choices=Method.choices,
    )

    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.COMPLETED,
    )

    transaction_reference = models.CharField(
        max_length=120,
        blank=True,
    )

    paid_at = models.DateTimeField(
        default=timezone.now,
    )

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_payments",
    )

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-paid_at", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="payment_amount_positive",
            ),
        ]

    def __str__(self):
        return (
            f"{self.invoice.invoice_number} - "
            f"{self.amount} ({self.get_method_display()})"
        )
