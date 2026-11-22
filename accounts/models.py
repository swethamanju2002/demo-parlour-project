from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models


class User(AbstractUser):
    """Single auth model; `role` drives access to /client/ vs /admin-panel/."""

    class Role(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        STAFF = "staff", "Staff"
        ADMIN = "admin", "Administrator"

    email = models.EmailField("email address", unique=True)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.CUSTOMER, db_index=True)
    phone = models.CharField(
        max_length=15, blank=True,
        validators=[RegexValidator(r"^[0-9+\- ]{8,15}$", "Enter a valid phone number.")],
    )
    address = models.TextField(blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True)

    REQUIRED_FIELDS = ["email"]

    @property
    def is_salon_admin(self):
        return self.is_active and (self.role == self.Role.ADMIN or self.is_superuser)

    @property
    def is_salon_team(self):
        return self.is_active and (self.role in (self.Role.ADMIN, self.Role.STAFF) or self.is_superuser)

    @property
    def display_name(self):
        return self.get_full_name() or self.username

    def __str__(self):
        return self.display_name
