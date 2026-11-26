from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.permissions import salon_admin_required

from .admin_forms import ProductAdminForm, ProductCategoryAdminForm
from .models import Product, ProductCategory


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
