from django import forms
from django.db.models import Q
from django.utils.text import slugify

from .models import Product, ProductCategory


class ProductCategoryAdminForm(forms.ModelForm):
    class Meta:
        model = ProductCategory
        fields = ["name", "description", "order", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Hair care products"}),
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "What belongs in this category..."}),
            "order": forms.NumberInput(attrs={"min": 0}),
        }

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        others = ProductCategory.objects.exclude(pk=self.instance.pk)
        if others.filter(name__iexact=name).exists():
            raise forms.ValidationError("A product category with this name already exists.")
        if not self.instance.pk:
            slug = slugify(name)
            if not slug:
                raise forms.ValidationError("Use letters or numbers in the name.")
            if others.filter(slug=slug).exists():
                raise forms.ValidationError("A category with a very similar name already exists.")
        return name


class ProductAdminForm(forms.ModelForm):
    """Stock quantity is deliberately absent: it changes only through inventory.services."""

    class Meta:
        model = Product
        fields = ["category", "name", "sku", "description", "unit", "cost_price", "selling_price",
                  "reorder_level", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Keratin repair serum 100 ml"}),
            "sku": forms.TextInput(attrs={"placeholder": "e.g. HAIR-KRS-100"}),
            "description": forms.Textarea(attrs={"rows": 4}),
            "unit": forms.TextInput(attrs={"placeholder": "pcs, bottle, ml..."}),
            "cost_price": forms.NumberInput(attrs={"min": "0", "step": "0.01", "placeholder": "0.00"}),
            "selling_price": forms.NumberInput(attrs={"min": "0", "step": "0.01", "placeholder": "0.00"}),
            "reorder_level": forms.NumberInput(attrs={"min": "0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cats = Q(is_active=True)
        if self.instance and self.instance.pk:
            cats |= Q(pk=self.instance.category_id)   # keep the current category selectable if deactivated
        self.fields["category"].queryset = ProductCategory.objects.filter(cats)

    def clean_sku(self):
        sku = self.cleaned_data["sku"].strip().upper()
        if " " in sku:
            raise forms.ValidationError("A SKU cannot contain spaces. Use hyphens instead.")
        if Product.objects.exclude(pk=self.instance.pk).filter(sku__iexact=sku).exists():
            raise forms.ValidationError("Another product already uses this SKU.")
        return sku

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())
