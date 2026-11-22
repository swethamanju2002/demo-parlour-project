from django.db import models


class StaffProfile(models.Model):
    """Public beautician profile. Working hours, leave and capabilities are added in Phase 4."""
    name = models.CharField(max_length=100)
    title = models.CharField(max_length=100)
    bio = models.TextField(blank=True)
    photo = models.ImageField(upload_to="staff/", blank=True)
    years_experience = models.PositiveSmallIntegerField(default=0)
    is_featured = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name
