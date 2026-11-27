import datetime as dt

from django.urls import reverse
from django.utils import timezone

from inventory import services as svc
from inventory.models import Product, StockMovement
from inventory.test_admin import InventoryAdminCase


def url(name, pk):
    return reverse(f"admin_panel:{name}", args=[pk])


class StockPageTests(InventoryAdminCase):
    def test_access(self):
        for n in ("inventory_product_detail",):
            self.client.logout()
            self.assertEqual(self.client.get(url(n, self.p.pk)).status_code, 302)
            self.client.force_login(self.plain)
            self.assertEqual(self.client.get(url(n, self.p.pk)).status_code, 403)
        for n in ("inventory_stock_in", "inventory_stock_out", "inventory_stock_adjust"):
            self.assertEqual(self.client.post(url(n, self.p.pk), {}).status_code, 403, n)
        self.assertEqual(self.client.get(reverse("admin_panel:inventory_movements")).status_code, 403)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_pages_render_and_actions_are_post_only(self):
        self.assertEqual(self.client.get(url("inventory_product_detail", self.p.pk)).status_code, 200)
        self.assertEqual(self.client.get(url("inventory_product_detail", 9999)).status_code, 404)
        self.assertEqual(self.client.get(reverse("admin_panel:inventory_movements")).status_code, 200)
        for n in ("inventory_stock_in", "inventory_stock_out", "inventory_stock_adjust"):
            self.assertEqual(self.client.get(url(n, self.p.pk)).status_code, 405, n)

    def test_stock_in_records_user_cost_and_reference(self):
        r = self.client.post(url("inventory_stock_in", self.p.pk),
                             {"in-quantity": "12", "in-reason": "purchase", "in-unit_cost": "95.50", "in-reference": "BILL-7", "in-notes": ""})
        self.assertRedirects(r, url("inventory_product_detail", self.p.pk))
        self.p.refresh_from_db()
        m = StockMovement.objects.get()
        self.assertEqual((self.p.quantity_on_hand, m.change, m.created_by, m.reference, str(m.unit_cost)), (12, 12, self.admin, "BILL-7", "95.50"))

    def test_stock_out_and_insufficient_stock(self):
        svc.stock_in(self.p.pk, 3)
        r = self.client.post(url("inventory_stock_out", self.p.pk), {"out-quantity": "5", "out-reason": "sale"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("Not enough stock", str(r.context["out_form"].non_field_errors()))
        self.p.refresh_from_db()
        self.assertEqual((self.p.quantity_on_hand, StockMovement.objects.count()), (3, 1))
        r = self.client.post(url("inventory_stock_out", self.p.pk), {"out-quantity": "3", "out-reason": "service_use", "out-reference": "DQ-1"})
        self.assertEqual(r.status_code, 302)
        self.p.refresh_from_db()
        self.assertEqual(self.p.quantity_on_hand, 0)

    def test_bad_input_rejected(self):
        cases = [("inventory_stock_in", {"in-quantity": "0", "in-reason": "purchase"}, "in_form"),
                 ("inventory_stock_in", {"in-quantity": "2.5", "in-reason": "purchase"}, "in_form"),
                 ("inventory_stock_in", {"in-quantity": "-3", "in-reason": "purchase"}, "in_form"),
                 ("inventory_stock_in", {"in-quantity": "1", "in-reason": "sale"}, "in_form"),          # wrong direction
                 ("inventory_stock_in", {"in-quantity": "1", "in-reason": "purchase", "in-unit_cost": "-1"}, "in_form"),
                 ("inventory_stock_out", {"out-quantity": "1", "out-reason": "purchase"}, "out_form"),
                 ("inventory_stock_adjust", {"adj-new_quantity": "-1", "adj-reason": "stocktake", "adj-notes": "x"}, "adjust_form"),
                 ("inventory_stock_adjust", {"adj-new_quantity": "4", "adj-reason": "stocktake", "adj-notes": "  "}, "adjust_form")]
        for name, data, key in cases:
            r = self.client.post(url(name, self.p.pk), data)
            self.assertEqual(r.status_code, 200, data)
            self.assertTrue(r.context[key].errors, data)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_adjustment(self):
        svc.stock_in(self.p.pk, 10)
        same = self.client.post(url("inventory_stock_adjust", self.p.pk), {"adj-new_quantity": "10", "adj-reason": "stocktake", "adj-notes": "recount"})
        self.assertEqual(same.status_code, 200)
        self.assertIn("Nothing to adjust", str(same.context["adjust_form"].non_field_errors()))
        r = self.client.post(url("inventory_stock_adjust", self.p.pk), {"adj-new_quantity": "7", "adj-reason": "damaged", "adj-notes": "Leaking bottles"})
        self.assertEqual(r.status_code, 302)
        self.p.refresh_from_db()
        m = StockMovement.objects.first()
        self.assertEqual((self.p.quantity_on_hand, m.change, m.movement_type, m.notes), (7, -3, "adjustment", "Leaking bottles"))

    def test_inactive_product_refused_by_server(self):
        Product.objects.filter(pk=self.p.pk).update(is_active=False)
        r = self.client.post(url("inventory_stock_in", self.p.pk), {"in-quantity": "1", "in-reason": "purchase"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("inactive", str(r.context["in_form"].non_field_errors()))
        self.assertContains(self.client.get(url("inventory_product_detail", self.p.pk)), "This product is inactive")

    def test_history_on_detail_and_global_list_with_filters(self):
        other = Product.objects.create(category=self.cat, name="Mask", sku="MSK-1")
        svc.stock_in(self.p.pk, 5, reference="BILL-A")
        svc.stock_out(self.p.pk, 2)
        svc.stock_in(other.pk, 9)
        detail = self.client.get(url("inventory_product_detail", self.p.pk))
        self.assertEqual(len(detail.context["page"]), 2)
        self.assertContains(detail, "BILL-A")
        lst = reverse("admin_panel:inventory_movements")
        count = lambda **q: len(self.client.get(lst, q).context["page"])
        self.assertEqual(count(), 3)
        self.assertEqual(count(type="out"), 1)
        self.assertEqual(count(q="msk"), 1)
        self.assertEqual(count(q="bill-a"), 1)
        today = timezone.localdate()
        self.assertEqual(count(date_from=today.isoformat()), 3)
        self.assertEqual(count(date_from=(today + dt.timedelta(days=1)).isoformat()), 0)
        self.assertEqual(count(date_to=(today - dt.timedelta(days=1)).isoformat()), 0)
        self.assertEqual(count(date_from="garbage", type="bogus"), 3)           # bad filters are ignored, not fatal
