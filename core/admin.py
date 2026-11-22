from django.contrib import admin

from .models import FAQ, BusinessHour, SiteSettings, Testimonial

for m in (SiteSettings, BusinessHour, Testimonial, FAQ):
    admin.site.register(m)
