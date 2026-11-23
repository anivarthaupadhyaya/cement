"""Sales billing: GST-inclusive bag rates -> GST invoice, stock out, credit control, returns.

Rates are quoted per bag *including* GST (how cement is sold). For each line:
    gross   = bags x rate                      (what the customer agreed to pay)
    taxable = gross x 100 / (100 + GST%)       rounded to paise
    gst     = gross - taxable                  (so taxable + gst == gross, exactly)
Delivery charges are taxed with the goods (composite supply) at the highest line rate.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    Party,
    Product,
    SalesInvoice,
    SalesLine,
    SalesReturn,
    SalesReturnLine,
    StockBalance,
)
from app.services import ledger, stock
from app.services.gst import is_interstate
from app.services.ledger import party_outstanding
from app.services.money import ZERO, q2, round_off, split_gst
from app.services.numbering import next_number
from app.services.pricing import gst_rate_on


class BillingError(Exception):
    pass


class CreditLimitExceeded(BillingError):
    pass


# ---- Pure maths -------------------------------------------------------------------
def split_inclusive(gross: Decimal, gst_rate: Decimal) -> tuple[Decimal, Decimal]:
    taxable = q2(gross * 100 / (100 + gst_rate))
    return taxable, gross - taxable


@dataclass(frozen=True)
class LineAmounts:
    gross: Decimal
    taxable: Decimal
    gst: Decimal


@dataclass(frozen=True)
class BillAmounts:
    lines: list[LineAmounts]
    delivery_taxable: Decimal
    delivery_gst: Decimal
    taxable_total: Decimal
    gst_total: Decimal
    round_off: Decimal
    grand_total: Decimal


def calc_bill(
    lines: list[tuple[int, Decimal, Decimal]], delivery_charge: Decimal = ZERO
) -> BillAmounts:
    """lines: (bags, GST-inclusive rate per bag, GST %). Pure, so it's property-tested."""
    calcs = []
    for qty, rate, gst_rate in lines:
        gross = q2(qty * rate)
        taxable, gst = split_inclusive(gross, gst_rate)
        calcs.append(LineAmounts(gross, taxable, gst))
    top_rate = max((r for _, _, r in lines), default=ZERO)
    d_taxable, d_gst = split_inclusive(q2(delivery_charge), top_rate)
    taxable_total = sum((c.taxable for c in calcs), ZERO) + d_taxable
    gst_total = sum((c.gst for c in calcs), ZERO) + d_gst
    ro = round_off(taxable_total + gst_total)
    return BillAmounts(
        calcs, d_taxable, d_gst, taxable_total, gst_total, ro, taxable_total + gst_total + ro
    )


def tax_split(gst_total: Decimal, interstate: bool) -> tuple[Decimal, Decimal, Decimal]:
    if interstate:
        return q2(ZERO), q2(ZERO), gst_total
    cgst, sgst = split_gst(gst_total)
    return cgst, sgst, q2(ZERO)


# ---- Preparing a bill (shared by preview and save) --------------------------------
@dataclass(frozen=True)
class BillLineIn:
    product_id: int
    qty: int
    rate: Decimal


@dataclass
class PreparedLine:
    product: Product
    qty: int
    rate: Decimal
    gst_rate: Decimal
    amounts: LineAmounts
    available: int
    avg_cost: Decimal

    @property
    def cost_total(self) -> Decimal:
        return q2(self.avg_cost * self.qty)

    @property
    def margin(self) -> Decimal:
        return self.amounts.taxable - self.cost_total

    @property
    def below_cost(self) -> bool:
        return self.avg_cost > 0 and self.amounts.taxable < self.cost_total


@dataclass
class PreparedBill:
    on: date
    party: Party | None
    customer_name: str
    place_of_supply: str
    interstate: bool
    payment_mode: str
    godown_id: int
    lines: list[PreparedLine]
    amounts: BillAmounts
    outstanding: Decimal | None
    credit_limit: Decimal | None
    warnings: list[str] = field(default_factory=list)

    @property
    def over_limit(self) -> bool:
        if self.payment_mode != "credit" or self.credit_limit is None or self.outstanding is None:
            return False
        return self.outstanding + self.amounts.grand_total > self.credit_limit

    @property
    def cost_total(self) -> Decimal:
        return sum((ln.cost_total for ln in self.lines), ZERO)

    @property
    def margin(self) -> Decimal:
        return self.amounts.taxable_total - self.amounts.delivery_taxable - self.cost_total


