from django.core.validators import RegexValidator
from django.db import models


class Enquiry(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        IN_PROGRESS = "in_progress", "In progress"
        RESOLVED = "resolved", "Resolved"

    name = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=15, validators=[RegexValidator(r"^[0-9+\- ]{8,15}$", "Enter a valid phone number.")])
    interested_in = models.CharField(max_length=120, blank=True)
    message = models.TextField(max_length=2000)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NEW, db_index=True)
    admin_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "enquiries"

    def __str__(self):
        return f"{self.name} · {self.created_at:%d %b %Y}"
