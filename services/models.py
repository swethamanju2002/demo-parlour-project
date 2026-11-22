from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class ServiceCategory(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=90, unique=True, blank=True)
    tagline = models.CharField(max_length=160, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="categories/", blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "name"]
        verbose_name_plural = "service categories"

    def save(self, *a, **kw):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*a, **kw)

    def __str__(self):
        return self.name


class ServiceQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True, category__is_active=True)

    def bookable(self):
        return self.active().filter(is_bookable=True)


class Service(models.Model):
    category = models.ForeignKey(ServiceCategory, on_delete=models.PROTECT, related_name="services")
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=130, unique=True, blank=True)
    description = models.TextField()
    # Current list price. Invoices copy this into an immutable snapshot (see billing, Phase 5).
    price = models.DecimalField(max_digits=9, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    duration_minutes = models.PositiveSmallIntegerField(validators=[MinValueValidator(5)])
    image = models.ImageField(upload_to="services/", blank=True)
    is_featured = models.BooleanField(default=False)
    is_popular = models.BooleanField(default=False)
    is_bookable = models.BooleanField(default=True, help_text="Untick for items handled by enquiry only, e.g. academy courses.")
    is_active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)

    objects = ServiceQuerySet.as_manager()

    class Meta:
        ordering = ["category__order", "order", "name"]
        indexes = [models.Index(fields=["is_active", "is_featured"]), models.Index(fields=["is_active", "is_popular"])]

    def save(self, *a, **kw):
        if not self.slug:
            base = slugify(self.name)
            slug, n = base, 2
            while Service.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug, n = f"{base}-{n}", n + 1
            self.slug = slug
        super().save(*a, **kw)

    @property
    def duration_label(self):
        h, m = divmod(self.duration_minutes, 60)
        if h and m:
            return f"{h} h {m} min"
        return f"{h} h" if h else f"{m} min"

    def __str__(self):
        return self.name