def prepare_bill(
    db: Session,
    *,
    on: date,
    party_id: int | None,
    customer_name: str | None,
    payment_mode: str,
    godown_id: int,
    lines: list[BillLineIn],
    delivery_charge: Decimal = ZERO,
) -> PreparedBill:
    if not lines:
        raise BillingError("Add at least one product")
    if len({ln.product_id for ln in lines}) != len(lines):
        raise BillingError("The same product is on two lines; put all its bags on one line")

    party = None
    if party_id is not None:
        party = db.get(Party, party_id)
        if party is None or not party.is_active or party.kind == "supplier":
            raise BillingError("Choose an active customer")
    if payment_mode == "credit" and party is None:
        raise BillingError("A credit bill needs a named customer")
    name = party.name if party else (customer_name or "").strip() or "Cash customer"
    pos = party.state_code if party else get_settings().shop_state_code

    prepared: list[PreparedLine] = []
    warnings: list[str] = []
    for ln in lines:
        product = db.get(Product, ln.product_id)
        if product is None or not product.is_active:
            raise BillingError(f"Unknown product {ln.product_id}")
        gst_rate = gst_rate_on(db, product.hsn_code, on)
        if gst_rate is None:
            raise BillingError(f"No GST rate for HSN {product.hsn_code} on {on}")
        bal = db.get(StockBalance, (product.id, godown_id))
        available = bal.qty if bal else 0
        avg_cost = bal.avg_cost if bal else ZERO
        if available < ln.qty:
            warnings.append(f"Only {available} bags of {product.name} in stock")
        prepared.append(
            PreparedLine(
                product,
                ln.qty,
                ln.rate,
                gst_rate,
                LineAmounts(ZERO, ZERO, ZERO),
                available,
                avg_cost,
            )
        )

    amounts = calc_bill([(p.qty, p.rate, p.gst_rate) for p in prepared], delivery_charge)
    for p, a in zip(prepared, amounts.lines, strict=True):
        p.amounts = a
        if p.below_cost:
            warnings.append(f"{p.product.name} is being sold below cost")

    outstanding = party_outstanding(db, party.id) if party else None
    bill = PreparedBill(
        on=on,
        party=party,
        customer_name=name,
        place_of_supply=pos,
        interstate=is_interstate(get_settings().shop_state_code, pos),
        payment_mode=payment_mode,
        godown_id=godown_id,
        lines=prepared,
        amounts=amounts,
        outstanding=outstanding,
        credit_limit=party.credit_limit if party else None,
        warnings=warnings,
    )
    if bill.over_limit:
        warnings.append("This bill takes the customer over their credit limit")
    if party is not None:
        from app.services.receipts import bounce_count  # local: receipts imports ledger too

        bounced = bounce_count(db, party.id)
        if bounced:
            warnings.append(f"{bounced} cheque(s) from this customer bounced before")
    return bill


# ---- Saving -------------------------------------------------------------------------
def create_invoice(
    db: Session,
    bill: PreparedBill,
    *,
    client_ref: str,
    is_owner: bool,
    user_id: int | None,
    customer_phone: str | None = None,
    vehicle_no: str | None = None,
    delivery_address: str | None = None,
    credit_override_reason: str | None = None,
    notes: str | None = None,
) -> SalesInvoice:
    if bill.over_limit:
        if not is_owner:
            raise CreditLimitExceeded("Over the credit limit: the owner has to approve this bill")
        if not (credit_override_reason or "").strip():
            raise CreditLimitExceeded("Give a reason for going over the credit limit")
    if not is_owner and any(ln.below_cost for ln in bill.lines):
        raise BillingError("Rate is below cost; only the owner can bill at this rate")

    settings = get_settings()
    invoice_no = next_number(db, "INV", settings.invoice_prefix, bill.on)
    cgst, sgst, igst = tax_split(bill.amounts.gst_total, bill.interstate)
    party = bill.party
    invoice = SalesInvoice(
        invoice_no=invoice_no,
        invoice_date=bill.on,
        client_ref=client_ref,
        party_id=party.id if party else None,
        customer_name=bill.customer_name,
        customer_phone=(party.phone if party else None) or customer_phone,
        customer_gstin=party.gstin if party else None,
        customer_address=party.address if party else None,
        place_of_supply=bill.place_of_supply,
        is_interstate=bill.interstate,
        payment_mode=bill.payment_mode,
        godown_id=bill.godown_id,
        vehicle_no=vehicle_no,
        delivery_address=delivery_address,
        delivery_charge=bill.amounts.delivery_taxable + bill.amounts.delivery_gst,
        delivery_taxable=bill.amounts.delivery_taxable,
        delivery_gst=bill.amounts.delivery_gst,
        taxable_total=bill.amounts.taxable_total,
        cgst_total=cgst,
        sgst_total=sgst,
        igst_total=igst,
        round_off=bill.amounts.round_off,
        grand_total=bill.amounts.grand_total,
        cost_total=q2(ZERO),
        credit_override_reason=credit_override_reason if bill.over_limit else None,
        notes=notes,
        created_by=user_id,
    )
    db.add(invoice)
    db.flush()

    cost_total = ZERO
    for ln in bill.lines:
        mv = stock.stock_out(
            db,
            ln.product.id,
            bill.godown_id,
            ln.qty,
            stock.Ref("sale", "sales_invoice", invoice.id),
            bill.on,
            user_id,
            product_name=ln.product.name,
        )
        cost_total += q2(mv.unit_cost * ln.qty)
        invoice.lines.append(
            SalesLine(
                product_id=ln.product.id,
                product_name=ln.product.name,
                hsn_code=ln.product.hsn_code,
                qty=ln.qty,
                rate=ln.rate,
                gst_rate=ln.gst_rate,
                taxable=ln.amounts.taxable,
                gst_amount=ln.amounts.gst,
                cost_per_bag=mv.unit_cost,
            )
        )
    invoice.cost_total = cost_total
    db.flush()
    if invoice.payment_mode == "credit":
        ledger.on_credit_invoice(db, invoice, user_id)
    return invoice


