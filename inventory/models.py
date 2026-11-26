from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
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
        ]

    def save(self, *a, **kw):
        if self.pk:
            raise ValidationError("Stock movements are permanent records and cannot be edited.")
        super().save(*a, **kw)

    def delete(self, *a, **kw):
        raise ValidationError("Stock movements are permanent records and cannot be deleted.")

    def __str__(self):
        return f"{self.product.sku} {self.change:+d} ({self.get_movement_type_display()})"
