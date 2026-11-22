from django.db import models


class GalleryCategory(models.Model):
    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(unique=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name_plural = "gallery categories"

    def __str__(self):
        return self.name


class GalleryItem(models.Model):
    title = models.CharField(max_length=120)
    category = models.ForeignKey(GalleryCategory, on_delete=models.PROTECT, related_name="items")
    image = models.ImageField(upload_to="gallery/", help_text="The 'after' photo for before-and-after items.")
    before_image = models.ImageField(upload_to="gallery/before/", blank=True, help_text="Add to show a before-and-after slider.")
    caption = models.CharField(max_length=200, blank=True)
    is_featured = models.BooleanField(default=False, help_text="Show on the homepage.")
    is_active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "-id"]

    @property
    def is_before_after(self):
        return bool(self.before_image)

    def __str__(self):
        return self.title