def find_by_client_ref(db: Session, client_ref: str) -> SalesInvoice | None:
    return db.scalar(select(SalesInvoice).where(SalesInvoice.client_ref == client_ref))


def cancel_invoice(
    db: Session, invoice: SalesInvoice, reason: str, user_id: int | None
) -> SalesInvoice:
    if invoice.status == "cancelled":
        raise BillingError("This bill is already cancelled")
    today = date.today()
    for line in invoice.lines:
        remaining = line.qty - line.qty_returned
        if remaining > 0:
            stock.stock_in(
                db,
                line.product_id,
                invoice.godown_id,
                remaining,
                line.cost_per_bag,
                stock.Ref("sale_cancel", "sales_invoice", invoice.id, reason),
                today,
                user_id,
            )
    invoice.status = "cancelled"
    invoice.cancel_reason = reason
    invoice.cancelled_at = datetime.now(UTC)
    db.flush()
    if invoice.payment_mode == "credit":
        returned = sum((r.total for r in invoice.returns), ZERO)
        ledger.on_invoice_cancel(db, invoice, returned, today, user_id)
    return invoice


def create_return(
    db: Session,
    invoice: SalesInvoice,
    items: list[tuple[int, int]],
    reason: str,
    on: date,
    user_id: int | None,
) -> SalesReturn:
    """items: (sales_line_id, bags coming back). Issues a credit note and restocks at cost."""
    if invoice.status != "active":
        raise BillingError("Can't take a return on a cancelled bill")
    if on < invoice.invoice_date:
        raise BillingError("Return date is before the bill date")
    by_id = {ln.id: ln for ln in invoice.lines}
    if not items:
        raise BillingError("Choose the bags being returned")

    ret_lines: list[SalesReturnLine] = []
    for line_id, qty in items:
        line = by_id.get(line_id)
        if line is None:
            raise BillingError("That product isn't on this bill")
        remaining = line.qty - line.qty_returned
        if qty <= 0 or qty > remaining:
            raise BillingError(f"{line.product_name}: only {remaining} bag(s) can be returned")
        if qty == remaining:
            # Last bags back: take exactly what's left so totals never drift by a paisa.
            prior = [rl for r in invoice.returns for rl in r.lines if rl.sales_line_id == line.id]
            taxable = line.taxable - sum((rl.taxable for rl in prior), ZERO)
            gst = line.gst_amount - sum((rl.gst_amount for rl in prior), ZERO)
        else:
            taxable = q2(line.taxable * qty / line.qty)
            gst = q2(line.gst_amount * qty / line.qty)
        ret_lines.append(
            SalesReturnLine(sales_line_id=line.id, qty=qty, taxable=taxable, gst_amount=gst)
        )
        line.qty_returned += qty

    taxable_total = sum((rl.taxable for rl in ret_lines), ZERO)
    gst_total = sum((rl.gst_amount for rl in ret_lines), ZERO)
    cgst, sgst, igst = tax_split(gst_total, invoice.is_interstate)
    ro = round_off(taxable_total + gst_total)
    ret = SalesReturn(
        return_no=next_number(db, "CN", get_settings().credit_note_prefix, on),
        invoice_id=invoice.id,
        return_date=on,
        reason=reason,
        taxable_total=taxable_total,
        cgst_total=cgst,
        sgst_total=sgst,
        igst_total=igst,
        round_off=ro,
        total=taxable_total + gst_total + ro,
        created_by=user_id,
        lines=ret_lines,
    )
    db.add(ret)
    db.flush()
    for rl in ret_lines:
        line = by_id[rl.sales_line_id]
        stock.stock_in(
            db,
            line.product_id,
            invoice.godown_id,
            rl.qty,
            line.cost_per_bag,
            stock.Ref("sale_return", "sales_return", ret.id, reason),
            on,
            user_id,
        )
    if invoice.payment_mode == "credit":
        db.refresh(invoice, ["returns"])
        ledger.on_credit_note(db, invoice, ret, user_id)
    return ret
