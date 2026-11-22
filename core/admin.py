from django.contrib import admin

from .models import FAQ, BusinessHour, Holiday, SiteSettings, Testimonial

for m in (SiteSettings, BusinessHour, Holiday, Testimonial, FAQ):
    admin.site.register(m)
