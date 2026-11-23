"""Expenses and the daily cash drawer.

Every rupee is counted on the day it physically moved:
  in : cash bills (on the bill date, even if cancelled later), cash receipts (receipt date)
  out: cash expenses, refunds for returns on cash bills (return date), refunds for cash bills
       cancelled (cancel date), cash receipts cancelled (cancel date)
So once a day is closed its figures never change, and a refund made today hits today's drawer.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from app.models import (
    CashClosing,
    Expense,
    PartyLedger,
    Receipt,
    SalesInvoice,
    SalesReturn,
)
from app.services.money import ZERO, q2


class CashError(Exception):
    pass


# ---- Day lock -----------------------------------------------------------------------
def last_closed_date(db: Session) -> date | None:
    return db.scalar(select(func.max(CashClosing.closing_date)))


def ensure_open(db: Session, on: date, what: str = "cash entries") -> None:
    closed = last_closed_date(db)
    if closed is not None and on <= closed:
        raise CashError(
            f"Cash for {closed:%d %b %Y} is already closed; {what} can't be dated on or before it"
        )


# ---- Expenses ---------------------------------------------------------------------------
def create_expense(
    db: Session,
    *,
    on: date,
    category: str,
    amount: Decimal,
    mode: str,
    paid_to: str | None,
    notes: str | None,
    user_id: int | None,
) -> Expense:
    if mode == "cash":
        ensure_open(db, on, "cash expenses")
    exp = Expense(
        expense_date=on,
        category=category,
        amount=q2(amount),
        mode=mode,
        paid_to=paid_to,
        notes=notes,
        created_by=user_id,
    )
    db.add(exp)
    db.flush()
    return exp


def cancel_expense(db: Session, exp: Expense, reason: str) -> Expense:
    if exp.status == "cancelled":
        raise CashError("This expense is already cancelled")
    if exp.mode == "cash":
        ensure_open(db, exp.expense_date, "a cash expense")
    exp.status = "cancelled"
    exp.cancel_reason = reason
    db.flush()
    return exp


# ---- Day summary ----------------------------------------------------------------------------
@dataclass
class DaySummary:
    on: date
    opening: Decimal
    opening_known: bool  # False before the very first closing: owner enters it
    cash_sales: Decimal = ZERO
    cash_receipts: Decimal = ZERO
    expenses: dict[str, Decimal] = field(default_factory=dict)
    return_refunds: Decimal = ZERO
    cancel_refunds: Decimal = ZERO
    receipt_reversals: Decimal = ZERO
    closing: CashClosing | None = None

    @property
    def cash_in(self) -> Decimal:
        return self.cash_sales + self.cash_receipts

    @property
    def cash_out(self) -> Decimal:
        return (
            sum(self.expenses.values(), ZERO)
            + self.return_refunds
            + self.cancel_refunds
            + self.receipt_reversals
        )

    @property
    def net(self) -> Decimal:
        return self.cash_in - self.cash_out

    @property
    def expected(self) -> Decimal:
        return self.opening + self.net


def _sum(db: Session, stmt: object) -> Decimal:
    return q2(Decimal(str(db.scalar(stmt) or 0)))  # type: ignore[call-overload]


def _flows(db: Session, on: date) -> DaySummary:
    s = DaySummary(on=on, opening=ZERO, opening_known=True)
    s.cash_sales = _sum(
        db,
        select(func.sum(SalesInvoice.grand_total)).where(
            SalesInvoice.payment_mode == "cash", SalesInvoice.invoice_date == on
        ),
    )
    s.cash_receipts = _sum(
        db,
        select(func.sum(Receipt.amount)).where(Receipt.mode == "cash", Receipt.receipt_date == on),
    )
    for cat, total in db.execute(
        select(Expense.category, func.sum(Expense.amount))
        .where(Expense.mode == "cash", Expense.status == "active", Expense.expense_date == on)
        .group_by(Expense.category)
    ):
        s.expenses[cat] = q2(Decimal(str(total)))
    s.return_refunds = _sum(
        db,
        select(func.sum(SalesReturn.total))
        .join(SalesInvoice, SalesInvoice.id == SalesReturn.invoice_id)
        .where(SalesInvoice.payment_mode == "cash", SalesReturn.return_date == on),
    )
    # Cash bill cancelled on this day: refund what hadn't already been refunded as returns.
    returned = (
        select(func.coalesce(func.sum(SalesReturn.total), 0))
        .where(SalesReturn.invoice_id == SalesInvoice.id)
        .scalar_subquery()
    )
    s.cancel_refunds = _sum(
        db,
        select(func.sum(SalesInvoice.grand_total - returned)).where(
            SalesInvoice.payment_mode == "cash",
            SalesInvoice.status == "cancelled",
            cast(func.timezone("Asia/Kolkata", SalesInvoice.cancelled_at), Date) == on,
        ),
    )
    s.receipt_reversals = _sum(
        db,
        select(func.sum(PartyLedger.debit))
        .join(Receipt, Receipt.id == PartyLedger.ref_id)
        .where(
            PartyLedger.kind == "receipt_cancel",
            PartyLedger.ref_type == "receipt",
            Receipt.mode == "cash",
            PartyLedger.entry_date == on,
        ),
    )
    return s


def day_summary(db: Session, on: date) -> DaySummary:
    """Opening = last counted cash + net of any unclosed days in between."""
    closing = db.scalar(select(CashClosing).where(CashClosing.closing_date == on))
    prev = db.scalar(
        select(CashClosing)
        .where(CashClosing.closing_date < on)
        .order_by(CashClosing.closing_date.desc())
        .limit(1)
    )
    s = _flows(db, on)
    s.closing = closing
    if closing is not None:
        s.opening = closing.opening_cash
    elif prev is None:
        s.opening_known = False
    else:
        opening = prev.counted
        d = prev.closing_date + timedelta(days=1)
        while d < on:
            opening += _flows(db, d).net
            d += timedelta(days=1)
        s.opening = opening
    return s


def close_day(
    db: Session,
    *,
    on: date,
    counted: Decimal,
    denominations: dict[str, int] | None,
    notes: str | None,
    opening_cash: Decimal | None,
    user_id: int | None,
    today: date,
) -> CashClosing:
    if on > today:
        raise CashError("Can't close a future day")
    if db.scalar(select(CashClosing.id).where(CashClosing.closing_date == on)):
        raise CashError("This day is already closed")
    last = last_closed_date(db)
    if last is not None and on < last:
        raise CashError(f"{last:%d %b %Y} is already closed; close days in order")
    s = day_summary(db, on)
    if not s.opening_known:
        if opening_cash is None:
            raise CashError("First closing: enter the cash that was in the drawer at the start")
        s.opening = q2(opening_cash)
    difference = q2(counted) - s.expected
    if difference != 0 and not (notes or "").strip():
        raise CashError("Counted cash doesn't match; add a note explaining the difference")
    closing = CashClosing(
        closing_date=on,
        opening_cash=s.opening,
        cash_in=s.cash_in,
        cash_out=s.cash_out,
        expected=s.expected,
        counted=q2(counted),
        difference=difference,
        denominations=denominations,
        notes=notes,
        closed_by=user_id,
    )
    db.add(closing)
    db.flush()
    return closing
