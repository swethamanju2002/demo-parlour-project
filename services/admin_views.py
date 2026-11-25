
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.permissions import salon_admin_required

from .admin_forms import ServiceAdminForm, ServiceCategoryAdminForm
from .models import Service, ServiceCategory


@salon_admin_required
def service_list(request):
    services = Service.objects.select_related("category").order_by(
        "order", "name"
    )

    search = request.GET.get("q", "").strip()
    category_id = request.GET.get("category", "").strip()
    status = request.GET.get("status", "").strip()

    if search:
        services = services.filter(
            Q(name__icontains=search)
            | Q(slug__icontains=search)
            | Q(description__icontains=search)
            | Q(category__name__icontains=search)
        )

    if category_id.isdigit():
        services = services.filter(category_id=int(category_id))

    if status == "active":
        services = services.filter(is_active=True)
    elif status == "inactive":
        services = services.filter(is_active=False)

    paginator = Paginator(services, 12)
    page = paginator.get_page(request.GET.get("page"))

    categories = ServiceCategory.objects.order_by("order", "name")

    return render(request, "admin_panel/services.html", {
        "page": page,
        "search": search,
        "selected_category": category_id,
        "selected_status": status,
        "categories": categories,
        "total_count": paginator.count,
    })


@salon_admin_required
def service_create(request):
    form = ServiceAdminForm(
        request.POST or None,
        request.FILES or None,
    )

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Service created successfully.")
        return redirect("admin_panel:services")

    return render(request, "admin_panel/service_form.html", {
        "form": form,
        "page_title": "Create Service",
        "form_description": "Add a new treatment or salon service.",
        "submit_label": "Create service",
    })


@salon_admin_required
def service_edit(request, service_id):
    service = get_object_or_404(Service, pk=service_id)

    form = ServiceAdminForm(
        request.POST or None,
        request.FILES or None,
        instance=service,
    )

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Service updated successfully.")
        return redirect("admin_panel:services")

    return render(request, "admin_panel/service_form.html", {
        "form": form,
        "service": service,
        "page_title": "Edit Service",
        "form_description": "Update service information and availability.",
        "submit_label": "Save changes",
    })


@salon_admin_required
@require_POST
def service_toggle_active(request, service_id):
    service = get_object_or_404(Service, pk=service_id)

    service.is_active = not service.is_active
    service.save(update_fields=["is_active"])

    messages.success(
        request,
        f"{service.name} is now "
        f"{'active' if service.is_active else 'inactive'}.",
    )

    return redirect("admin_panel:services")


@salon_admin_required
def category_list(request):
    categories = ServiceCategory.objects.order_by("order", "name")

    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()

    if search:
        categories = categories.filter(
            Q(name__icontains=search)
            | Q(slug__icontains=search)
            | Q(description__icontains=search)
        )

    if status == "active":
        categories = categories.filter(is_active=True)
    elif status == "inactive":
        categories = categories.filter(is_active=False)

    paginator = Paginator(categories, 12)
    page = paginator.get_page(request.GET.get("page"))

    return render(request, "admin_panel/categories.html", {
        "page": page,
        "search": search,
        "selected_status": status,
        "total_count": paginator.count,
    })


@salon_admin_required
def category_create(request):
    form = ServiceCategoryAdminForm(
        request.POST or None,
        request.FILES or None,
    )

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Category created successfully.")
        return redirect("admin_panel:categories")

    return render(request, "admin_panel/category_form.html", {
        "form": form,
        "page_title": "Create Category",
        "form_description": "Create a new salon service category.",
        "submit_label": "Create category",
    })


@salon_admin_required
def category_edit(request, category_id):
    category = get_object_or_404(ServiceCategory, pk=category_id)

    form = ServiceCategoryAdminForm(
        request.POST or None,
        request.FILES or None,
        instance=category,
    )

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Category updated successfully.")
        return redirect("admin_panel:categories")

    return render(request, "admin_panel/category_form.html", {
        "form": form,
        "category": category,
        "page_title": "Edit Category",
        "form_description": "Update category details and visibility.",
        "submit_label": "Save changes",
    })


@salon_admin_required
@require_POST
def category_toggle_active(request, category_id):
    category = get_object_or_404(ServiceCategory, pk=category_id)

    category.is_active = not category.is_active
    category.save(update_fields=["is_active"])

    messages.success(
        request,
        f"{category.name} is now "
        f"{'active' if category.is_active else 'inactive'}.",
    )

    return redirect("admin_panel:categories")
