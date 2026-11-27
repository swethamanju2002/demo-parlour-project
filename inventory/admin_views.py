import datetime as dt

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.permissions import salon_admin_required

from . import purchasing, services
from .admin_forms import (ProductAdminForm, ProductCategoryAdminForm, PurchaseForm, PurchaseItemFormSet,
                          StockAdjustForm, StockInForm, StockOutForm, SupplierAdminForm)
from .models import Product, ProductCategory, Purchase, StockMovement, Supplier


# ── Product categories ───────────────────────────────────────────────────────

@salon_admin_required
def category_list(request):
    categories = ProductCategory.objects.annotate(product_count=Count("products")).order_by("order", "name")
    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    if search:
        categories = categories.filter(Q(name__icontains=search) | Q(description__icontains=search))
    if status == "active":
        categories = categories.filter(is_active=True)
    elif status == "inactive":
        categories = categories.filter(is_active=False)
    paginator = Paginator(categories, 12)
    return render(request, "admin_panel/inventory_categories.html", {
        "page": paginator.get_page(request.GET.get("page")), "search": search,
        "selected_status": status, "total_count": paginator.count,
    })


def _category_form(request, instance, title, description, label):
    form = ProductCategoryAdminForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        messages.success(request, f"Category “{obj.name}” saved.")
        return redirect("admin_panel:inventory_categories")
    return render(request, "admin_panel/inventory_category_form.html", {
        "form": form, "category": instance, "page_title": title, "form_description": description, "submit_label": label})


@salon_admin_required
def category_create(request):
    return _category_form(request, None, "Create Product Category", "Group your retail and consumable products.", "Create category")


@salon_admin_required
def category_edit(request, category_id):
    obj = get_object_or_404(ProductCategory, pk=category_id)
    return _category_form(request, obj, "Edit Product Category", "Update the category details and visibility.", "Save changes")


@salon_admin_required
@require_POST
def category_toggle_active(request, category_id):
    obj = get_object_or_404(ProductCategory, pk=category_id)
    obj.is_active = not obj.is_active
    obj.save(update_fields=["is_active"])
    messages.success(request, f"{obj.name} is now {'active' if obj.is_active else 'inactive'}.")
    return redirect("admin_panel:inventory_categories")


# ── Products ─────────────────────────────────────────────────────────────────

@salon_admin_required
def product_list(request):
    products = Product.objects.select_related("category").order_by("category__order", "name")
    search = request.GET.get("q", "").strip()
    category_id = request.GET.get("category", "").strip()
    status = request.GET.get("status", "").strip()
    stock = request.GET.get("stock", "").strip()
    if search:
        products = products.filter(Q(name__icontains=search) | Q(sku__icontains=search) | Q(description__icontains=search))
    if category_id.isdigit():
        products = products.filter(category_id=int(category_id))
    if status == "active":
        products = products.filter(is_active=True)
    elif status == "inactive":
        products = products.filter(is_active=False)
    if stock == "low":
        products = products.filter(is_active=True, quantity_on_hand__lte=F("reorder_level"))
    elif stock == "out":
        products = products.filter(quantity_on_hand=0)
    paginator = Paginator(products, 12)
    return render(request, "admin_panel/inventory_products.html", {
        "page": paginator.get_page(request.GET.get("page")), "search": search,
        "selected_category": category_id, "selected_status": status, "selected_stock": stock,
        "categories": ProductCategory.objects.all(), "total_count": paginator.count,
        "low_stock_count": Product.objects.low_stock().count(),
    })


def _product_form(request, instance, title, description, label):
    form = ProductAdminForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        messages.success(request, f"Product “{obj.name}” saved.")
        return redirect("admin_panel:inventory_products")
    return render(request, "admin_panel/inventory_product_form.html", {
        "form": form, "product": instance, "page_title": title, "form_description": description, "submit_label": label})


