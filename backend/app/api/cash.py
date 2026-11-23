from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.db import get_db
from app.models import CashClosing, Expense, Role, User
from app.models.cash import EXPENSE_CATEGORIES
from app.schemas.inventory import CancelIn
from app.services import cash

router = APIRouter(prefix="/api", tags=["cash"])

staff = require_roles(Role.OWNER, Role.ACCOUNTANT, Role.BILLING)
accounts = require_roles(Role.OWNER, Role.ACCOUNTANT)
owner_only = require_roles(Role.OWNER)

Category = Literal[
    "rent", "electricity", "salary", "hamali", "diesel", "transport", "maintenance",
    "supplier_payment", "bank_deposit", "owner_drawings", "misc",
]  # fmt: skip
assert set(Category.__args__) == set(EXPENSE_CATEGORIES)  # type: ignore[attr-defined]

DENOMINATIONS = ("500", "200", "100", "50", "20", "10", "coins")


class ExpenseIn(BaseModel):
    expense_date: date | None = None
    category: Category
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    mode: Literal["cash", "upi", "bank"] = "cash"
    paid_to: str | None = Field(default=None, max_length=120)
    notes: str | None = None


class ExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    expense_date: date
    category: Category
    amount: Decimal
    mode: Literal["cash", "upi", "bank"]
    paid_to: str | None
    notes: str | None
    status: Literal["active", "cancelled"]
    cancel_reason: str | None
    created_at: datetime


class DayOut(BaseModel):
    on: date
    opening: Decimal
    opening_known: bool
    cash_sales: Decimal
    cash_receipts: Decimal
    cash_in: Decimal
    expenses: dict[str, Decimal]
    return_refunds: Decimal
    cancel_refunds: Decimal
    receipt_reversals: Decimal
    cash_out: Decimal
    expected: Decimal
    closed: bool
    counted: Decimal | None
    difference: Decimal | None
    last_closed: date | None


class CloseIn(BaseModel):
    on: date
    counted: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    denominations: dict[str, int] | None = None
    notes: str | None = Field(default=None, max_length=500)
    opening_cash: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)


class ClosingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    closing_date: date
    opening_cash: Decimal
    cash_in: Decimal
    cash_out: Decimal
    expected: Decimal
    counted: Decimal
    difference: Decimal
    denominations: dict[str, int] | None
    notes: str | None
    closed_at: datetime


# ---- Expenses ------------------------------------------------------------------------
@router.get("/expenses", response_model=list[ExpenseOut])
def list_expenses(
    date_from: date | None = None,
    date_to: date | None = None,
    category: Category | None = None,
    limit: int = Query(default=200, le=1000),
    db: Session = Depends(get_db),
    _: User = Depends(staff),
) -> Any:
    q = select(Expense).order_by(Expense.expense_date.desc(), Expense.id.desc()).limit(limit)
    if date_from:
        q = q.where(Expense.expense_date >= date_from)
    if date_to:
        q = q.where(Expense.expense_date <= date_to)
    if category:
        q = q.where(Expense.category == category)
    return db.scalars(q).all()


@router.post("/expenses", response_model=ExpenseOut, status_code=201)
def add_expense(body: ExpenseIn, db: Session = Depends(get_db), user: User = Depends(staff)) -> Any:
    today = date.today()
    on = body.expense_date or today
    if on > today:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Date is in the future")
    if on != today and user.role == Role.BILLING.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the office can back-date expenses")
    try:
        exp = cash.create_expense(
            db,
            on=on,
            category=body.category,
            amount=body.amount,
            mode=body.mode,
            paid_to=(body.paid_to or "").strip() or None,
            notes=body.notes,
            user_id=user.id,
        )
        db.commit()
    except cash.CashError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return exp


@router.post("/expenses/{expense_id}/cancel", response_model=ExpenseOut)
def cancel_expense(
    expense_id: int, body: CancelIn, db: Session = Depends(get_db), _: User = Depends(owner_only)
) -> Any:
    exp = db.get(Expense, expense_id)
    if exp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Expense not found")
    try:
        cash.cancel_expense(db, exp, body.reason)
        db.commit()
    except cash.CashError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return exp


# ---- Cash drawer ------------------------------------------------------------------------
def _day_out(db: Session, s: cash.DaySummary) -> dict[str, Any]:
    return {
        "on": s.on,
        "opening": s.opening,
        "opening_known": s.opening_known,
        "cash_sales": s.cash_sales,
        "cash_receipts": s.cash_receipts,
        "cash_in": s.cash_in,
        "expenses": s.expenses,
        "return_refunds": s.return_refunds,
        "cancel_refunds": s.cancel_refunds,
        "receipt_reversals": s.receipt_reversals,
        "cash_out": s.cash_out,
        "expected": s.expected,
        "closed": s.closing is not None,
        "counted": s.closing.counted if s.closing else None,
        "difference": s.closing.difference if s.closing else None,
        "last_closed": cash.last_closed_date(db),
    }


@router.get("/cash/day", response_model=DayOut)
def cash_day(
    on: date | None = None, db: Session = Depends(get_db), _: User = Depends(staff)
) -> Any:
    return _day_out(db, cash.day_summary(db, on or date.today()))


@router.post("/cash/close", response_model=DayOut, status_code=201)
def close_cash(body: CloseIn, db: Session = Depends(get_db), user: User = Depends(accounts)) -> Any:
    if body.denominations is not None:
        unknown = set(body.denominations) - set(DENOMINATIONS)
        if unknown or any(v < 0 for v in body.denominations.values()):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Bad denomination count")
    try:
        cash.close_day(
            db,
            on=body.on,
            counted=body.counted,
            denominations=body.denominations,
            notes=(body.notes or "").strip() or None,
            opening_cash=body.opening_cash,
            user_id=user.id,
            today=date.today(),
        )
        db.commit()
    except cash.CashError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _day_out(db, cash.day_summary(db, body.on))


@router.get("/cash/closings", response_model=list[ClosingOut])
def closings(
    limit: int = Query(default=30, le=366),
    db: Session = Depends(get_db),
    _: User = Depends(accounts),
) -> Any:
    return db.scalars(
        select(CashClosing).order_by(CashClosing.closing_date.desc()).limit(limit)
    ).all()
