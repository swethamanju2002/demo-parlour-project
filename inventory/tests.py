from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from inventory import services as s
from inventory.models import Product, ProductCategory, StockMovement

R = StockMovement.Reason


class InventoryServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cat = ProductCategory.objects.create(name="Hair products")
        cls.p = Product.objects.create(category=cls.cat, name="Keratin serum", sku=" ks-001 ",
                                       cost_price=Decimal("400"), selling_price=Decimal("650"), reorder_level=3)
        cls.user = get_user_model().objects.create_user("admin1", password="x")

    def fresh(self):
        self.p.refresh_from_db()
        return self.p

    def test_sku_is_normalised_and_unique(self):
        self.assertEqual(self.p.sku, "KS-001")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Product.objects.create(category=self.cat, name="Dup", sku="ks-001")

    def test_stock_in_out_and_ledger(self):
        m1 = s.stock_in(self.p.pk, 10, reason=R.OPENING, user=self.user, unit_cost="400")
        m2 = s.stock_out(self.p.pk, "4", reason=R.SALE, reference="INV-1")
        self.assertEqual(self.fresh().quantity_on_hand, 6)
        self.assertEqual((m1.quantity_before, m1.quantity_after, m1.change, m1.created_by), (0, 10, 10, self.user))
        self.assertEqual((m2.quantity_before, m2.quantity_after, m2.change), (10, 6, -4))
        self.assertEqual(m1.unit_cost, Decimal("400.00"))
        self.assertEqual(self.p.movements.count(), 2)

    def test_cannot_go_negative(self):
        s.stock_in(self.p.pk, 2)
        with self.assertRaises(ValidationError):
            s.stock_out(self.p.pk, 3)
        self.assertEqual(self.fresh().quantity_on_hand, 2)
        self.assertEqual(self.p.movements.count(), 1)       # failed attempt leaves no trace
        s.stock_out(self.p.pk, 2)
        self.assertEqual(self.fresh().quantity_on_hand, 0)

    def test_invalid_quantities_rejected(self):
        for bad in (0, -1, "abc", 1.5, True, None, "", "2.5"):
            with self.assertRaises(ValidationError, msg=repr(bad)):
                s.stock_in(self.p.pk, bad)
        with self.assertRaises(ValidationError):
            s.stock_in(self.p.pk, 1, unit_cost="-5")
        with self.assertRaises(ValidationError):
            s.stock_in(self.p.pk, 1, unit_cost="NaN")
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_reason_must_match_direction(self):
        with self.assertRaises(ValidationError):
            s.stock_in(self.p.pk, 1, reason=R.SALE)
        with self.assertRaises(ValidationError):
            s.stock_out(self.p.pk, 1, reason=R.PURCHASE)
        with self.assertRaises(ValidationError):
            s.stock_in(self.p.pk, 1, reason="made-up")

    def test_adjustment_needs_note_and_a_real_difference(self):
        s.stock_in(self.p.pk, 5)
        with self.assertRaises(ValidationError):
            s.adjust_stock(self.p.pk, 3, notes="  ")
        with self.assertRaises(ValidationError):
            s.adjust_stock(self.p.pk, 5, notes="recount")
        with self.assertRaises(ValidationError):
            s.adjust_stock(self.p.pk, -1, notes="recount")
        m = s.adjust_stock(self.p.pk, 3, notes="Shelf count", user=self.user)
        self.assertEqual((m.change, m.quantity_after, m.movement_type), (-2, 3, "adjustment"))
        m = s.adjust_stock(self.p.pk, 8, notes="Found a box")
        self.assertEqual((m.change, self.fresh().quantity_on_hand), (5, 8))

    def test_inactive_or_missing_product_refused(self):
        Product.objects.filter(pk=self.p.pk).update(is_active=False)
        with self.assertRaises(ValidationError):
            s.stock_in(self.p.pk, 1)
        with self.assertRaises(ValidationError):
            s.stock_in(99999, 1)

    def test_ledger_is_append_only(self):
        m = s.stock_in(self.p.pk, 5)
        m.notes = "tampered"
        with self.assertRaises(ValidationError):
            m.save()
        with self.assertRaises(ValidationError):
            m.delete()

    def test_db_blocks_inconsistent_ledger_rows(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            StockMovement.objects.create(product=self.p, movement_type="in", reason="purchase",
                                         change=5, quantity_before=0, quantity_after=9)
        with self.assertRaises(IntegrityError), transaction.atomic():
            StockMovement.objects.create(product=self.p, movement_type="in", reason="purchase",
                                         change=0, quantity_before=1, quantity_after=1)

    def test_low_stock(self):
        self.assertTrue(self.p.is_low_stock)                      # 0 <= 3
        s.stock_in(self.p.pk, 4)
        self.assertNotIn(self.p, Product.objects.low_stock())
        s.stock_out(self.p.pk, 1)
        self.assertIn(self.p, Product.objects.low_stock())        # 3 <= 3
        Product.objects.filter(pk=self.p.pk).update(is_active=False)
        self.assertNotIn(self.p, Product.objects.low_stock())

    def test_stock_value_uses_cost(self):
        s.stock_in(self.p.pk, 3)
        self.assertEqual(self.fresh().stock_value, Decimal("1200.00"))
