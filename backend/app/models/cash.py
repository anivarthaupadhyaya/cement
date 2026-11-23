from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin
from app.models.masters import Money

EXPENSE_CATEGORIES = (
    "rent",
    "electricity",
    "salary",
    "hamali",
    "diesel",
    "transport",
    "maintenance",
    "supplier_payment",
    "bank_deposit",
    "owner_drawings",
    "misc",
)


class Expense(TimestampMixin, Base):
    """Money going out: shop expenses, and other cash leaving the drawer
    (bank deposits, supplier payments, owner drawings)."""

    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_expenses_amount"),
        CheckConstraint("mode IN ('cash','upi','bank')", name="ck_expenses_mode"),
        CheckConstraint("status IN ('active','cancelled')", name="ck_expenses_status"),
        CheckConstraint(
            "category IN (" + ",".join(f"'{c}'" for c in EXPENSE_CATEGORIES) + ")",
            name="ck_expenses_category",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    expense_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    mode: Mapped[str] = mapped_column(String(10), nullable=False)
    paid_to: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="active")
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class CashClosing(Base):
    """End-of-day cash count. Final once saved: later corrections land on the next day."""

    __tablename__ = "cash_closings"

    id: Mapped[int] = mapped_column(primary_key=True)
    closing_date: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    opening_cash: Mapped[Decimal] = mapped_column(Money, nullable=False)
    cash_in: Mapped[Decimal] = mapped_column(Money, nullable=False)
    cash_out: Mapped[Decimal] = mapped_column(Money, nullable=False)
    expected: Mapped[Decimal] = mapped_column(Money, nullable=False)
    counted: Mapped[Decimal] = mapped_column(Money, nullable=False)
    difference: Mapped[Decimal] = mapped_column(Money, nullable=False)
    denominations: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    notes: Mapped[str | None] = mapped_column(Text)
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    closed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
