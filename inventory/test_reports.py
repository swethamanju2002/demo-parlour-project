import csv
import datetime as dt
import io
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from inventory import purchasing, services as svc
from inventory.models import Product, ProductCategory, Purchase, PurchaseItem, StockMovement, Supplier
from inventory.test_admin import InventoryAdminCase

REPORTS = ("inventory_report_stock", "inventory_report_low_stock", "inventory_report_out_of_stock",
           "inventory_report_movements", "inventory_report_purchases", "inventory_report_product_history")


def url(name, *args):
    return reverse(f"admin_panel:{name}", args=args)


def csv_rows(response):
    return list(csv.reader(io.StringIO(response.content.decode())))


class ReportCase(InventoryAdminCase):
    """Active: Serum (0, out), Cream (3, reorder 5, low), Oil (20, healthy). Inactive: Old (4)."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.cat2 = ProductCategory.objects.create(name="Skin care")
        cls.cream = Product.objects.create(category=cls.cat2, name="Cream", sku="CRM-1", cost_price=Decimal("40"), selling_price=Decimal("90"), reorder_level=5)
        cls.oil = Product.objects.create(category=cls.cat, name="Oil", sku="OIL-1", cost_price=Decimal("20"), selling_price=Decimal("60"), reorder_level=5)
        cls.old = Product.objects.create(category=cls.cat, name="Old", sku="OLD-1", cost_price=Decimal("10"), selling_price=Decimal("15"))
        svc.stock_in(cls.cream.pk, 3, user=cls.admin)
        svc.stock_in(cls.oil.pk, 20, user=cls.admin)
        svc.stock_out(cls.oil.pk, 5, reason="sale", reference="INV-1", user=cls.admin)
        svc.stock_in(cls.old.pk, 4)
        Product.objects.filter(pk=cls.old.pk).update(is_active=False)
        cls.sup = Supplier.objects.create(name="Glow Distributors")

    def purchase(self, number, rows, status="draft"):
        p = Purchase.objects.create(purchase_number=number, supplier=self.sup, status="draft", purchase_date=dt.date(2026, 11, 10))
        for prod, qty, cost in rows:
            PurchaseItem.objects.create(purchase=p, product=prod, quantity=qty, unit_cost=Decimal(cost))
        purchasing.recalculate_total(p)
        if status == "received":
            purchasing.receive_purchase(p.pk, self.admin)
        elif status == "cancelled":
            purchasing.cancel_purchase(p.pk)
        return Purchase.objects.get(pk=p.pk)


class AccessTests(ReportCase):
    def test_everything_is_admin_only(self):
        names = ("inventory_dashboard", "inventory_reports") + REPORTS
        for n in names:
            self.client.logout()
            self.assertEqual(self.client.get(url(n)).status_code, 302, n)
            self.client.force_login(self.plain)
            self.assertEqual(self.client.get(url(n)).status_code, 403, n)
            self.assertEqual(self.client.get(url(n), {"export": "csv"}).status_code, 403, n)
        self.client.force_login(self.admin)
        for n in names:
            self.assertEqual(self.client.get(url(n)).status_code, 200, n)


class DashboardTests(ReportCase):
    def test_numbers_come_from_the_database(self):
        self.purchase("PUR-T-1", [(self.oil, 10, "20.00")], status="received")        # +10 oil, 200.00 received
        self.purchase("PUR-T-2", [(self.cream, 2, "40.00")])                          # draft, 80.00 awaiting
        self.purchase("PUR-T-3", [(self.cream, 1, "40.00")], status="cancelled")
        s = self.client.get(url("inventory_dashboard")).context["stats"]
        self.assertEqual((s["active_products"], s["categories"], s["suppliers"]), (3, 2, 1))
        self.assertEqual((s["low_stock"], s["out_of_stock"]), (1, 1))                  # inactive Old excluded; Serum is out, Cream low
        self.assertEqual(s["units"], 3 + 25)                                           # Cream 3 + Oil 25
        self.assertEqual(s["stock_value"], Decimal("3") * 40 + Decimal("25") * 20)
        self.assertEqual(s["retail_value"], Decimal("3") * 90 + Decimal("25") * 60)
        self.assertEqual((s["received_total"], s["received_30"]), (Decimal("200.00"), Decimal("200.00")))
        self.assertEqual((s["awaiting_count"], s["awaiting_value"]), (1, Decimal("80.00")))

    def test_alerts_and_recent_lists(self):
        r = self.client.get(url("inventory_dashboard"))
        self.assertEqual([p.name for p in r.context["alerts"]], ["Serum", "Cream"])    # lowest stock first
        self.assertEqual(len(r.context["recent_movements"]), 4)
        self.assertEqual(list(r.context["recent_purchases"]), [])
        self.assertContains(r, "No purchases yet")

    def test_dashboard_with_no_active_products_still_renders(self):
        Product.objects.update(is_active=False)
        s = self.client.get(url("inventory_dashboard")).context["stats"]
        self.assertEqual((s["active_products"], s["units"], s["stock_value"], s["low_stock"]), (0, 0, Decimal("0.00"), 0))


class StockReportTests(ReportCase):
    def names(self, name, **q):
        r = self.client.get(url(name), q)
        return [row[0]["text"] for row in r.context["page"]], r

    def test_current_stock_filters_and_totals(self):
        names, r = self.names("inventory_report_stock")
        self.assertEqual(sorted(names), ["Cream", "Oil", "Serum"])
        summary = dict(r.context["summary"])
        self.assertEqual((summary["Products"], summary["Units on hand"], summary["Stock value at cost"]), (3, 18, "₹420.00"))
        self.assertEqual(summary["Stock value at selling price"], "₹1,170.00")
        self.assertEqual(sorted(self.names("inventory_report_stock", status="all")[0]), ["Cream", "Oil", "Old", "Serum"])
        self.assertEqual(self.names("inventory_report_stock", status="inactive")[0], ["Old"])
        self.assertEqual(self.names("inventory_report_stock", category=self.cat2.pk)[0], ["Cream"])
        self.assertEqual(self.names("inventory_report_stock", q="oil-1")[0], ["Oil"])
        self.assertEqual(sorted(self.names("inventory_report_stock", status="bogus", category="x")[0]), ["Cream", "Oil", "Serum"])

    def test_low_and_out_reports_are_disjoint(self):
        low, r = self.names("inventory_report_low_stock")
        self.assertEqual(low, ["Cream"])
        self.assertEqual(dict(r.context["summary"])["Total units below alert level"], 2)   # reorder 5 - stock 3
        out, r = self.names("inventory_report_out_of_stock")
        self.assertEqual(out, ["Serum"])
        self.assertEqual(r.context["page"][0][4]["text"], "No stock recorded")
        svc.stock_out(self.cream.pk, 3, reason="sale")
        self.assertEqual(sorted(self.names("inventory_report_out_of_stock")[0]), ["Cream", "Serum"])
        self.assertEqual(self.names("inventory_report_low_stock")[0], [])

    def test_csv_export_and_formula_injection_guard(self):
        Product.objects.create(category=self.cat, name="=HYPERLINK(1)", sku="EVIL-1")
        r = self.client.get(url("inventory_report_stock"), {"export": "csv"})
        self.assertEqual(r["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("attachment; filename=\"current-stock-", r["Content-Disposition"])
        rows = csv_rows(r)
        self.assertEqual(rows[0][:3], ["Product", "SKU", "Category"])
        self.assertEqual(len(rows), 1 + 4)
        self.assertIn("'=HYPERLINK(1)", [row[0] for row in rows])               # neutralised
        self.assertNotIn("=HYPERLINK(1)", [row[0] for row in rows])
        self.assertEqual(sorted(row[3] for row in rows[1:]), ["0", "0", "15", "3"])   # numbers stay numeric


class MovementReportTests(ReportCase):
    def test_summary_filters_and_csv(self):
        url_ = url("inventory_report_movements")
        r = self.client.get(url_)
        s = dict(r.context["summary"])
        self.assertEqual((s["Movements"], s["Units added"], s["Units removed"], s["Net change"]), (4, 27, 5, 22))
        count = lambda **q: len(self.client.get(url_, q).context["page"])
        self.assertEqual(count(type="out"), 1)
        self.assertEqual(count(q="inv-1"), 1)
        self.assertEqual(count(q="oil"), 2)
        self.assertEqual(count(reason="sale"), 1)
        today = timezone.localdate()
        self.assertEqual(count(date_from=today.isoformat(), date_to=today.isoformat()), 4)
        self.assertEqual(count(date_from=(today + dt.timedelta(days=1)).isoformat()), 0)
        self.assertEqual(count(date_from="junk", type="bogus", reason="bogus"), 4)
        rows = csv_rows(self.client.get(url_, {"type": "out", "export": "csv"}))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][rows[0].index("Change")], "-5")                  # a real negative number, not quoted text
        self.assertEqual(rows[1][rows[0].index("Reference")], "INV-1")


class PurchaseReportTests(ReportCase):
    def test_totals_follow_filters(self):
        self.purchase("PUR-T-1", [(self.oil, 10, "20.00"), (self.cream, 2, "40.00")], status="received")    # 280
        self.purchase("PUR-T-2", [(self.cream, 5, "40.00")])                                                  # 200 draft
        self.purchase("PUR-T-3", [(self.cream, 1, "40.00")], status="cancelled")
        url_ = url("inventory_report_purchases")
        r = self.client.get(url_)
        s = dict(r.context["summary"])
        self.assertEqual((s["Purchases"], s["Received value"], s["Awaiting receipt (value)"], s["Cancelled"]), (3, "₹280.00", "₹200.00", 1))
        self.assertEqual(sorted(row[5]["text"] for row in r.context["page"]), [1, 1, 2])       # line counts
        s = dict(self.client.get(url_, {"status": "received"}).context["summary"])
        self.assertEqual((s["Purchases"], s["Received value"], s["Awaiting receipt (value)"]), (1, "₹280.00", "₹0.00"))
        self.assertEqual(len(self.client.get(url_, {"supplier": self.sup.pk, "date_from": "2026-11-10", "date_to": "2026-11-10"}).context["page"]), 3)
        self.assertEqual(len(self.client.get(url_, {"date_to": "2026-11-09"}).context["page"]), 0)
        rows = csv_rows(self.client.get(url_, {"export": "csv"}))
        self.assertEqual(len(rows), 4)
        self.assertIn("PUR-T-1", [row[0] for row in rows])


class ProductHistoryReportTests(ReportCase):
    def test_balances_and_empty_state(self):
        url_ = url("inventory_report_product_history")
        r = self.client.get(url_)
        self.assertEqual(r.context["summary"], [])
        self.assertContains(r, "choose a product")
        r = self.client.get(url_, {"product": self.oil.pk})
        s = dict(r.context["summary"])
        self.assertEqual((s["Opening balance"], s["Units added"], s["Units removed"], s["Closing balance"]), (0, 20, 5, 15))
        self.assertEqual([row[3]["text"] for row in r.context["page"]], ["+20", "-5"])        # oldest first
        s = dict(self.client.get(url_, {"product": self.oil.pk, "type": "out"}).context["summary"])
        self.assertEqual((s["Opening balance"], s["Closing balance"]), (20, 15))
        s = dict(self.client.get(url_, {"product": self.oil.pk, "date_from": "2099-01-01"}).context["summary"])
        self.assertEqual((s["Opening balance"], s["Closing balance"], s["Units added"]), ("—", "—", 0))
        self.assertEqual(self.client.get(url_, {"product": "999999"}).status_code, 200)
        rows = csv_rows(self.client.get(url_, {"product": self.oil.pk, "export": "csv"}))
        self.assertEqual(len(rows), 3)

    def test_pagination_keeps_filters(self):
        big = Product.objects.create(category=self.cat, name="Bulk", sku="BLK-1")
        for _ in range(35):
            svc.stock_in(big.pk, 1)
        r = self.client.get(url("inventory_report_product_history"), {"product": big.pk})
        self.assertEqual((len(r.context["page"]), r.context["page"].paginator.num_pages), (30, 2))
        self.assertIn(f"product={big.pk}", r.context["qs"])
        self.assertContains(r, f"?product={big.pk}&amp;page=2".replace("&amp;", "&"))
        self.assertEqual(len(csv_rows(self.client.get(url("inventory_report_product_history"), {"product": big.pk, "export": "csv"}))), 36)
