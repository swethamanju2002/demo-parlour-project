import re

from django import forms
from django.db.models import Q
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.utils.text import slugify

from .models import Product, ProductCategory, Purchase, PurchaseItem, StockMovement, Supplier
from .services import ALLOWED_REASONS


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


# ── Stock operation forms (shape only; business rules live in inventory.services) ──

def _reason_choices(movement_type):
    allowed = ALLOWED_REASONS[movement_type]
    return [(r.value, r.label) for r in StockMovement.Reason if r in allowed]


class _StockForm(forms.Form):
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Optional note"}))


class StockInForm(_StockForm):
    quantity = forms.IntegerField(min_value=1, label="Quantity received", widget=forms.NumberInput(attrs={"min": 1}))
    reason = forms.ChoiceField(choices=_reason_choices(StockMovement.Type.IN))
    unit_cost = forms.DecimalField(required=False, min_value=0, max_digits=10, decimal_places=2, label="Unit cost (₹)",
                                   widget=forms.NumberInput(attrs={"min": 0, "step": "0.01", "placeholder": "Optional"}))
    reference = forms.CharField(required=False, max_length=80, label="Reference", widget=forms.TextInput(attrs={"placeholder": "Bill or order no."}))


class StockOutForm(_StockForm):
    quantity = forms.IntegerField(min_value=1, label="Quantity removed", widget=forms.NumberInput(attrs={"min": 1}))
    reason = forms.ChoiceField(choices=_reason_choices(StockMovement.Type.OUT))
    reference = forms.CharField(required=False, max_length=80, label="Reference", widget=forms.TextInput(attrs={"placeholder": "Invoice or booking ID"}))


class StockAdjustForm(forms.Form):
    new_quantity = forms.IntegerField(min_value=0, label="Counted quantity", widget=forms.NumberInput(attrs={"min": 0}))
    reason = forms.ChoiceField(choices=_reason_choices(StockMovement.Type.ADJUSTMENT))
    notes = forms.CharField(required=True, label="Why is the count different?", widget=forms.Textarea(attrs={"rows": 2}))

    def clean_notes(self):
        notes = self.cleaned_data["notes"].strip()
        if not notes:
            raise forms.ValidationError("Explain the adjustment.")
        return notes


# ── Suppliers and purchases ──────────────────────────────────────────────────

class SupplierAdminForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ["name", "contact_person", "phone", "email", "address", "notes", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Glow Beauty Distributors"}),
            "contact_person": forms.TextInput(attrs={"placeholder": "Who do you deal with?"}),
            "phone": forms.TextInput(attrs={"placeholder": "Phone number"}),
            "address": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Payment terms, delivery days..."}),
        }

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if Supplier.objects.exclude(pk=self.instance.pk).filter(name__iexact=name).exists():
            raise forms.ValidationError("A supplier with this name already exists.")
        return name

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        if phone and not re.fullmatch(r"[0-9+\- ]{8,15}", phone):
            raise forms.ValidationError("Enter a valid phone number.")
        return phone


class PurchaseForm(forms.ModelForm):
    class Meta:
        model = Purchase
        fields = ["supplier", "invoice_number", "purchase_date", "notes"]
        widgets = {
            "purchase_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "invoice_number": forms.TextInput(attrs={"placeholder": "Optional"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        suppliers = Q(is_active=True)
        if self.instance and self.instance.pk:
            suppliers |= Q(pk=self.instance.supplier_id)
        self.fields["supplier"].queryset = Supplier.objects.filter(suppliers)


class PurchaseItemForm(forms.ModelForm):
    class Meta:
        model = PurchaseItem
        fields = ["product", "quantity", "unit_cost"]
        widgets = {
            "quantity": forms.NumberInput(attrs={"min": 1, "placeholder": "Qty"}),
            "unit_cost": forms.NumberInput(attrs={"min": 0, "step": "0.01", "placeholder": "Unit cost"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        products = Q(is_active=True)
        if self.instance and self.instance.pk:
            products |= Q(pk=self.instance.product_id)
        self.fields["product"].queryset = Product.objects.filter(products).select_related("category")
        self.fields["product"].empty_label = "Choose a product"

    def clean_quantity(self):
        quantity = self.cleaned_data["quantity"]
        if quantity < 1:
            raise forms.ValidationError("Quantity must be at least 1.")
        return quantity


class BasePurchaseItemFormSet(BaseInlineFormSet):
    def clean(self):
        if any(self.errors):
            return
        seen, count = set(), 0
        for form in self.forms:
            if not hasattr(form, "cleaned_data") or form.cleaned_data.get("DELETE"):
                continue
            product = form.cleaned_data.get("product")
            if product is None:
                continue
            if product.pk in seen:
                raise forms.ValidationError(f"“{product.name}” is listed more than once. Combine it into one line.")
            seen.add(product.pk)
            count += 1
        if count == 0:
            raise forms.ValidationError("Add at least one product to the purchase.")
        super().clean()


PurchaseItemFormSet = inlineformset_factory(
    Purchase, PurchaseItem, form=PurchaseItemForm, formset=BasePurchaseItemFormSet,
    extra=1, min_num=1, validate_min=True, can_delete=True,
)
