from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from inventory import services as svc
from inventory.models import Product, ProductCategory


class InventoryAdminCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        U = get_user_model()
        cls.admin = U.objects.create_user("boss", password="x", is_superuser=True)
        cls.plain = U.objects.create_user("cust", password="x")
        cls.cat = ProductCategory.objects.create(name="Hair care")
        cls.p = Product.objects.create(category=cls.cat, name="Serum", sku="SRM-1", cost_price=Decimal("100"),
                                       selling_price=Decimal("250"), reorder_level=2)

    def setUp(self):
        self.client.force_login(self.admin)

    def product_data(self, **over):
        d = dict(category=self.cat.pk, name="Shampoo", sku="shp-1", description="", unit="bottle",
                 cost_price="120.00", selling_price="300.00", reorder_level="5", is_active="on")
        d.update(over)
        return d


class AccessTests(InventoryAdminCase):
    NAMES = ("inventory_products", "inventory_product_create", "inventory_categories", "inventory_category_create")

    def test_anonymous_redirected_and_non_admin_forbidden(self):
        for n in self.NAMES:
            self.client.logout()
            self.assertEqual(self.client.get(reverse(f"admin_panel:{n}")).status_code, 302, n)
            self.client.force_login(self.plain)
            self.assertEqual(self.client.get(reverse(f"admin_panel:{n}")).status_code, 403, n)
        self.client.force_login(self.plain)
        self.assertEqual(self.client.post(reverse("admin_panel:inventory_product_toggle", args=[self.p.pk])).status_code, 403)
        self.p.refresh_from_db()
        self.assertTrue(self.p.is_active)

    def test_admin_pages_render(self):
        for n in self.NAMES:
            self.assertEqual(self.client.get(reverse(f"admin_panel:{n}")).status_code, 200, n)
        self.assertEqual(self.client.get(reverse("admin_panel:inventory_product_edit", args=[self.p.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin_panel:inventory_category_edit", args=[self.cat.pk])).status_code, 200)

    def test_toggle_is_post_only(self):
        self.assertEqual(self.client.get(reverse("admin_panel:inventory_product_toggle", args=[self.p.pk])).status_code, 405)
        self.assertEqual(self.client.get(reverse("admin_panel:inventory_category_toggle", args=[self.cat.pk])).status_code, 405)


class CategoryTests(InventoryAdminCase):
    def test_create_edit_toggle(self):
        r = self.client.post(reverse("admin_panel:inventory_category_create"), {"name": "  Skin   care ", "order": 1, "is_active": "on"})
        self.assertRedirects(r, reverse("admin_panel:inventory_categories"))
        c = ProductCategory.objects.get(name="Skin care")
        self.assertEqual(c.slug, "skin-care")
        self.client.post(reverse("admin_panel:inventory_category_edit", args=[c.pk]), {"name": "Skincare", "order": 2, "is_active": "on"})
        c.refresh_from_db()
        self.assertEqual((c.name, c.slug, c.order), ("Skincare", "skin-care", 2))     # slug stays stable on rename
        self.client.post(reverse("admin_panel:inventory_category_toggle", args=[c.pk]))
        c.refresh_from_db()
        self.assertFalse(c.is_active)

    def test_duplicate_and_empty_slug_names_rejected(self):
        for name in ("hair CARE", "Hair-care", "!!!"):
            r = self.client.post(reverse("admin_panel:inventory_category_create"), {"name": name, "order": 0})
            self.assertEqual(r.status_code, 200, name)
            self.assertTrue(r.context["form"].errors["name"], name)
        self.assertEqual(ProductCategory.objects.count(), 1)

    def test_list_search_and_counts(self):
        r = self.client.get(reverse("admin_panel:inventory_categories"), {"q": "hair"})
        self.assertEqual([c.product_count for c in r.context["page"]], [1])
        self.assertEqual(len(self.client.get(reverse("admin_panel:inventory_categories"), {"q": "zzz"}).context["page"]), 0)


class ProductTests(InventoryAdminCase):
    def test_create_normalises_sku_and_starts_at_zero(self):
        r = self.client.post(reverse("admin_panel:inventory_product_create"), self.product_data(quantity_on_hand="999"))
        self.assertRedirects(r, reverse("admin_panel:inventory_products"))
        p = Product.objects.get(name="Shampoo")
        self.assertEqual((p.sku, p.quantity_on_hand, p.cost_price), ("SHP-1", 0, Decimal("120.00")))   # posted quantity ignored

    def test_edit_cannot_change_stock(self):
        svc.stock_in(self.p.pk, 7)
        self.client.post(reverse("admin_panel:inventory_product_edit", args=[self.p.pk]),
                         self.product_data(name="Serum 2", sku="srm-1", quantity_on_hand="1"))
        self.p.refresh_from_db()
        self.assertEqual((self.p.name, self.p.quantity_on_hand), ("Serum 2", 7))

    def test_validation(self):
        url = reverse("admin_panel:inventory_product_create")
        for over, field in (({"sku": "srm-1"}, "sku"), ({"sku": "A B"}, "sku"), ({"cost_price": "-1"}, "cost_price"),
                            ({"selling_price": "-5"}, "selling_price"), ({"reorder_level": "-1"}, "reorder_level"),
                            ({"name": ""}, "name"), ({"category": "9999"}, "category")):
            r = self.client.post(url, self.product_data(**over))
            self.assertEqual(r.status_code, 200, over)
            self.assertIn(field, r.context["form"].errors, over)
        self.assertEqual(Product.objects.count(), 1)

    def test_own_sku_allowed_on_edit_and_inactive_category_hidden_for_new(self):
        r = self.client.post(reverse("admin_panel:inventory_product_edit", args=[self.p.pk]), self.product_data(sku="SRM-1"))
        self.assertEqual(r.status_code, 302)
        ProductCategory.objects.filter(pk=self.cat.pk).update(is_active=False)
        r = self.client.post(reverse("admin_panel:inventory_product_create"), self.product_data(sku="NEW-1"))
        self.assertIn("category", r.context["form"].errors)
        r = self.client.get(reverse("admin_panel:inventory_product_edit", args=[self.p.pk]))
        self.assertIn(self.cat, r.context["form"].fields["category"].queryset)   # still selectable on its own product

    def test_filters(self):
        other = ProductCategory.objects.create(name="Nails")
        out = Product.objects.create(category=other, name="Polish", sku="PL-1", reorder_level=0)
        svc.stock_in(self.p.pk, 2)                                             # at reorder level -> low
        url = reverse("admin_panel:inventory_products")
        names = lambda **q: sorted(p.name for p in self.client.get(url, q).context["page"])
        self.assertEqual(names(), ["Polish", "Serum"])
        self.assertEqual(names(stock="low"), ["Polish", "Serum"])
        self.assertEqual(names(stock="out"), ["Polish"])
        self.assertEqual(names(category=other.pk), ["Polish"])
        self.assertEqual(names(q="srm"), ["Serum"])
        Product.objects.filter(pk=out.pk).update(is_active=False)
        self.assertEqual(names(status="inactive"), ["Polish"])
        self.assertEqual(self.client.get(url, {"stock": "low"}).context["low_stock_count"], 1)

    def test_toggle(self):
        self.client.post(reverse("admin_panel:inventory_product_toggle", args=[self.p.pk]))
        self.p.refresh_from_db()
        self.assertFalse(self.p.is_active)
