"""Generate clearly-fictional placeholder artwork in the brand palette (demo data only)."""
import io
import random

from django.core.files.base import ContentFile
from PIL import Image, ImageDraw, ImageFilter

PALETTES = [
    ("#E3ECF2", "#8FB2C9", "#1F2740", "#D2364E"),
    ("#F7F9FB", "#C7D8E4", "#46506B", "#D2364E"),
    ("#1F2740", "#46506B", "#8FB2C9", "#E3ECF2"),
    ("#EAD9DC", "#D9A6B0", "#1F2740", "#8FB2C9"),
    ("#DDE7E2", "#7C9A8E", "#1F2740", "#F7F9FB"),
]


def make_art(seed: str, w=900, h=1100, palette=None) -> ContentFile:
    rnd = random.Random(seed)
    bg, a, b, c = palette or PALETTES[rnd.randrange(len(PALETTES))]
    im = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(im, "RGBA")
    # arches, circles, soft ribbons: echo the signage language
    for _ in range(3):
        x0 = rnd.randint(-w // 6, w // 2); aw = rnd.randint(w // 3, int(w * .7))
        y0 = rnd.randint(h // 6, h // 2)
        d.rounded_rectangle((x0, y0, x0 + aw, h + 200), radius=aw // 2, fill=(*Image.new("RGB", (1, 1), a).getpixel((0, 0)), 170))
    for _ in range(2):
        r = rnd.randint(w // 8, w // 4); cx, cy = rnd.randint(0, w), rnd.randint(0, h // 2)
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(*Image.new("RGB", (1, 1), b).getpixel((0, 0)), 110))
    cx, cy, r = rnd.randint(w // 4, 3 * w // 4), rnd.randint(h // 5, h // 2), w // 14
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=c)
    im = im.filter(ImageFilter.GaussianBlur(1.2))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=84)
    return ContentFile(buf.getvalue())
