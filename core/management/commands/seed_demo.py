from datetime import date, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import User
from core.models import FAQ, BusinessHour, SiteSettings, Testimonial
from core.placeholder_art import make_art
from enquiries.models import Enquiry
from gallery.models import GalleryCategory, GalleryItem
from offers.models import Offer
from services.models import Service, ServiceCategory
from staff.models import StaffProfile
from django.utils import timezone
from bookings.demo import seed_booking_demo

CATEGORIES = [
    ("Skin Care", "Clear, calm, glowing", "Facials and clinical skin treatments chosen for your skin, not a menu."),
    ("Hair Care", "Healthy from root to tip", "Cuts, colour and repair treatments with careful consultation."),
    ("PMU", "Permanent makeup, done softly", "Brows, lips and eyeliner with natural, healed-in results."),
    ("Bridal Makeup", "Your day, your face", "Trials, bridal looks and family styling for the whole celebration."),
    ("Academy", "Learn the craft", "Professional training in beauty, hair and makeup. Enrol by enquiry."),
]
# category, name, description, price, minutes, featured, popular, bookable
SERVICES = [
    ("Skin Care", "Signature Hydra Facial", "Deep cleanse, exfoliation and hydration for an instantly fresher complexion.", 2200, 60, True, True, True),
    ("Skin Care", "Brightening Glow Facial", "Vitamin-rich facial that evens tone and restores radiance.", 1800, 60, False, True, True),
    ("Skin Care", "Acne Clarity Treatment", "Targeted care to calm breakouts and prevent marks.", 2500, 75, False, False, True),
    ("Hair Care", "Haircut and Styling", "Consultation, cut and blow-dry shaped to your face and routine.", 700, 45, True, False, True),
    ("Hair Care", "Keratin Smoothing", "Frizz control and shine that lasts for months.", 6500, 150, True, True, True),
    ("Hair Care", "Hair Spa Repair", "Nourishing scalp and hair treatment for dry, tired hair.", 1500, 60, False, True, True),
    ("Hair Care", "Global Colour", "Single-tone colour with a protective finish.", 4200, 120, False, False, True),
    ("PMU", "Microblading Brows", "Fine hair-stroke brows designed around your natural shape.", 9000, 120, True, False, True),
    ("PMU", "Lip Blush", "Soft, even colour that keeps your lips looking naturally rosy.", 8000, 120, False, True, True),
    ("Bridal Makeup", "Bridal Makeup Trial", "A full run-through so your wedding look is decided before the day.", 3500, 90, False, False, True),
    ("Bridal Makeup", "Bridal Makeup (Wedding Day)", "Long-wear bridal makeup and hair styling with touch-up kit.", 18000, 180, True, True, True),
    ("Academy", "Professional Makeup Course", "Hands-on training in makeup artistry. Enquire for batches and fees.", 25000, 60, False, False, False),
]
STAFF = [
    ("Dhanya Q.", "Founder and Lead Aesthetician", "Skin specialist who leads treatments and trains the team.", 10),
    ("Meenakshi R.", "Senior Bridal Artist", "Bridal looks for traditional and modern ceremonies.", 8),
    ("Priya S.", "Hair Stylist", "Cuts, colour and smoothing treatments.", 6),
    ("Kavya M.", "PMU Artist", "Brows and lips with a soft, natural finish.", 5),
]
TESTIMONIALS = [
    ("Sample client A", "The consultation alone was worth it. Nobody had ever looked at my skin that carefully.", "Hydra Facial"),
    ("Sample client B", "My bridal trial calmed every worry. On the day, I looked like myself, only better.", "Bridal Makeup"),
    ("Sample client C", "Hair feels healthy again after the repair spa. Easy booking, no waiting around.", "Hair Spa Repair"),
]
FAQS = [
    ("How do I book?", "Create an account, choose your services, pick a date and time, and confirm. We confirm every booking."),
    ("Can I choose my beautician?", "Yes. Pick a preferred beautician or let us assign the best available one."),
    ("What is your cancellation policy?", "Cancel at least 4 hours before your appointment from your account."),
    ("Do you offer bridal packages?", "Yes. Book a trial first, then we tailor the wedding-day package."),
]


