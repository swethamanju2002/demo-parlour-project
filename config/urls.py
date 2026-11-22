from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("django-admin/", admin.site.urls),  # raw Django admin kept for superuser maintenance only
    path("", include("core.urls")),
    path("services/", include("services.urls")),
    path("gallery/", include("gallery.urls")),
    path("offers/", include("offers.urls")),
    path("accounts/", include("accounts.urls")),
    path("client/", include("bookings.client_urls")),
    path("admin-panel/", include("bookings.admin_urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
