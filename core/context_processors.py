from django.conf import settings
from django.db.utils import OperationalError, ProgrammingError


class _Brand(dict):
    """Dict that also allows template dot-access; falls back to settings defaults before migrations."""


def brand(request):
    data = dict(settings.BRAND_DEFAULTS)
    try:
        from .models import SiteSettings
        s = SiteSettings.load()
        data.update(
            name=s.name, tagline=s.tagline, phone=s.phone, whatsapp=s.whatsapp, address=s.address, city=s.city,
            demo_mode=s.demo_mode, email=s.email, map_embed_url=s.map_embed_url, announcement=s.announcement,
            instagram_url=s.instagram_url, facebook_url=s.facebook_url,
        )
    except (OperationalError, ProgrammingError):
        pass
    return {"BRAND": data}
