"""Purchase entry: GST maths, landed cost, and putting good bags into stock."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Party, Product, Purchase, PurchaseLine
from app.services import stock
from app.services.gst import is_interstate
from app.services.money import ZERO, allocate, q2, q4, round_off, split_gst
from app.services.pricing import gst_rate_on


class PurchaseError(Exception):
    pass


@dataclass(frozen=True)
class LineInput:
    product_id: int
    qty_invoiced: int
    qty_received: int
    qty_damaged: int
    rate: Decimal  # per bag, before GST


@dataclass(frozen=True)
class LineCalc:
    taxable: Decimal
    gst_amount: Decimal
    charges: Decimal
    landed_cost: Decimal


def calculate_lines(
    lines: list[LineInput],
    gst_rates: list[Decimal],
    bag_kgs: list[Decimal],
    total_charges: Decimal,
) -> list[LineCalc]:
    """Pure function (no DB) so it can be tested exhaustively.

    * taxable = bags billed x rate; GST per line, rounded to paise
    * freight/unloading/other charges are split by weight (bags x kg per bag)
    * landed cost per *good* bag = (taxable + charges) / good bags. Damaged and short bags
      therefore raise the cost of the good ones until a claim is settled with the supplier.
      Input GST is excluded: the dealer gets it back as tax credit.
    """
    weights = [Decimal(ln.qty_invoiced) * kg for ln, kg in zip(lines, bag_kgs, strict=True)]
    shares = allocate(total_charges, weights)
    out = []
    for ln, gst_rate, share in zip(lines, gst_rates, shares, strict=True):
        taxable = q2(ln.qty_invoiced * ln.rate)
        gst_amount = q2(taxable * gst_rate / 100)
        landed = q4((taxable + share) / ln.qty_received) if ln.qty_received else ZERO
        out.append(LineCalc(taxable, gst_amount, share, landed))
    return out


def create_purchase(
    db: Session,
    *,
    supplier: Party,
    supplier_invoice_no: str,
    invoice_date: date,
    received_date: date,
    godown_id: int,
    lines: list[LineInput],
    freight: Decimal = ZERO,
    unloading: Decimal = ZERO,
    other_charges: Decimal = ZERO,
    vehicle_no: str | None = None,
    lr_no: str | None = None,
    notes: str | None = None,
    user_id: int | None = None,
) -> Purchase:
    if not lines:
        raise PurchaseError("Add at least one product")
    products: list[Product] = []
    gst_rates: list[Decimal] = []
    for ln in lines:
        product = db.get(Product, ln.product_id)
        if product is None:
            raise PurchaseError(f"Unknown product {ln.product_id}")
        if ln.qty_received + ln.qty_damaged > ln.qty_invoiced:
            raise PurchaseError(f"{product.name}: received + damaged is more than billed")
        rate = gst_rate_on(db, product.hsn_code, invoice_date)
        if rate is None:
            raise PurchaseError(f"No GST rate for HSN {product.hsn_code} on {invoice_date}")
        products.append(product)
        gst_rates.append(rate)

    calcs = calculate_lines(
        lines, gst_rates, [p.bag_kg for p in products], freight + unloading + other_charges
    )
    taxable_total = sum((c.taxable for c in calcs), ZERO)
    gst_total = sum((c.gst_amount for c in calcs), ZERO)
    interstate = is_interstate(get_settings().shop_state_code, supplier.state_code)
    if interstate:
        cgst = sgst = q2(ZERO)
        igst = gst_total
    else:
        cgst, sgst = split_gst(gst_total)
        igst = q2(ZERO)
    gross = taxable_total + gst_total
    ro = round_off(gross)

    purchase = Purchase(
        supplier_id=supplier.id,
        supplier_invoice_no=supplier_invoice_no.strip(),
        invoice_date=invoice_date,
        received_date=received_date,
        godown_id=godown_id,
        vehicle_no=vehicle_no,
        lr_no=lr_no,
        is_interstate=interstate,
        freight=freight,
        unloading=unloading,
        other_charges=other_charges,
        taxable_total=taxable_total,
        cgst_total=cgst,
        sgst_total=sgst,
        igst_total=igst,
        round_off=ro,
        invoice_total=gross + ro,
        notes=notes,
        created_by=user_id,
    )
    for ln, calc, gst_rate in zip(lines, calcs, gst_rates, strict=True):
        purchase.lines.append(
            PurchaseLine(
                product_id=ln.product_id,
                qty_invoiced=ln.qty_invoiced,
                qty_received=ln.qty_received,
                qty_damaged=ln.qty_damaged,
                rate=ln.rate,
                gst_rate=gst_rate,
                taxable=calc.taxable,
                gst_amount=calc.gst_amount,
                charges=calc.charges,
                landed_cost=calc.landed_cost,
            )
        )
    db.add(purchase)
    db.flush()  # get ids for the stock references

    for line in purchase.lines:
        if line.qty_received > 0:
            stock.stock_in(
                db,
                line.product_id,
                godown_id,
                line.qty_received,
                line.landed_cost,
                stock.Ref("purchase", "purchase", purchase.id),
                received_date,
                user_id,
            )
    return purchase


def cancel_purchase(
    db: Session, purchase: Purchase, reason: str, on: date, user_id: int | None = None
) -> Purchase:
    if purchase.status == "cancelled":
        raise PurchaseError("This purchase is already cancelled")
    for line in purchase.lines:
        if line.qty_received > 0:
            stock.reverse_in(
                db,
                line.product_id,
                purchase.godown_id,
                line.qty_received,
                line.landed_cost,
                stock.Ref("purchase_cancel", "purchase", purchase.id, reason),
                on,
                user_id,
                product_name=line.product.name,
            )
    purchase.status = "cancelled"
    purchase.cancel_reason = reason
    return purchase
