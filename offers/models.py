from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class OfferQuerySet(models.QuerySet):
    def current(self, on=None):
        """Offers that are switched on and inside their validity window. Expired offers never appear."""
        on = on or timezone.localdate()
        return self.filter(is_active=True, valid_from__lte=on, valid_to__gte=on)


class Offer(models.Model):
    class DiscountType(models.TextChoices):
        PERCENT = "percent", "Percentage off"
        FLAT = "flat", "Flat amount off"

    title = models.CharField(max_length=120)
    slug = models.SlugField(max_length=130, unique=True, blank=True)
    summary = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    discount_type = models.CharField(max_length=8, choices=DiscountType.choices, default=DiscountType.PERCENT)
    discount_value = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    services = models.ManyToManyField("services.Service", blank=True, related_name="offers",
                                      help_text="Leave empty to apply to every service.")
    coupon_code = models.CharField(max_length=24, blank=True, db_index=True)
    is_package = models.BooleanField(default=False)
    valid_from = models.DateField()
    valid_to = models.DateField()
    terms = models.TextField(blank=True)
    banner = models.ImageField(upload_to="offers/", blank=True)
    is_active = models.BooleanField(default=True)

    objects = OfferQuerySet.as_manager()

    class Meta:
        ordering = ["valid_to"]

    def clean(self):
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValidationError("Valid-to date cannot be before the valid-from date.")
        if self.discount_type == self.DiscountType.PERCENT and self.discount_value and self.discount_value > 100:
            raise ValidationError("A percentage discount cannot exceed 100.")

    def save(self, *a, **kw):
        if not self.slug:
            base, slug, n = slugify(self.title), slugify(self.title), 2
            while Offer.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug, n = f"{base}-{n}", n + 1
            self.slug = slug
        if self.coupon_code:
            self.coupon_code = self.coupon_code.strip().upper()
        super().save(*a, **kw)

    @property
    def is_current(self):
        return self.is_active and self.valid_from <= timezone.localdate() <= self.valid_to

    @property
    def badge(self):
        v = self.discount_value.normalize()
        return f"{v:f}% off" if self.discount_type == self.DiscountType.PERCENT else f"₹{v:f} off"

    def __str__(self):
        return self.title
