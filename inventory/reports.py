"""Inventory dashboard and reports. Everything here is read-only and computed from the database."""
import csv
import datetime as dt
from decimal import Decimal
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Max, Q, Sum
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from accounts.permissions import salon_admin_required

from .models import Product, ProductCategory, Purchase, StockMovement, Supplier

COST_VALUE = ExpressionWrapper(F("quantity_on_hand") * F("cost_price"), output_field=DecimalField(max_digits=16, decimal_places=2))
RETAIL_VALUE = ExpressionWrapper(F("quantity_on_hand") * F("selling_price"), output_field=DecimalField(max_digits=16, decimal_places=2))
PAGE_SIZE = 30


# ── helpers ──────────────────────────────────────────────────────────────────

def _money(value):
    return f"₹{Decimal(value or 0):,.2f}"


def _cell(text, url=None, raw=None, num=False):
    """One table cell: `text` is shown, `raw` goes to the CSV export."""
    return {"text": text, "url": url, "raw": text if raw is None else raw, "num": num}


def _date(raw):
    try:
        return dt.date.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


def _csv_safe(value):
    """Stop spreadsheet formula injection: text that starts with = + - @ is prefixed with a quote."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def _filter(request, name, label, kind, options=None):
    return {"name": name, "label": label, "kind": kind, "options": options or [], "value": request.GET.get(name, "").strip()}


def _report(request, *, slug, title, description, filters, columns, rows, summary):
    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{slug}-{timezone.localdate():%Y%m%d}.csv"'
        writer = csv.writer(response)
        writer.writerow(columns)
        for row in rows:
            writer.writerow([_csv_safe(c["raw"]) for c in row])
        return response
    params = {k: v for k, v in request.GET.items() if k not in ("page", "export") and v}
    page = Paginator(rows, PAGE_SIZE).get_page(request.GET.get("page"))
    return render(request, "admin_panel/inventory_report.html", {
        "title": title, "description": description, "filters": filters, "columns": columns, "page": page,
        "summary": summary, "qs": urlencode(params), "export_qs": urlencode({**params, "export": "csv"}),
        "total_rows": len(rows),
    })


# ── dashboard and index ──────────────────────────────────────────────────────

@salon_admin_required
def dashboard(request):
    products = Product.objects.active().aggregate(
        n=Count("id"), units=Sum("quantity_on_hand"), cost=Sum(COST_VALUE), retail=Sum(RETAIL_VALUE),
        out=Count("id", filter=Q(quantity_on_hand=0)),
        low=Count("id", filter=Q(quantity_on_hand__gt=0, quantity_on_hand__lte=F("reorder_level"))),
    )
    since = timezone.now() - dt.timedelta(days=30)
    open_statuses = [Purchase.Status.DRAFT, Purchase.Status.ORDERED]
    purchases = Purchase.objects.aggregate(
        received_total=Sum("total_amount", filter=Q(status=Purchase.Status.RECEIVED)),
        received_30=Sum("total_amount", filter=Q(status=Purchase.Status.RECEIVED, received_at__gte=since)),
        awaiting_n=Count("id", filter=Q(status__in=open_statuses)),
        awaiting_value=Sum("total_amount", filter=Q(status__in=open_statuses)),
    )
    stats = {
        "active_products": products["n"], "units": products["units"] or 0, "out_of_stock": products["out"], "low_stock": products["low"],
        "stock_value": products["cost"] or Decimal("0.00"), "retail_value": products["retail"] or Decimal("0.00"),
        "categories": ProductCategory.objects.filter(is_active=True).count(),
        "suppliers": Supplier.objects.filter(is_active=True).count(),
        "received_total": purchases["received_total"] or Decimal("0.00"), "received_30": purchases["received_30"] or Decimal("0.00"),
        "awaiting_count": purchases["awaiting_n"], "awaiting_value": purchases["awaiting_value"] or Decimal("0.00"),
    }
    return render(request, "admin_panel/inventory_dashboard.html", {
        "stats": stats,
        "alerts": Product.objects.low_stock().select_related("category").order_by("quantity_on_hand", "name")[:8],
        "recent_movements": StockMovement.objects.select_related("product", "created_by")[:8],
        "recent_purchases": Purchase.objects.select_related("supplier")[:5],
    })


@salon_admin_required
def reports_index(request):
    return render(request, "admin_panel/inventory_reports.html")


# ── reports ──────────────────────────────────────────────────────────────────

def _product_base(request):
    qs = Product.objects.select_related("category")
    q = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(sku__icontains=q))
    if category.isdigit():
        qs = qs.filter(category_id=int(category))
    return qs


def _category_options():
    return [(str(c.pk), c.name) for c in ProductCategory.objects.all()]


@salon_admin_required
def report_stock(request):
    qs = _product_base(request)
    status = request.GET.get("status", "").strip()
    if status == "inactive":
        qs = qs.filter(is_active=False)
    elif status != "all":
        qs = qs.filter(is_active=True)
    qs = qs.order_by("category__order", "name")
    totals = qs.aggregate(n=Count("id"), units=Sum("quantity_on_hand"), cost=Sum(COST_VALUE), retail=Sum(RETAIL_VALUE))
    rows = []
    for p in qs:
        state = "Out of stock" if not p.quantity_on_hand else "Low stock" if p.is_low_stock else "In stock"
        rows.append([
            _cell(p.name, reverse("admin_panel:inventory_product_detail", args=[p.pk])), _cell(p.sku), _cell(p.category.name),
            _cell(f"{p.quantity_on_hand} {p.unit}", raw=p.quantity_on_hand, num=True), _cell(_money(p.cost_price), raw=p.cost_price, num=True),
            _cell(_money(p.stock_value), raw=p.stock_value, num=True), _cell(_money(p.selling_price), raw=p.selling_price, num=True),
            _cell(_money(p.selling_price * p.quantity_on_hand), raw=p.selling_price * p.quantity_on_hand, num=True),
            _cell(state if p.is_active else f"{state} (inactive)"),
        ])
    return _report(
        request, slug="current-stock", title="Current stock", description="Stock on hand for every product, valued at cost and at selling price.",
        filters=[_filter(request, "q", "Search", "search"), _filter(request, "category", "Category", "select", _category_options()),
                 _filter(request, "status", "Products", "select", [("all", "All products"), ("inactive", "Inactive only")])],
        columns=["Product", "SKU", "Category", "In stock", "Cost", "Stock value (cost)", "Selling price", "Stock value (retail)", "Status"],
        rows=rows, summary=[("Products", totals["n"]), ("Units on hand", totals["units"] or 0),
                            ("Stock value at cost", _money(totals["cost"])), ("Stock value at selling price", _money(totals["retail"]))])


@salon_admin_required
def report_low_stock(request):
    qs = _product_base(request).filter(is_active=True, quantity_on_hand__gt=0, quantity_on_hand__lte=F("reorder_level")).order_by("quantity_on_hand", "name")
    rows, short = [], 0
    for p in qs:
        gap = p.reorder_level - p.quantity_on_hand
        short += gap
        rows.append([_cell(p.name, reverse("admin_panel:inventory_product_detail", args=[p.pk])), _cell(p.sku), _cell(p.category.name),
                     _cell(f"{p.quantity_on_hand} {p.unit}", raw=p.quantity_on_hand, num=True), _cell(p.reorder_level, num=True),
                     _cell(gap, num=True), _cell(_money(p.cost_price), raw=p.cost_price, num=True)])
    return _report(
        request, slug="low-stock", title="Low stock", description="Active products at or below their alert level but not yet out of stock.",
        filters=[_filter(request, "q", "Search", "search"), _filter(request, "category", "Category", "select", _category_options())],
        columns=["Product", "SKU", "Category", "In stock", "Alert level", "Below alert level by", "Cost"],
        rows=rows, summary=[("Products to reorder", len(rows)), ("Total units below alert level", short)])


@salon_admin_required
def report_out_of_stock(request):
    qs = _product_base(request).filter(is_active=True, quantity_on_hand=0).annotate(last_move=Max("movements__created_at")).order_by("name")
    rows = []
    for p in qs:
        when = timezone.localtime(p.last_move).strftime("%d %b %Y") if p.last_move else "No stock recorded"
        rows.append([_cell(p.name, reverse("admin_panel:inventory_product_detail", args=[p.pk])), _cell(p.sku), _cell(p.category.name),
                     _cell(p.reorder_level, num=True), _cell(when)])
    return _report(
        request, slug="out-of-stock", title="Out of stock", description="Active products with no stock on hand.",
        filters=[_filter(request, "q", "Search", "search"), _filter(request, "category", "Category", "select", _category_options())],
        columns=["Product", "SKU", "Category", "Alert level", "Last stock movement"], rows=rows, summary=[("Products out of stock", len(rows))])


@salon_admin_required
def report_movements(request):
    qs = StockMovement.objects.select_related("product", "created_by")
    q = request.GET.get("q", "").strip()
    mtype = request.GET.get("type", "").strip()
    reason = request.GET.get("reason", "").strip()
    date_from, date_to = _date(request.GET.get("date_from")), _date(request.GET.get("date_to"))
    if q:
        qs = qs.filter(Q(product__name__icontains=q) | Q(product__sku__icontains=q) | Q(reference__icontains=q))
    if mtype in StockMovement.Type.values:
        qs = qs.filter(movement_type=mtype)
    if reason in StockMovement.Reason.values:
        qs = qs.filter(reason=reason)
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    t = qs.aggregate(n=Count("id"), plus=Sum("change", filter=Q(change__gt=0)), minus=Sum("change", filter=Q(change__lt=0)))
    plus, minus = t["plus"] or 0, -(t["minus"] or 0)
    rows = []
    for m in qs:
        who = (m.created_by.first_name or m.created_by.username) if m.created_by else "—"
        rows.append([
            _cell(timezone.localtime(m.created_at).strftime("%d %b %Y %I:%M %p")),
            _cell(m.product.name, reverse("admin_panel:inventory_product_detail", args=[m.product_id])), _cell(m.product.sku),
            _cell(m.get_movement_type_display()), _cell(m.get_reason_display()), _cell(f"{m.change:+d}", raw=m.change, num=True),
            _cell(m.quantity_before, num=True), _cell(m.quantity_after, num=True),
            _cell(_money(m.unit_cost) if m.unit_cost is not None else "—", raw=m.unit_cost if m.unit_cost is not None else "", num=True),
            _cell(m.reference or "—", raw=m.reference), _cell(who),
        ])
    return _report(
        request, slug="stock-movements", title="Stock movements", description="Every recorded stock change, with totals for the filtered period.",
        filters=[_filter(request, "q", "Search", "search"), _filter(request, "type", "Type", "select", list(StockMovement.Type.choices)),
                 _filter(request, "reason", "Reason", "select", list(StockMovement.Reason.choices)),
                 _filter(request, "date_from", "From", "date"), _filter(request, "date_to", "To", "date")],
        columns=["When", "Product", "SKU", "Type", "Reason", "Change", "Before", "After", "Unit cost", "Reference", "By"],
        rows=rows, summary=[("Movements", t["n"]), ("Units added", plus), ("Units removed", minus), ("Net change", plus - minus)])


@salon_admin_required
def report_purchases(request):
    qs = Purchase.objects.select_related("supplier").annotate(line_count=Count("items"))
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    supplier = request.GET.get("supplier", "").strip()
    date_from, date_to = _date(request.GET.get("date_from")), _date(request.GET.get("date_to"))
    if q:
        qs = qs.filter(Q(purchase_number__icontains=q) | Q(invoice_number__icontains=q) | Q(supplier__name__icontains=q))
    if status in Purchase.Status.values:
        qs = qs.filter(status=status)
    if supplier.isdigit():
        qs = qs.filter(supplier_id=int(supplier))
    if date_from:
        qs = qs.filter(purchase_date__gte=date_from)
    if date_to:
        qs = qs.filter(purchase_date__lte=date_to)
    open_statuses = [Purchase.Status.DRAFT, Purchase.Status.ORDERED]
    t = qs.aggregate(n=Count("id", distinct=True), received=Sum("total_amount", filter=Q(status=Purchase.Status.RECEIVED)),
                     awaiting=Sum("total_amount", filter=Q(status__in=open_statuses)),
                     cancelled=Count("id", filter=Q(status=Purchase.Status.CANCELLED), distinct=True))
    rows = []
    for p in qs.order_by("-purchase_date", "-id"):
        rows.append([_cell(p.purchase_number, reverse("admin_panel:inventory_purchase_detail", args=[p.pk])), _cell(p.supplier.name),
                     _cell(p.purchase_date.strftime("%d %b %Y"), raw=p.purchase_date.isoformat()), _cell(p.invoice_number or "—", raw=p.invoice_number),
                     _cell(p.get_status_display()), _cell(p.line_count, num=True), _cell(_money(p.total_amount), raw=p.total_amount, num=True)])
    return _report(
        request, slug="purchases", title="Purchases", description="Purchases by date, supplier and status. Totals below follow your filters.",
        filters=[_filter(request, "q", "Search", "search"), _filter(request, "supplier", "Supplier", "select", [(str(s.pk), s.name) for s in Supplier.objects.order_by("name")]),
                 _filter(request, "status", "Status", "select", list(Purchase.Status.choices)),
                 _filter(request, "date_from", "From", "date"), _filter(request, "date_to", "To", "date")],
        columns=["Purchase", "Supplier", "Date", "Supplier invoice no.", "Status", "Lines", "Total"],
        rows=rows, summary=[("Purchases", t["n"]), ("Received value", _money(t["received"])), ("Awaiting receipt (value)", _money(t["awaiting"])), ("Cancelled", t["cancelled"])])


@salon_admin_required
def report_product_history(request):
    product_id = request.GET.get("product", "").strip()
    mtype = request.GET.get("type", "").strip()
    date_from, date_to = _date(request.GET.get("date_from")), _date(request.GET.get("date_to"))
    rows, summary = [], []
    product = Product.objects.filter(pk=int(product_id)).first() if product_id.isdigit() else None
    if product:
        qs = product.movements.select_related("created_by")
        if mtype in StockMovement.Type.values:
            qs = qs.filter(movement_type=mtype)
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        ordered = list(qs.order_by("created_at", "id"))
        plus = sum(m.change for m in ordered if m.change > 0)
        minus = -sum(m.change for m in ordered if m.change < 0)
        for m in ordered:
            who = (m.created_by.first_name or m.created_by.username) if m.created_by else "—"
            rows.append([_cell(timezone.localtime(m.created_at).strftime("%d %b %Y %I:%M %p")), _cell(m.get_movement_type_display()),
                         _cell(m.get_reason_display()), _cell(f"{m.change:+d}", raw=m.change, num=True), _cell(m.quantity_before, num=True),
                         _cell(m.quantity_after, num=True), _cell(m.reference or "—", raw=m.reference), _cell(m.notes or "—", raw=m.notes), _cell(who)])
        summary = [("Product", f"{product.name} ({product.sku})"), ("Opening balance", ordered[0].quantity_before if ordered else "—"),
                   ("Units added", plus), ("Units removed", minus), ("Closing balance", ordered[-1].quantity_after if ordered else "—"),
                   ("Current stock", f"{product.quantity_on_hand} {product.unit}")]
    return _report(
        request, slug=f"stock-history-{slugify(product.sku) if product else 'product'}", title="Product stock history",
        description="Choose a product to see its full stock history with opening and closing balances." if not product else f"Stock history for {product.name}.",
        filters=[_filter(request, "product", "Product", "select", [(str(p.pk), f"{p.name} ({p.sku})") for p in Product.objects.order_by("name")]),
                 _filter(request, "type", "Type", "select", list(StockMovement.Type.choices)),
                 _filter(request, "date_from", "From", "date"), _filter(request, "date_to", "To", "date")],
        columns=["When", "Type", "Reason", "Change", "Before", "After", "Reference", "Notes", "By"], rows=rows, summary=summary)
