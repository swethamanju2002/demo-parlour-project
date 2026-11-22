from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class SiteSettings(models.Model):
    """Single editable record: everything that changes when the real client details are final."""
    name = models.CharField(max_length=80, default="DQ Aesthetic")
    tagline = models.CharField(max_length=160, default="Skin, hair and bridal artistry for women.")
    announcement = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=20, default="93606 55255")
    whatsapp = models.CharField(max_length=15, default="919360655255", help_text="Digits only, with country code.")
    email = models.EmailField(blank=True)
    address = models.TextField(default="Dillo Textile backside, Therkupatty Road, Akshaya Traders Upstair, Melur")
    city = models.CharField(max_length=60, default="Melur")
    map_embed_url = models.URLField(blank=True, help_text="Google Maps 'Embed a map' URL. Leave blank to hide the map.")
    instagram_url = models.URLField(blank=True)
    facebook_url = models.URLField(blank=True)
    demo_mode = models.BooleanField(default=True, help_text="Shows the 'demonstration data' notice in the footer.")

    class Meta:
        verbose_name_plural = "site settings"

    def save(self, *a, **kw):
        self.pk = 1  # singleton
        super().save(*a, **kw)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Site settings"


class BusinessHour(models.Model):
    DAYS = [(0, "Monday"), (1, "Tuesday"), (2, "Wednesday"), (3, "Thursday"), (4, "Friday"), (5, "Saturday"), (6, "Sunday")]
    weekday = models.PositiveSmallIntegerField(choices=DAYS, unique=True)
    opens = models.TimeField(null=True, blank=True)
    closes = models.TimeField(null=True, blank=True)
    is_closed = models.BooleanField(default=False)

    class Meta:
        ordering = ["weekday"]

    @property
    def day_name(self):
        return self.get_weekday_display()

    def __str__(self):
        return self.day_name


class Testimonial(models.Model):
    name = models.CharField(max_length=80)
    quote = models.TextField(max_length=400)
    rating = models.PositiveSmallIntegerField(default=5, validators=[MinValueValidator(1), MaxValueValidator(5)])
    service_name = models.CharField(max_length=80, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class FAQ(models.Model):
    question = models.CharField(max_length=200)
    answer = models.TextField()
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order"]
        verbose_name = "FAQ"

    def __str__(self):
        return self.question


class Holiday(models.Model):
    """A full day on which the salon takes no appointments, regardless of the weekly opening hours."""
    date = models.DateField(unique=True)
    reason = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"{self.date:%d %b %Y}" + (f" · {self.reason}" if self.reason else "")