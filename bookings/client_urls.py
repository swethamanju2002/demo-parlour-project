from django.urls import path

from . import api, client_views as v

app_name = "client"

urlpatterns = [
    path("", v.dashboard, name="dashboard"),
    path("book/", v.book, name="book"),
    path("bookings/", v.bookings, name="bookings"),
    path("bookings/<str:public_id>/", v.booking_detail, name="booking_detail"),
    path("bookings/<str:public_id>/cancel/", v.booking_cancel, name="booking_cancel"),
    path("bookings/<str:public_id>/reschedule/", v.booking_reschedule, name="booking_reschedule"),
    path("offers/", v.offers, name="offers"),
    path("billing/", v.billing, name="billing"),
    # JSON endpoints for the booking wizard
    path("api/services/", api.services, name="api_services"),
    path("api/dates/", api.dates, name="api_dates"),
    path("api/slots/", api.slots, name="api_slots"),
    path("api/staff/", api.staff, name="api_staff"),
    path("api/summary/", api.summary, name="api_summary"),
    path("api/book/", api.book, name="api_book"),
]
