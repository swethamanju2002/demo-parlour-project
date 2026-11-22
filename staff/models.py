from django.db import models
from django.db.models import F, Q

WEEKDAYS = [(0, "Monday"), (1, "Tuesday"), (2, "Wednesday"), (3, "Thursday"), (4, "Friday"), (5, "Saturday"), (6, "Sunday")]


class StaffProfile(models.Model):
    """Public beautician profile, plus the services they are able to perform (used by the booking engine)."""
    name = models.CharField(max_length=100)
    title = models.CharField(max_length=100)
    bio = models.TextField(blank=True)
    photo = models.ImageField(upload_to="staff/", blank=True)
    years_experience = models.PositiveSmallIntegerField(default=0)
    is_featured = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)
    services = models.ManyToManyField(
        "services.Service", blank=True, related_name="staff_members",
        help_text="Services this beautician can perform. Customers are only offered beauticians who can do every selected service.",
    )

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class StaffSchedule(models.Model):
    """Weekly working hours: one block per weekday. A weekday without a row means the beautician is off."""
    staff = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name="schedules")
    weekday = models.PositiveSmallIntegerField(choices=WEEKDAYS)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        ordering = ["staff_id", "weekday"]
        constraints = [
            models.UniqueConstraint(fields=["staff", "weekday"], name="staffschedule_one_block_per_day"),
            models.CheckConstraint(condition=Q(end_time__gt=F("start_time")), name="staffschedule_end_after_start"),
        ]

    def __str__(self):
        return f"{self.staff} · {self.get_weekday_display()} {self.start_time:%H:%M}–{self.end_time:%H:%M}"


class StaffLeave(models.Model):
    """A period when the beautician cannot take appointments. Only approved leave blocks bookings."""
    staff = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name="leaves")
    start = models.DateTimeField()
    end = models.DateTimeField()
    reason = models.CharField(max_length=160, blank=True)
    is_approved = models.BooleanField(default=True)

    class Meta:
        ordering = ["-start"]
        constraints = [models.CheckConstraint(condition=Q(end__gt=F("start")), name="staffleave_end_after_start")]

    def __str__(self):
        return f"{self.staff} · {self.start:%d %b %Y %H:%M} → {self.end:%d %b %Y %H:%M}"
