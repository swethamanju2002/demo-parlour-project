from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.text import slugify


class ProductCategory(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=90, unique=True, blank=True)
    description = models.TextField(blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "name"]
        verbose_name_plural = "product categories"

    def save(self, *a, **kw):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*a, **kw)

    def __str__(self):
        return self.name


class Supplier(models.Model):
    name = models.CharField(max_length=120, unique=True)
    contact_person = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=15, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ProductQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def low_stock(self):
        """Active products at or below their reorder level."""
        return self.active().filter(quantity_on_hand__lte=F("reorder_level"))


class Product(models.Model):
    """Retail or consumable item. `quantity_on_hand` is changed ONLY through inventory.services."""

    category = models.ForeignKey(ProductCategory, on_delete=models.PROTECT, related_name="products")
    name = models.CharField(max_length=140)
    sku = models.CharField("SKU", max_length=40, unique=True)
    description = models.TextField(blank=True)
    unit = models.CharField(max_length=20, default="pcs", help_text="e.g. pcs, bottle, ml, g")
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"),
                                     validators=[MinValueValidator(Decimal("0.00"))])
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"),
                                        validators=[MinValueValidator(Decimal("0.00"))])
    quantity_on_hand = models.PositiveIntegerField(default=0, editable=False)
    reorder_level = models.PositiveIntegerField(default=0, help_text="Alert when stock is at or below this number.")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ["category__order", "name"]
        constraints = [
            models.CheckConstraint(condition=Q(cost_price__gte=0), name="product_cost_nonnegative"),
            models.CheckConstraint(condition=Q(selling_price__gte=0), name="product_price_nonnegative"),
        ]

    def save(self, *a, **kw):
        self.sku = (self.sku or "").strip().upper()
        super().save(*a, **kw)

    @property
    def is_low_stock(self):
        return self.is_active and self.quantity_on_hand <= self.reorder_level

    @property
    def stock_value(self):
        """Stock valued at current cost price."""
        return self.cost_price * self.quantity_on_hand

    def __str__(self):
        return f"{self.name} ({self.sku})"


class StockMovement(models.Model):
    """Append-only ledger. One row per stock change; rows are never edited or deleted."""

    class Type(models.TextChoices):
        IN = "in", "Stock in"
        OUT = "out", "Stock out"
        ADJUSTMENT = "adjustment", "Adjustment"

    class Reason(models.TextChoices):
        PURCHASE = "purchase", "Purchase received"
        OPENING = "opening", "Opening stock"
        CUSTOMER_RETURN = "customer_return", "Customer return"
        SALE = "sale", "Sold to customer"
        SERVICE_USE = "service_use", "Used in a service"
        DAMAGED = "damaged", "Damaged"
        EXPIRED = "expired", "Expired"
        SUPPLIER_RETURN = "supplier_return", "Returned to supplier"
        STOCKTAKE = "stocktake", "Stock count correction"
        OTHER = "other", "Other"

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="movements")
    movement_type = models.CharField(max_length=12, choices=Type.choices)
    reason = models.CharField(max_length=20, choices=Reason.choices)
    change = models.IntegerField(help_text="Signed quantity: positive adds stock, negative removes it.")
    quantity_before = models.PositiveIntegerField()
    quantity_after = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    reference = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)
    purchase = models.ForeignKey("inventory.Purchase", null=True, blank=True, editable=False,
                                 on_delete=models.PROTECT, related_name="stock_movements")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="stock_movements")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["product", "-created_at"])]
        constraints = [
            models.CheckConstraint(condition=~Q(change=0), name="stockmovement_change_nonzero"),
            models.CheckConstraint(condition=Q(quantity_after=F("quantity_before") + F("change")),
                                   name="stockmovement_balance_consistent"),
            # a purchase line can add stock to a product only once, so a repeated receipt cannot double-count
            models.UniqueConstraint(fields=["purchase", "product"], condition=Q(purchase__isnull=False),
                                    name="stockmovement_one_per_purchase_product"),
        ]

    def save(self, *a, **kw):
        if self.pk:
            raise ValidationError("Stock movements are permanent records and cannot be edited.")
        super().save(*a, **kw)

    def delete(self, *a, **kw):
        raise ValidationError("Stock movements are permanent records and cannot be deleted.")

    def __str__(self):
        return f"{self.product.sku} {self.change:+d} ({self.get_movement_type_display()})"


class Purchase(models.Model):
    """Stock bought from a supplier. Stock changes only when the purchase is received (inventory.purchasing)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ORDERED = "ordered", "Ordered"
        RECEIVED = "received", "Received"
        CANCELLED = "cancelled", "Cancelled"

    purchase_number = models.CharField(max_length=20, unique=True, editable=False)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchases")
    invoice_number = models.CharField("Supplier invoice no.", max_length=60, blank=True)
    purchase_date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), editable=False)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="purchases_created")
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="purchases_received")
    received_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-purchase_date", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(total_amount__gte=0), name="purchase_total_nonnegative"),
            models.CheckConstraint(condition=~Q(status="received") | Q(received_at__isnull=False),
                                   name="purchase_received_has_timestamp"),
        ]

    @property
    def is_editable(self):
        return self.status in (self.Status.DRAFT, self.Status.ORDERED)

    can_receive = is_editable
    can_cancel = is_editable

    def __str__(self):
        return self.purchase_number


class PurchaseItem(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="purchase_items")
    product_name = models.CharField(max_length=140, editable=False)   # snapshot, survives later renames
    quantity = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    line_total = models.DecimalField(max_digits=12, decimal_places=2, editable=False, default=Decimal("0.00"))

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="purchaseitem_quantity_positive"),
            models.CheckConstraint(condition=Q(unit_cost__gte=0), name="purchaseitem_cost_nonnegative"),
            models.UniqueConstraint(fields=["purchase", "product"], name="purchaseitem_one_line_per_product"),
        ]

    def save(self, *a, **kw):
        self.product_name = self.product.name
        self.line_total = (Decimal(self.quantity) * self.unit_cost).quantize(Decimal("0.01"))
        super().save(*a, **kw)

    def __str__(self):
        return f"{self.purchase_id} · {self.product_name} x{self.quantity}"
