"""Decimal helpers. All money maths goes through here; floats are never used for money."""

from decimal import ROUND_HALF_UP, Decimal

PAISE = Decimal("0.01")
COST = Decimal("0.0001")  # unit costs keep 4 places so averages don't drift
RUPEE = Decimal("1")
ZERO = Decimal("0")


def q2(x: Decimal) -> Decimal:
    """Round to paise, half-up (how GST invoices round)."""
    return x.quantize(PAISE, rounding=ROUND_HALF_UP)


def q4(x: Decimal) -> Decimal:
    return x.quantize(COST, rounding=ROUND_HALF_UP)


def round_off(total: Decimal) -> Decimal:
    """Amount to add so the bill is a whole rupee (can be negative)."""
    return q2(total.quantize(RUPEE, rounding=ROUND_HALF_UP) - total)


def split_gst(gst: Decimal) -> tuple[Decimal, Decimal]:
    """CGST/SGST halves that always add back to the exact GST amount."""
    cgst = q2(gst / 2)
    return cgst, gst - cgst


def allocate(total: Decimal, weights: list[Decimal]) -> list[Decimal]:
    """Split `total` across weights in paise; the parts always sum exactly to `total`.

    Uses largest-remainder so no paisa is lost or invented by rounding.
    """
    if not weights:
        return []
    weight_sum = sum(weights, ZERO)
    if weight_sum == 0:
        weights = [Decimal(1)] * len(weights)
        weight_sum = Decimal(len(weights))
    total_paise = int((total / PAISE).to_integral_value(rounding=ROUND_HALF_UP))
    raw = [Decimal(total_paise) * w / weight_sum for w in weights]
    floors = [int(r) for r in raw]
    leftover = total_paise - sum(floors)
    order = sorted(range(len(raw)), key=lambda i: raw[i] - floors[i], reverse=True)
    for i in order[:leftover]:
        floors[i] += 1
    return [Decimal(p) * PAISE for p in floors]
