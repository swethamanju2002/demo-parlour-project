import datetime as dt
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse

from inventory import purchasing, services as svc
from inventory.models import Product, Purchase, PurchaseItem, StockMovement, Supplier
from inventory.test_admin import InventoryAdminCase


def msgs(response):
    return " ".join(str(m) for m in response.context["messages"])


def url(name, *args):
    return reverse(f"admin_panel:{name}", args=args)


def items_data(rows, initial=0, existing=()):
    d = {"items-TOTAL_FORMS": str(len(rows)), "items-INITIAL_FORMS": str(initial),
         "items-MIN_NUM_FORMS": "1", "items-MAX_NUM_FORMS": "1000"}
    for i, row in enumerate(rows):
        d[f"items-{i}-product"], d[f"items-{i}-quantity"], d[f"items-{i}-unit_cost"] = row
    for i, (item_id, purchase_id) in enumerate(existing):
        d[f"items-{i}-id"], d[f"items-{i}-purchase"] = item_id, purchase_id
    return d


class PurchaseCase(InventoryAdminCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.other = Product.objects.create(category=cls.cat, name="Mask", sku="MSK-1", cost_price=Decimal("50"))
        cls.sup = Supplier.objects.create(name="Glow Distributors", phone="9876543210")

    def header(self, **over):
        d = {"supplier": self.sup.pk, "invoice_number": "INV-9", "purchase_date": "2026-11-20", "notes": ""}
        d.update(over)
        return d

    def make(self, rows=None, **over):
        """Create a purchase through the real create view; returns the Purchase."""
        rows = rows or [(self.p.pk, "10", "95.50"), (self.other.pk, "4", "40.00")]
        r = self.client.post(url("inventory_purchase_create"), {**self.header(**over), **items_data(rows)})
        self.assertEqual(r.status_code, 302, getattr(r, "context", None) and r.context["formset"].errors)
        return Purchase.objects.latest("id")


class SupplierTests(PurchaseCase):
    def test_access_and_pages(self):
        names = ("inventory_suppliers", "inventory_supplier_create", "inventory_purchases", "inventory_purchase_create")
        for n in names:
            self.client.logout()
            self.assertEqual(self.client.get(url(n)).status_code, 302, n)
            self.client.force_login(self.plain)
            self.assertEqual(self.client.get(url(n)).status_code, 403, n)
        self.client.force_login(self.admin)
        for n in names:
            self.assertEqual(self.client.get(url(n)).status_code, 200, n)
        self.assertEqual(self.client.get(url("inventory_supplier_edit", self.sup.pk)).status_code, 200)
        self.assertEqual(self.client.get(url("inventory_supplier_toggle", self.sup.pk)).status_code, 405)

    def test_create_edit_toggle_and_validation(self):
        r = self.client.post(url("inventory_supplier_create"), {"name": "  New   Co ", "phone": "98765 43210", "is_active": "on"})
        self.assertRedirects(r, url("inventory_suppliers"))
        s = Supplier.objects.get(name="New Co")
        for over, field in (({"name": "glow distributors"}, "name"), ({"name": "X", "phone": "abc"}, "phone"), ({"name": "Y", "email": "bad"}, "email")):
            r = self.client.post(url("inventory_supplier_create"), over)
            self.assertIn(field, r.context["form"].errors, over)
        self.client.post(url("inventory_supplier_edit", s.pk), {"name": "New Co Ltd", "is_active": "on"})
        s.refresh_from_db()
        self.assertEqual(s.name, "New Co Ltd")
        self.client.post(url("inventory_supplier_toggle", s.pk))
        s.refresh_from_db()
        self.assertFalse(s.is_active)

    def test_search_and_counts(self):
        self.make()
        r = self.client.get(url("inventory_suppliers"), {"q": "glow"})
        self.assertEqual([x.purchase_count for x in r.context["page"]], [1])
        self.assertEqual(len(self.client.get(url("inventory_suppliers"), {"q": "zzz"}).context["page"]), 0)


class PurchaseCreateEditTests(PurchaseCase):
    def test_create_computes_total_server_side(self):
        r = self.client.post(url("inventory_purchase_create"),
                             {**self.header(total_amount="1"), **items_data([(self.p.pk, "10", "95.50"), (self.other.pk, "4", "40.00")])})
        pu = Purchase.objects.get()
        self.assertRedirects(r, url("inventory_purchase_detail", pu.pk))
        self.assertEqual((pu.status, pu.total_amount, pu.created_by, pu.items.count()), ("draft", Decimal("1115.00"), self.admin, 2))
        self.assertRegex(pu.purchase_number, r"^PUR-\d{6}-[A-HJ-NP-Z2-9]{4}$")
        self.assertEqual(sorted(i.line_total for i in pu.items.all()), [Decimal("160.00"), Decimal("955.00")])
        self.assertEqual(self.client.get(url("inventory_purchase_detail", pu.pk)).status_code, 200)
        self.p.refresh_from_db()
        self.assertEqual(self.p.quantity_on_hand, 0)                       # nothing received yet

    def test_validation(self):
        url_ = url("inventory_purchase_create")
        bad = [({**self.header(), **items_data([(self.p.pk, "1", "5"), (self.p.pk, "2", "5")])}, "listed more than once"),
               ({**self.header(), **items_data([("", "", "")])}, None),
               ({**self.header(), **items_data([(self.p.pk, "0", "5")])}, None),
               ({**self.header(), **items_data([(self.p.pk, "-2", "5")])}, None),
               ({**self.header(), **items_data([(self.p.pk, "2.5", "5")])}, None),
               ({**self.header(), **items_data([(self.p.pk, "2", "-5")])}, None),
               ({**self.header(), **items_data([("9999", "2", "5")])}, None),
               ({**self.header(supplier="9999"), **items_data([(self.p.pk, "2", "5")])}, None),
               ({**self.header(purchase_date="nope"), **items_data([(self.p.pk, "2", "5")])}, None)]
        for data, text in bad:
            r = self.client.post(url_, data)
            self.assertEqual(r.status_code, 200, data)
            if text:
                self.assertIn(text, str(r.context["formset"].non_form_errors()))
        self.assertEqual(Purchase.objects.count(), 0)

    def test_inactive_supplier_and_product_not_offered(self):
        Supplier.objects.filter(pk=self.sup.pk).update(is_active=False)
        Product.objects.filter(pk=self.other.pk).update(is_active=False)
        r = self.client.post(url("inventory_purchase_create"), {**self.header(), **items_data([(self.p.pk, "1", "5")])})
        self.assertIn("supplier", r.context["form"].errors)
        Supplier.objects.filter(pk=self.sup.pk).update(is_active=True)
        r = self.client.post(url("inventory_purchase_create"), {**self.header(), **items_data([(self.other.pk, "1", "5")])})
        self.assertTrue(r.context["formset"].errors[0].get("product"))

    def test_edit_replaces_lines_and_recalculates(self):
        pu = self.make()
        first, second = list(pu.items.order_by("id"))
        data = {**self.header(invoice_number="INV-10"),
                **items_data([(self.p.pk, "20", "100.00"), (self.other.pk, "4", "40.00")], initial=2,
                             existing=[(first.pk, pu.pk), (second.pk, pu.pk)])}
        data["items-1-DELETE"] = "on"
        r = self.client.post(url("inventory_purchase_edit", pu.pk), data)
        self.assertRedirects(r, url("inventory_purchase_detail", pu.pk))
        pu.refresh_from_db()
        self.assertEqual((pu.invoice_number, pu.total_amount, pu.items.count(), pu.status), ("INV-10", Decimal("2000.00"), 1, "draft"))

    def test_edit_cannot_revert_status_or_touch_closed_purchases(self):
        pu = self.make()
        purchasing.mark_ordered(pu.pk)
        r = self.client.post(url("inventory_purchase_edit", pu.pk), {**self.header(), **items_data([(self.p.pk, "1", "1")])})
        self.assertRedirects(r, url("inventory_purchase_detail", pu.pk))      # clash is reported, not a server error
        pu.refresh_from_db()
        self.assertEqual((pu.status, pu.items.count()), ("ordered", 2))
        purchasing.receive_purchase(pu.pk, self.admin)
        for method in (self.client.get, lambda u: self.client.post(u, {**self.header(), **items_data([(self.p.pk, "1", "1")])})):
            self.assertRedirects(method(url("inventory_purchase_edit", pu.pk)), url("inventory_purchase_detail", pu.pk))
        self.assertEqual(Purchase.objects.get(pk=pu.pk).total_amount, Decimal("1115.00"))

    def test_list_filters(self):
        a = self.make(purchase_date="2026-11-01", invoice_number="AAA")
        b = self.make(purchase_date="2026-11-20", invoice_number="BBB")
        purchasing.cancel_purchase(b.pk)
        other_sup = Supplier.objects.create(name="Other Co")
        c = self.make(supplier=other_sup.pk)
        lst = url("inventory_purchases")
        ids = lambda **q: sorted(p.pk for p in self.client.get(lst, q).context["page"])
        self.assertEqual(ids(), sorted([a.pk, b.pk, c.pk]))
        self.assertEqual(ids(status="cancelled"), [b.pk])
        self.assertEqual(ids(supplier=other_sup.pk), [c.pk])
        self.assertEqual(ids(q="aaa"), [a.pk])
        self.assertEqual(ids(q=a.purchase_number), [a.pk])
        self.assertEqual(ids(date_from="2026-11-10", date_to="2026-11-25", supplier=self.sup.pk), [b.pk])
        self.assertEqual(ids(date_from="garbage", status="bogus"), sorted([a.pk, b.pk, c.pk]))
        self.assertEqual(self.client.get(lst).context["awaiting_count"], 2)


class ReceiveTests(PurchaseCase):
    def test_receive_adds_stock_and_links_ledger(self):
        pu = self.make()
        self.client.post(url("inventory_purchase_order", pu.pk))
        r = self.client.post(url("inventory_purchase_receive", pu.pk))
        self.assertRedirects(r, url("inventory_purchase_detail", pu.pk))
        pu.refresh_from_db(); self.p.refresh_from_db(); self.other.refresh_from_db()
        self.assertEqual((pu.status, pu.received_by), ("received", self.admin))
        self.assertIsNotNone(pu.received_at)
        self.assertEqual((self.p.quantity_on_hand, self.other.quantity_on_hand), (10, 4))
        moves = StockMovement.objects.filter(purchase=pu)
        self.assertEqual(moves.count(), 2)
        m = moves.get(product=self.p)
        self.assertEqual((m.movement_type, m.reason, m.change, m.reference, m.unit_cost, m.created_by),
                         ("in", "purchase", 10, pu.purchase_number, Decimal("95.50"), self.admin))
        self.assertEqual(self.p.cost_price, Decimal("100.00"))             # product prices are never changed silently
        self.assertContains(self.client.get(url("inventory_purchase_detail", pu.pk)), "Stock added")

    def test_receiving_twice_never_double_counts(self):
        pu = self.make()
        self.client.post(url("inventory_purchase_receive", pu.pk))
        r = self.client.post(url("inventory_purchase_receive", pu.pk), follow=True)
        self.assertIn("already received", msgs(r))
        with self.assertRaises(ValidationError):
            purchasing.receive_purchase(pu.pk, self.admin)
        self.p.refresh_from_db()
        self.assertEqual(self.p.quantity_on_hand, 10)
        self.assertEqual(StockMovement.objects.filter(purchase=pu).count(), 2)

    def test_database_blocks_duplicate_ledger_row_for_a_purchase_line(self):
        pu = self.make([(self.p.pk, "10", "5")])
        purchasing.receive_purchase(pu.pk, self.admin)
        with self.assertRaises(IntegrityError), transaction.atomic():
            svc.stock_in(self.p.pk, 1, purchase=pu)
        self.p.refresh_from_db()
        self.assertEqual(self.p.quantity_on_hand, 10)

    def test_receive_is_all_or_nothing(self):
        pu = self.make()
        Product.objects.filter(pk=self.other.pk).update(is_active=False)    # second line cannot be stocked
        r = self.client.post(url("inventory_purchase_receive", pu.pk), follow=True)
        self.assertIn("inactive", msgs(r))
        pu.refresh_from_db(); self.p.refresh_from_db()
        self.assertEqual((pu.status, pu.received_at, self.p.quantity_on_hand, StockMovement.objects.count()), ("draft", None, 0, 0))
        Product.objects.filter(pk=self.other.pk).update(is_active=True)
        purchasing.receive_purchase(pu.pk, self.admin)
        self.p.refresh_from_db()
        self.assertEqual(self.p.quantity_on_hand, 10)

    def test_cancel_rules(self):
        pu = self.make()
        self.client.post(url("inventory_purchase_cancel", pu.pk))
        self.assertEqual(Purchase.objects.get(pk=pu.pk).status, "cancelled")
        with self.assertRaises(ValidationError):
            purchasing.receive_purchase(pu.pk, self.admin)
        with self.assertRaises(ValidationError):
            purchasing.mark_ordered(pu.pk)
        done = self.make()
        purchasing.receive_purchase(done.pk, self.admin)
        with self.assertRaises(ValidationError):
            purchasing.cancel_purchase(done.pk)
        self.assertEqual(Purchase.objects.get(pk=done.pk).status, "received")

    def test_order_needs_draft(self):
        pu = self.make()
        purchasing.mark_ordered(pu.pk)
        with self.assertRaises(ValidationError):
            purchasing.mark_ordered(pu.pk)

    def test_actions_are_post_only_and_admin_only(self):
        pu = self.make()
        for n in ("inventory_purchase_order", "inventory_purchase_receive", "inventory_purchase_cancel"):
            self.assertEqual(self.client.get(url(n, pu.pk)).status_code, 405, n)
        self.client.force_login(self.plain)
        for n in ("inventory_purchase_order", "inventory_purchase_receive", "inventory_purchase_cancel"):
            self.assertEqual(self.client.post(url(n, pu.pk)).status_code, 403, n)
        self.assertEqual(Purchase.objects.get(pk=pu.pk).status, "draft")

    def test_db_constraints(self):
        pu = self.make()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Purchase.objects.filter(pk=pu.pk).update(status="received")     # received needs a timestamp
        with self.assertRaises(IntegrityError), transaction.atomic():
            PurchaseItem.objects.create(purchase=pu, product=self.p, quantity=1, unit_cost=1)   # duplicate line
        with self.assertRaises(IntegrityError), transaction.atomic():
            PurchaseItem.objects.create(purchase=pu, product=self.other, quantity=0, unit_cost=1)

    def test_item_snapshot_survives_rename(self):
        pu = self.make([(self.p.pk, "2", "10")])
        Product.objects.filter(pk=self.p.pk).update(name="Renamed")
        self.assertEqual(pu.items.get().product_name, "Serum")
