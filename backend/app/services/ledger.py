"""Customer accounts: ledger postings, open bills, payment allocation, statements, ageing.

Two views of the same money that must always agree:
  * the ledger: append-only debits (bills, dues, bounces) and credits (payments, returns)
  * open items: each credit bill / other due with its unpaid balance, plus unallocated
    payment money ("advance")
Invariant (tested): ledger balance == SUM(open item balances) - advance.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    OtherDue,
    Party,
    PartyLedger,
    Receipt,
    ReceiptAllocation,
    SalesInvoice,
    SalesReturn,
)
from app.services.money import ZERO, q2


# ---- Posting ------------------------------------------------------------------------
def post(
    db: Session,
    party_id: int,
    on: date,
    kind: str,
    *,
    debit: Decimal = ZERO,
    credit: Decimal = ZERO,
    ref_type: str | None = None,
    ref_id: int | None = None,
    ref_no: str | None = None,
    narration: str | None = None,
    user_id: int | None = None,
) -> PartyLedger | None:
    if debit == 0 and credit == 0:
        return None
    entry = PartyLedger(
        party_id=party_id,
        entry_date=on,
        kind=kind,
        debit=q2(debit),
        credit=q2(credit),
        ref_type=ref_type,
        ref_id=ref_id,
        ref_no=ref_no,
        narration=narration,
        user_id=user_id,
    )
    db.add(entry)
    db.flush()
    return entry


def lock_party(db: Session, party_id: int) -> None:
    """Serialise money changes for one customer (two receipts can't grab the same bill)."""
    db.execute(select(Party.id).where(Party.id == party_id).with_for_update())


def party_balance(db: Session, party_id: int, before: date | None = None) -> Decimal:
    q = select(func.coalesce(func.sum(PartyLedger.debit - PartyLedger.credit), 0)).where(
        PartyLedger.party_id == party_id
    )
    if before is not None:
        q = q.where(PartyLedger.entry_date < before)
    return q2(Decimal(db.scalar(q) or 0))


def party_outstanding(db: Session, party_id: int) -> Decimal:
    """What the customer owes right now (negative = we hold an advance)."""
    return party_balance(db, party_id)


# ---- Open items -----------------------------------------------------------------------
@dataclass
class OpenItem:
    kind: str  # "invoice" | "due"
    id: int
    ref_no: str
    on: date
    amount: Decimal  # bill total less returns (or due amount)
    paid: Decimal

    @property
    def balance(self) -> Decimal:
        return self.amount - self.paid

    @property
    def key(self) -> tuple[str, int]:
        return (self.kind, self.id)


def _alloc_sums(db: Session, column: Any, ids: Iterable[int]) -> dict[int, Decimal]:
    """Active (unreleased) allocation totals grouped by bill / due / receipt id."""
    id_list = list(ids)
    if not id_list:
        return {}
    rows = db.execute(
        select(column, func.sum(ReceiptAllocation.amount))
        .where(column.in_(id_list), ReceiptAllocation.released_at.is_(None))
        .group_by(column)
    )
    return {int(k): Decimal(str(v)) for k, v in rows}


def invoice_items(
    db: Session, party_id: int | None = None, invoice_ids: list[int] | None = None
) -> list[OpenItem]:
    q = select(SalesInvoice).where(
        SalesInvoice.payment_mode == "credit", SalesInvoice.status == "active"
    )
    if party_id is not None:
        q = q.where(SalesInvoice.party_id == party_id)
    if invoice_ids is not None:
        q = q.where(SalesInvoice.id.in_(invoice_ids))
    invoices = db.scalars(q).unique().all()
    ids = [i.id for i in invoices]
    returned: dict[int, Decimal] = {}
    if ids:
        for inv_id, total in db.execute(
            select(SalesReturn.invoice_id, func.sum(SalesReturn.total))
            .where(SalesReturn.invoice_id.in_(ids))
            .group_by(SalesReturn.invoice_id)
        ):
            returned[int(inv_id)] = Decimal(str(total))
    paid = _alloc_sums(db, ReceiptAllocation.invoice_id, ids)
    return [
        OpenItem(
            "invoice",
            i.id,
            i.invoice_no,
            i.invoice_date,
            i.grand_total - returned.get(i.id, ZERO),
            paid.get(i.id, ZERO),
        )
        for i in invoices
    ]


def due_items(db: Session, party_id: int | None = None) -> list[OpenItem]:
    q = select(OtherDue)
    if party_id is not None:
        q = q.where(OtherDue.party_id == party_id)
    dues = db.scalars(q).unique().all()
    paid = _alloc_sums(db, ReceiptAllocation.other_due_id, [d.id for d in dues])
    return [
        OpenItem("due", d.id, d.ref_no, d.due_date, d.amount, paid.get(d.id, ZERO)) for d in dues
    ]


def open_items(db: Session, party_id: int) -> list[OpenItem]:
    """Unpaid bills and dues, oldest first (the order payments settle them)."""
    items = invoice_items(db, party_id) + due_items(db, party_id)
    return sorted((i for i in items if i.balance > 0), key=lambda i: (i.on, i.kind != "due", i.id))


def invoice_paid(db: Session, invoice_id: int) -> Decimal:
    return _alloc_sums(db, ReceiptAllocation.invoice_id, [invoice_id]).get(invoice_id, ZERO)


def unallocated(db: Session, party_id: int) -> list[tuple[Receipt, Decimal]]:
    """Live receipts with money not yet set against any bill, oldest first."""
    receipts = (
        db.scalars(
            select(Receipt)
            .where(Receipt.party_id == party_id, Receipt.status == "active")
            .order_by(Receipt.receipt_date, Receipt.id)
        )
        .unique()
        .all()
    )
    live = [r for r in receipts if r.is_live]
    used = _alloc_sums(db, ReceiptAllocation.receipt_id, [r.id for r in live])
    out = []
    for r in live:
        free = r.amount - used.get(r.id, ZERO)
        if free > 0:
            out.append((r, free))
    return out


def advance(db: Session, party_id: int) -> Decimal:
    return sum((free for _, free in unallocated(db, party_id)), ZERO)


# ---- Allocation -----------------------------------------------------------------------
def plan_fifo(items: list[OpenItem], amount: Decimal) -> list[tuple[OpenItem, Decimal]]:
    """Pure: split `amount` over items oldest first. Leftover is the caller's advance."""
    plan = []
    left = amount
    for item in items:
        if left <= 0:
            break
        take = min(left, item.balance)
        if take > 0:
            plan.append((item, take))
            left -= take
    return plan


def allocate(db: Session, receipt: Receipt, item: OpenItem, amount: Decimal) -> ReceiptAllocation:
    alloc = ReceiptAllocation(
        receipt_id=receipt.id,
        invoice_id=item.id if item.kind == "invoice" else None,
        other_due_id=item.id if item.kind == "due" else None,
        amount=q2(amount),
    )
    db.add(alloc)
    item.paid += amount
    return alloc


def allocate_fifo(db: Session, party_id: int) -> None:
    """Use every rupee of unallocated money to settle the oldest open items."""
    items = open_items(db, party_id)
    for receipt, free in unallocated(db, party_id):
        for item, take in plan_fifo([i for i in items if i.balance > 0], free):
            allocate(db, receipt, item, take)
    db.flush()


def _active_allocations(db: Session, **where: int) -> list[ReceiptAllocation]:
    q = select(ReceiptAllocation).where(ReceiptAllocation.released_at.is_(None))
    for col, val in where.items():
        q = q.where(getattr(ReceiptAllocation, col) == val)
    return list(db.scalars(q.order_by(ReceiptAllocation.id.desc())))


def release(
    db: Session, allocations: list[ReceiptAllocation], limit: Decimal | None = None
) -> Decimal:
    """Undo allocations (newest first), up to `limit`. A partly-kept allocation is split."""
    now = datetime.now(UTC)
    freed = ZERO
    for alloc in allocations:
        if limit is not None and freed >= limit:
            break
        alloc.released_at = now
        if limit is not None and freed + alloc.amount > limit:
            keep = alloc.amount - (limit - freed)
            db.add(
                ReceiptAllocation(
                    receipt_id=alloc.receipt_id,
                    invoice_id=alloc.invoice_id,
                    other_due_id=alloc.other_due_id,
                    amount=keep,
                )
            )
            freed = limit
        else:
            freed += alloc.amount
    db.flush()
    return freed


def release_invoice(db: Session, invoice_id: int, limit: Decimal | None = None) -> Decimal:
    return release(db, _active_allocations(db, invoice_id=invoice_id), limit)


def release_receipt(db: Session, receipt_id: int) -> Decimal:
    return release(db, _active_allocations(db, receipt_id=receipt_id))


# ---- Hooks used by billing ----------------------------------------------------------------
def on_credit_invoice(db: Session, invoice: SalesInvoice, user_id: int | None) -> None:
    assert invoice.party_id is not None
    lock_party(db, invoice.party_id)
    post(
        db,
        invoice.party_id,
        invoice.invoice_date,
        "invoice",
        debit=invoice.grand_total,
        ref_type="sales_invoice",
        ref_id=invoice.id,
        ref_no=invoice.invoice_no,
        narration="Credit bill",
        user_id=user_id,
    )
    allocate_fifo(db, invoice.party_id)  # an advance pays the new bill straight away


def on_invoice_cancel(
    db: Session, invoice: SalesInvoice, returned: Decimal, on: date, user_id: int | None
) -> None:
    assert invoice.party_id is not None
    lock_party(db, invoice.party_id)
    release_invoice(db, invoice.id)
    post(
        db,
        invoice.party_id,
        on,
        "invoice_cancel",
        credit=invoice.grand_total - returned,
        ref_type="sales_invoice",
        ref_id=invoice.id,
        ref_no=invoice.invoice_no,
        narration=f"Bill cancelled: {invoice.cancel_reason}",
        user_id=user_id,
    )
    allocate_fifo(db, invoice.party_id)  # money that paid it now settles other bills


def on_credit_note(
    db: Session, invoice: SalesInvoice, ret: SalesReturn, user_id: int | None
) -> None:
    assert invoice.party_id is not None
    lock_party(db, invoice.party_id)
    post(
        db,
        invoice.party_id,
        ret.return_date,
        "credit_note",
        credit=ret.total,
        ref_type="sales_return",
        ref_id=ret.id,
        ref_no=ret.return_no,
        narration=f"Goods returned against {invoice.invoice_no}",
        user_id=user_id,
    )
    # If the bill was already paid, the returned value becomes an advance.
    item = invoice_items(db, invoice_ids=[invoice.id])[0]
    if item.balance < 0:
        release_invoice(db, invoice.id, limit=-item.balance)
    allocate_fifo(db, invoice.party_id)


# ---- Statement & ageing ----------------------------------------------------------------------
@dataclass(frozen=True)
class StatementLine:
    id: int
    on: date
    kind: str
    ref_no: str | None
    narration: str | None
    debit: Decimal
    credit: Decimal
    balance: Decimal


def statement(
    db: Session, party_id: int, date_from: date, date_to: date
) -> tuple[Decimal, list[StatementLine], Decimal]:
    opening = party_balance(db, party_id, before=date_from)
    entries = db.scalars(
        select(PartyLedger)
        .where(
            PartyLedger.party_id == party_id,
            PartyLedger.entry_date >= date_from,
            PartyLedger.entry_date <= date_to,
        )
        .order_by(PartyLedger.entry_date, PartyLedger.id)
    ).all()
    running = opening
    lines = []
    for e in entries:
        running += e.debit - e.credit
        lines.append(
            StatementLine(
                e.id, e.entry_date, e.kind, e.ref_no, e.narration, e.debit, e.credit, running
            )
        )
    return opening, lines, running


BUCKETS = ("0-30", "31-60", "61-90", "90+")


def bucket(days: int) -> str:
    if days <= 30:
        return "0-30"
    if days <= 60:
        return "31-60"
    if days <= 90:
        return "61-90"
    return "90+"


def ageing(db: Session, as_of: date, area: str | None = None) -> list[dict[str, Any]]:
    """Outstanding per customer split by age of the unpaid bills."""
    q = select(Party).where(Party.kind != "supplier")
    if area:
        q = q.where(Party.area.ilike(area))
    rows: list[dict[str, Any]] = []
    for party in db.scalars(q.order_by(Party.name)):
        items = open_items(db, party.id)
        adv = advance(db, party.id)
        if not items and adv == 0:
            continue
        buckets = dict.fromkeys(BUCKETS, ZERO)
        overdue = ZERO
        oldest = 0
        for item in items:
            days = (as_of - item.on).days
            buckets[bucket(days)] += item.balance
            if days > party.credit_days:
                overdue += item.balance
            oldest = max(oldest, days)
        due = sum(buckets.values(), ZERO)
        rows.append(
            {
                "party_id": party.id,
                "party_name": party.name,
                "phone": party.phone,
                "area": party.area,
                "credit_limit": party.credit_limit,
                "credit_days": party.credit_days,
                "buckets": buckets,
                "due": due,
                "advance": adv,
                "net": due - adv,
                "overdue": overdue,
                "oldest_days": oldest,
                "open_bills": len(items),
            }
        )
    return rows


def check_party(db: Session, party_id: int) -> tuple[Decimal, Decimal]:
    """(ledger balance, open items - advance). They must be equal."""
    items = invoice_items(db, party_id) + due_items(db, party_id)
    open_total = sum((i.balance for i in items), ZERO)
    return party_balance(db, party_id), open_total - advance(db, party_id)