@salon_admin_required
def product_create(request):
    return _product_form(request, None, "Add Product", "Register a product. Opening stock is added separately so it is recorded in the stock history.", "Create product")


@salon_admin_required
def product_edit(request, product_id):
    obj = get_object_or_404(Product, pk=product_id)
    return _product_form(request, obj, "Edit Product", "Update product details and pricing. Stock levels change only through stock movements.", "Save changes")


@salon_admin_required
@require_POST
def product_toggle_active(request, product_id):
    obj = get_object_or_404(Product, pk=product_id)
    obj.is_active = not obj.is_active
    obj.save(update_fields=["is_active", "updated_at"])
    messages.success(request, f"{obj.name} is now {'active' if obj.is_active else 'inactive'}.")
    return redirect("admin_panel:inventory_products")


# ── Stock operations and history ─────────────────────────────────────────────

def _detail(request, product, in_form=None, out_form=None, adjust_form=None):
    movements = product.movements.select_related("created_by")
    paginator = Paginator(movements, 15)
    return render(request, "admin_panel/inventory_product_detail.html", {
        "product": product,
        "page": paginator.get_page(request.GET.get("page")),
        "in_form": in_form or StockInForm(prefix="in"),
        "out_form": out_form or StockOutForm(prefix="out"),
        "adjust_form": adjust_form or StockAdjustForm(prefix="adj"),
    })


@salon_admin_required
def product_detail(request, product_id):
    return _detail(request, get_object_or_404(Product.objects.select_related("category"), pk=product_id))


def _stock_action(request, product_id, form_class, prefix, form_key, run, success):
    product = get_object_or_404(Product.objects.select_related("category"), pk=product_id)
    form = form_class(request.POST, prefix=prefix)
    if form.is_valid():
        try:
            movement = run(product, form.cleaned_data)
        except ValidationError as exc:
            for message in exc.messages:
                form.add_error(None, message)
        else:
            messages.success(request, success(movement))
            return redirect("admin_panel:inventory_product_detail", product_id=product.pk)
    return _detail(request, product, **{form_key: form})


@salon_admin_required
@require_POST
def stock_in(request, product_id):
    return _stock_action(
        request, product_id, StockInForm, "in", "in_form",
        lambda p, d: services.stock_in(p.pk, d["quantity"], reason=d["reason"], unit_cost=d["unit_cost"],
                                       reference=d["reference"], notes=d["notes"], user=request.user),
        lambda m: f"Added {m.change} to {m.product.name}. Stock is now {m.quantity_after}.")


@salon_admin_required
@require_POST
def stock_out(request, product_id):
    return _stock_action(
        request, product_id, StockOutForm, "out", "out_form",
        lambda p, d: services.stock_out(p.pk, d["quantity"], reason=d["reason"], reference=d["reference"],
                                        notes=d["notes"], user=request.user),
        lambda m: f"Removed {-m.change} from {m.product.name}. Stock is now {m.quantity_after}.")


@salon_admin_required
@require_POST
def stock_adjust(request, product_id):
    return _stock_action(
        request, product_id, StockAdjustForm, "adj", "adjust_form",
        lambda p, d: services.adjust_stock(p.pk, d["new_quantity"], reason=d["reason"], notes=d["notes"], user=request.user),
        lambda m: f"Stock for {m.product.name} corrected to {m.quantity_after} ({m.change:+d}).")


def _date(raw):
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        return None


