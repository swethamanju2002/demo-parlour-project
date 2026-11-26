"""Stock operations. The only code allowed to change Product.quantity_on_hand.

Each operation locks the product row, validates, updates the balance and writes a ledger row inside
one transaction, so the balance and the history can never disagree and stock cannot go negative.
"""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Product, StockMovement

T, R = StockMovement.Type, StockMovement.Reason

ALLOWED_REASONS = {
    T.IN: {R.PURCHASE, R.OPENING, R.CUSTOMER_RETURN, R.OTHER},
    T.OUT: {R.SALE, R.SERVICE_USE, R.DAMAGED, R.EXPIRED, R.SUPPLIER_RETURN, R.OTHER},
    T.ADJUSTMENT: {R.STOCKTAKE, R.DAMAGED, R.EXPIRED, R.OTHER},
}


def _whole_number(value, label, *, minimum):
    if isinstance(value, bool) or isinstance(value, float):
        raise ValidationError(f"{label} must be a whole number.")
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValidationError(f"{label} must be a whole number.")
    if number < minimum:
        raise ValidationError(f"{label} must be {'greater than zero' if minimum == 1 else 'zero or more'}.")
    return number


def _reason(movement_type, reason):
    if reason not in {r.value for r in ALLOWED_REASONS[movement_type]}:
        raise ValidationError("Choose a valid reason for this stock change.")
    return reason


def _unit_cost(value):
    if value in (None, ""):
        return None
    try:
        cost = Decimal(str(value))
    except InvalidOperation:
        raise ValidationError("Unit cost must be a number.")
    if not cost.is_finite() or cost < 0:
        raise ValidationError("Unit cost cannot be negative.")
    return cost.quantize(Decimal("0.01"))


def _apply(product_id, movement_type, reason, change_fn, *, unit_cost=None, reference="", notes="", user=None):
    with transaction.atomic():
        try:
            product = Product.objects.select_for_update().get(pk=product_id)
        except Product.DoesNotExist:
            raise ValidationError("That product does not exist.")
        if not product.is_active:
            raise ValidationError("This product is inactive. Activate it before changing its stock.")
        before = product.quantity_on_hand
        change = change_fn(before)
        after = before + change
        if after < 0:
            raise ValidationError(f"Not enough stock. Only {before} {product.unit} available.")
        product.quantity_on_hand = after
        product.save(update_fields=["quantity_on_hand", "updated_at"])
        return StockMovement.objects.create(
            product=product, movement_type=movement_type, reason=reason, change=change,
            quantity_before=before, quantity_after=after, unit_cost=unit_cost,
            reference=(reference or "").strip()[:80], notes=(notes or "").strip(), created_by=user,
        )


def stock_in(product_id, quantity, *, reason=R.PURCHASE, unit_cost=None, reference="", notes="", user=None):
    qty = _whole_number(quantity, "Quantity", minimum=1)
    return _apply(product_id, T.IN, _reason(T.IN, reason), lambda before: qty,
                  unit_cost=_unit_cost(unit_cost), reference=reference, notes=notes, user=user)


def stock_out(product_id, quantity, *, reason=R.SALE, reference="", notes="", user=None):
    qty = _whole_number(quantity, "Quantity", minimum=1)
    return _apply(product_id, T.OUT, _reason(T.OUT, reason), lambda before: -qty,
                  reference=reference, notes=notes, user=user)


def adjust_stock(product_id, new_quantity, *, reason=R.STOCKTAKE, notes="", user=None):
    """Set the counted quantity. A note is mandatory and a no-op adjustment is refused."""
    target = _whole_number(new_quantity, "Counted quantity", minimum=0)
    if not (notes or "").strip():
        raise ValidationError("Explain the adjustment in the notes.")

    def delta(before):
        if target == before:
            raise ValidationError("The counted quantity equals the current stock. Nothing to adjust.")
        return target - before

    return _apply(product_id, T.ADJUSTMENT, _reason(T.ADJUSTMENT, reason), delta, notes=notes, user=user)