class Command(BaseCommand):
    help = "Load fictional DQ Aesthetic demo data. Safe to re-run."

    @transaction.atomic
    def handle(self, *a, **kw):
        s = SiteSettings.load()
        s.announcement = "Grand opening offer: 15% off your first visit this month."
        s.save()

        for i, (day, closed) in enumerate([(0, False), (1, False), (2, False), (3, False), (4, False), (5, False), (6, True)]):
            BusinessHour.objects.update_or_create(weekday=day, defaults=dict(
                opens=None if closed else time(10, 0), closes=None if closed else time(19, 30), is_closed=closed))

        cats = {}
        for i, (n, tag, desc) in enumerate(CATEGORIES):
            c, _ = ServiceCategory.objects.get_or_create(name=n, defaults=dict(tagline=tag, description=desc, order=i))
            if not c.image:
                c.image.save(f"cat-{c.slug}.jpg", make_art(f"cat-{n}", 900, 1100), save=True)
            cats[n] = c
        for i, (cat, n, desc, price, mins, feat, pop, book) in enumerate(SERVICES):
            sv, created = Service.objects.get_or_create(name=n, defaults=dict(
                category=cats[cat], description=desc, price=Decimal(price), duration_minutes=mins,
                is_featured=feat, is_popular=pop, is_bookable=book, order=i))
            if not sv.image:
                sv.image.save(f"svc-{sv.slug}.jpg", make_art(f"svc-{n}", 900, 1100), save=True)

        gcats = {}
        for i, n in enumerate(["Hair", "Skin", "Bridal", "PMU"]):
            gcats[n], _ = GalleryCategory.objects.get_or_create(slug=n.lower(), defaults=dict(name=n, order=i))
        if not GalleryItem.objects.exists():
            plan = [("Soft waves", "Hair", False), ("Glass skin glow", "Skin", True), ("Classic bridal red lip", "Bridal", False),
                    ("Brow definition", "PMU", True), ("Keratin shine", "Hair", True), ("Dewy bridal base", "Bridal", True),
                    ("Hydra facial result", "Skin", False), ("Lip blush", "PMU", False), ("Layered cut", "Hair", False)]
            for i, (t, cat, ba) in enumerate(plan):
                item = GalleryItem(title=t, category=gcats[cat], caption="Demo artwork", is_featured=i < 6, order=i)
                item.image.save(f"gal-{i}.jpg", make_art(f"gal-{t}", 900, 1100 if i % 3 else 1300), save=False)
                if ba:
                    item.before_image.save(f"gal-{i}-before.jpg", make_art(f"before-{t}", 900, 1100,
                                           palette=("#DDDDDD", "#BFC4C9", "#7A7F87", "#9AA0A8")), save=False)
                item.save()

        today = timezone.localdate()
        offers = [
            ("Grand Opening: 15% off", "Celebrate with us. 15% off any first-visit service.", "percent", 15, False, "WELCOME15",
             today - timedelta(days=6), today + timedelta(days=24), "New customers only. One use per customer. Not combinable with other offers."),
            ("Bridal Trial Special", "₹500 off a bridal trial when you book the wedding day.", "flat", 500, True, "BRIDE500",
             today - timedelta(days=2), today + timedelta(days=60), "Valid when the wedding-day booking is confirmed."),
            ("Glow Facial Week", "20% off brightening and hydra facials.", "percent", 20, False, "GLOW20",
             today - timedelta(days=40), today - timedelta(days=10), "Expired sample, hidden from visitors."),
        ]
        for t, summ, dt, dv, pkg, code, vf, vt, terms in offers:
            Offer.objects.get_or_create(title=t, defaults=dict(summary=summ, discount_type=dt, discount_value=Decimal(dv),
                                        is_package=pkg, coupon_code=code, valid_from=vf, valid_to=vt, terms=terms))
        for i, (n, title, bio, yrs) in enumerate(STAFF):
            p, _ = StaffProfile.objects.get_or_create(name=n, defaults=dict(title=title, bio=bio, years_experience=yrs, order=i))
            if not p.photo:
                p.photo.save(f"staff-{i}.jpg", make_art(f"staff-{n}", 800, 1000), save=True)
        for n, q, sv in TESTIMONIALS:
            Testimonial.objects.get_or_create(name=n, defaults=dict(quote=q, service_name=sv))
        for i, (q, an) in enumerate(FAQS):
            FAQ.objects.get_or_create(question=q, defaults=dict(answer=an, order=i))
        if not Enquiry.objects.exists():
            Enquiry.objects.create(name="Sample enquirer", phone="9876500000", interested_in="Academy",
                                   message="Demo enquiry: what are the batch timings for the makeup course?")

        for username, email, role, pw, first in [
            ("admin_demo", "admin@dq-demo.test", "admin", "DQAdmin#2026", "Demo Admin"),
            ("demo_customer", "customer@dq-demo.test", "customer", "DQCustomer#2026", "Demo Customer"),
        ]:
            u, created = User.objects.get_or_create(username=username, defaults=dict(email=email, role=role, first_name=first))
            if created:
                u.set_password(pw)
                u.save()
                
                seed_booking_demo(self.stdout.write)
        self.stdout.write(self.style.SUCCESS("Demo data ready. admin_demo / DQAdmin#2026 · demo_customer / DQCustomer#2026"))