@salon_admin_required
def movement_list(request):
    movements = StockMovement.objects.select_related("product", "created_by")
    search = request.GET.get("q", "").strip()
    mtype = request.GET.get("type", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    if search:
        movements = movements.filter(Q(product__name__icontains=search) | Q(product__sku__icontains=search)
                                     | Q(reference__icontains=search) | Q(notes__icontains=search))
    if mtype in StockMovement.Type.values:
        movements = movements.filter(movement_type=mtype)
    if date_from and (d := _date(date_from)):
        movements = movements.filter(created_at__date__gte=d)
    if date_to and (d := _date(date_to)):
        movements = movements.filter(created_at__date__lte=d)
    paginator = Paginator(movements, 20)
    return render(request, "admin_panel/inventory_movements.html", {
        "page": paginator.get_page(request.GET.get("page")), "search": search, "selected_type": mtype,
        "date_from": date_from, "date_to": date_to, "type_choices": StockMovement.Type.choices,
        "total_count": paginator.count,
    })


# ── Suppliers ────────────────────────────────────────────────────────────────

@salon_admin_required
def supplier_list(request):
    suppliers = Supplier.objects.annotate(purchase_count=Count("purchases")).order_by("name")
    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    if search:
        suppliers = suppliers.filter(Q(name__icontains=search) | Q(contact_person__icontains=search)
                                     | Q(phone__icontains=search) | Q(email__icontains=search))
    if status == "active":
        suppliers = suppliers.filter(is_active=True)
    elif status == "inactive":
        suppliers = suppliers.filter(is_active=False)
    paginator = Paginator(suppliers, 12)
    return render(request, "admin_panel/inventory_suppliers.html", {
        "page": paginator.get_page(request.GET.get("page")), "search": search,
        "selected_status": status, "total_count": paginator.count,
    })


def _supplier_form(request, instance, title, description, label):
    form = SupplierAdminForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        messages.success(request, f"Supplier “{obj.name}” saved.")
        return redirect("admin_panel:inventory_suppliers")
    return render(request, "admin_panel/inventory_supplier_form.html", {
        "form": form, "supplier": instance, "page_title": title, "form_description": description, "submit_label": label})


@salon_admin_required
def supplier_create(request):
    return _supplier_form(request, None, "Add Supplier", "Register a supplier you buy stock from.", "Create supplier")


@salon_admin_required
def supplier_edit(request, supplier_id):
    obj = get_object_or_404(Supplier, pk=supplier_id)
    return _supplier_form(request, obj, "Edit Supplier", "Update contact details and status.", "Save changes")


@salon_admin_required
@require_POST
def supplier_toggle_active(request, supplier_id):
    obj = get_object_or_404(Supplier, pk=supplier_id)
    obj.is_active = not obj.is_active
    obj.save(update_fields=["is_active"])
    messages.success(request, f"{obj.name} is now {'active' if obj.is_active else 'inactive'}.")
    return redirect("admin_panel:inventory_suppliers")


# ── Purchases ────────────────────────────────────────────────────────────────

@salon_admin_required
def purchase_list(request):
    purchases = Purchase.objects.select_related("supplier")
    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    supplier_id = request.GET.get("supplier", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    if search:
        purchases = purchases.filter(Q(purchase_number__icontains=search) | Q(invoice_number__icontains=search)
                                     | Q(supplier__name__icontains=search))
    if status in Purchase.Status.values:
        purchases = purchases.filter(status=status)
    if supplier_id.isdigit():
        purchases = purchases.filter(supplier_id=int(supplier_id))
    if date_from and (d := _date(date_from)):
        purchases = purchases.filter(purchase_date__gte=d)
    if date_to and (d := _date(date_to)):
        purchases = purchases.filter(purchase_date__lte=d)
    paginator = Paginator(purchases, 12)
    return render(request, "admin_panel/inventory_purchases.html", {
        "page": paginator.get_page(request.GET.get("page")), "search": search, "selected_status": status,
        "selected_supplier": supplier_id, "date_from": date_from, "date_to": date_to,
        "status_choices": Purchase.Status.choices, "suppliers": Supplier.objects.order_by("name"),
        "total_count": paginator.count,
        "awaiting_count": Purchase.objects.filter(status__in=[Purchase.Status.DRAFT, Purchase.Status.ORDERED]).count(),
    })


@salon_admin_required
def purchase_create(request):
    purchase = Purchase()
    form = PurchaseForm(request.POST or None, instance=purchase)
    formset = PurchaseItemFormSet(request.POST or None, instance=purchase, prefix="items")
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            obj = form.save(commit=False)
            obj.created_by = request.user
            obj.purchase_number = purchasing.generate_purchase_number()
            obj.save()
            formset.instance = obj
            formset.save()
            purchasing.recalculate_total(obj)
        messages.success(request, f"Purchase {obj.purchase_number} saved as a draft.")
        return redirect("admin_panel:inventory_purchase_detail", purchase_id=obj.pk)
    return render(request, "admin_panel/inventory_purchase_form.html", {
        "form": form, "formset": formset, "purchase": None, "page_title": "New Purchase",
        "form_description": "Record stock bought from a supplier. Stock is added only when you receive it.",
        "submit_label": "Save purchase"})


@salon_admin_required
def purchase_edit(request, purchase_id):
    purchase = get_object_or_404(Purchase.objects.select_related("supplier"), pk=purchase_id)
    if not purchase.is_editable:
        messages.error(request, f"A {purchase.get_status_display().lower()} purchase can no longer be edited.")
        return redirect("admin_panel:inventory_purchase_detail", purchase_id=purchase.pk)
    form = PurchaseForm(request.POST or None, instance=purchase)
    formset = PurchaseItemFormSet(request.POST or None, instance=purchase, prefix="items")
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        try:
            with transaction.atomic():
                if not Purchase.objects.select_for_update().get(pk=purchase.pk).is_editable:
                    raise ValidationError("This purchase changed status while you were editing it.")
                obj = form.save(commit=False)
                obj.save(update_fields=["supplier", "invoice_number", "purchase_date", "notes", "updated_at"])
                formset.save()
                purchasing.recalculate_total(obj)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return redirect("admin_panel:inventory_purchase_detail", purchase_id=purchase.pk)
        except IntegrityError:   # e.g. a stale form re-adding a product that already has a line
            messages.error(request, "The purchase lines could not be saved because they clash with existing lines. Please reopen the purchase and try again.")
            return redirect("admin_panel:inventory_purchase_detail", purchase_id=purchase.pk)
        messages.success(request, f"Purchase {purchase.purchase_number} updated.")
        return redirect("admin_panel:inventory_purchase_detail", purchase_id=purchase.pk)
    return render(request, "admin_panel/inventory_purchase_form.html", {
        "form": form, "formset": formset, "purchase": purchase, "page_title": f"Edit {purchase.purchase_number}",
        "form_description": "Update the supplier details and the products on this purchase.",
        "submit_label": "Save changes"})


@salon_admin_required
def purchase_detail(request, purchase_id):
    purchase = get_object_or_404(Purchase.objects.select_related("supplier", "created_by", "received_by"), pk=purchase_id)
    return render(request, "admin_panel/inventory_purchase_detail.html", {
        "purchase": purchase, "items": purchase.items.select_related("product"),
        "movements": purchase.stock_movements.select_related("product", "created_by"),
    })


def _purchase_action(request, purchase_id, run, success):
    try:
        purchase = run()
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, success(purchase))
    return redirect("admin_panel:inventory_purchase_detail", purchase_id=purchase_id)


@salon_admin_required
@require_POST
def purchase_order(request, purchase_id):
    return _purchase_action(request, purchase_id, lambda: purchasing.mark_ordered(purchase_id),
                            lambda p: f"{p.purchase_number} marked as ordered.")


@salon_admin_required
@require_POST
def purchase_receive(request, purchase_id):
    return _purchase_action(request, purchase_id, lambda: purchasing.receive_purchase(purchase_id, user=request.user),
                            lambda p: f"{p.purchase_number} received. Stock has been updated.")


@salon_admin_required
@require_POST
def purchase_cancel(request, purchase_id):
    return _purchase_action(request, purchase_id, lambda: purchasing.cancel_purchase(purchase_id),
                            lambda p: f"{p.purchase_number} cancelled.")
