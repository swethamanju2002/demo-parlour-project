"""Purchase workflow. Stock only changes in receive_purchase(), which goes through inventory.services.stock_in.

draft -> ordered -> received      cancelled is possible from draft/ordered only.
Receiving is all-or-nothing and can happen once: the purchase row is locked, its status is re-checked,
and the database allows only one ledger row per (purchase, product).
"""
import secrets

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from . import services
from .models import Purchase, StockMovement

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_purchase_number():
    for _ in range(20):
        number = f"PUR-{timezone.localdate():%y%m%d}-" + "".join(secrets.choice(_ALPHABET) for _ in range(4))
        if not Purchase.objects.filter(purchase_number=number).exists():
            return number
    raise ValidationError("Could not generate a purchase number. Please try again.")


def recalculate_total(purchase):
    """Total is always computed from the saved lines; nothing the browser sends is trusted."""
    total = purchase.items.aggregate(t=Sum("line_total"))["t"] or 0
    Purchase.objects.filter(pk=purchase.pk).update(total_amount=total, updated_at=timezone.now())
    purchase.total_amount = total
    return total


def _lock(purchase_id):
    try:
        return Purchase.objects.select_for_update().get(pk=purchase_id)
    except Purchase.DoesNotExist:
        raise ValidationError("That purchase does not exist.")


def mark_ordered(purchase_id):
    with transaction.atomic():
        purchase = _lock(purchase_id)
        if purchase.status != Purchase.Status.DRAFT:
            raise ValidationError("Only a draft purchase can be marked as ordered.")
        if not purchase.items.exists():
            raise ValidationError("Add at least one product before ordering.")
        purchase.status = Purchase.Status.ORDERED
        purchase.save(update_fields=["status", "updated_at"])
    return purchase


def cancel_purchase(purchase_id):
    with transaction.atomic():
        purchase = _lock(purchase_id)
        if not purchase.can_cancel:
            raise ValidationError(f"A {purchase.get_status_display().lower()} purchase cannot be cancelled.")
        purchase.status = Purchase.Status.CANCELLED
        purchase.save(update_fields=["status", "updated_at"])
    return purchase


def receive_purchase(purchase_id, user=None):
    with transaction.atomic():
        purchase = _lock(purchase_id)
        if not purchase.can_receive:
            raise ValidationError(f"This purchase is already {purchase.get_status_display().lower()} and cannot be received.")
        items = list(purchase.items.select_related("product"))
        if not items:
            raise ValidationError("This purchase has no products to receive.")
        for item in items:
            services.stock_in(
                item.product_id, item.quantity, reason=StockMovement.Reason.PURCHASE, unit_cost=item.unit_cost,
                reference=purchase.purchase_number, notes=f"Received from {purchase.supplier.name}",
                user=user, purchase=purchase,
            )
        purchase.status = Purchase.Status.RECEIVED
        purchase.received_at = timezone.now()
        purchase.received_by = user
        purchase.save(update_fields=["status", "received_at", "received_by", "updated_at"])
    return purchase
