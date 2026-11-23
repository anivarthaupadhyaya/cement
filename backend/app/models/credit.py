from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin
from app.models.masters import Money, Party

LEDGER_KINDS = (
    "opening",
    "invoice",
    "invoice_cancel",
    "credit_note",
    "receipt",
    "receipt_cancel",
    "cheque_bounce",
    "bounce_charge",
)


class PartyLedger(Base):
    """Append-only customer account. Balance (what they owe) = SUM(debit - credit)."""

    __tablename__ = "party_ledger"
    __table_args__ = (
        CheckConstraint(
            "(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)", name="ck_ledger_one_side"
        ),
        CheckConstraint(
            "kind IN (" + ",".join(f"'{k}'" for k in LEDGER_KINDS) + ")", name="ck_ledger_kind"
        ),
        Index("ix_party_ledger_party_date", "party_id", "entry_date", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    party_id: Mapped[int] = mapped_column(ForeignKey("parties.id"), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    ref_type: Mapped[str | None] = mapped_column(String(20))
    ref_id: Mapped[int | None] = mapped_column()
    ref_no: Mapped[str | None] = mapped_column(String(40))
    debit: Mapped[Decimal] = mapped_column(Money, nullable=False, server_default=text("0"))
    credit: Mapped[Decimal] = mapped_column(Money, nullable=False, server_default=text("0"))
    narration: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OtherDue(Base):
    """A due that isn't a sales bill: old udhaar from before go-live, or a cheque-bounce
    charge. Payments are allocated to these exactly like bills."""

    __tablename__ = "other_dues"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_other_dues_amount"),
        CheckConstraint("kind IN ('opening','bounce_charge')", name="ck_other_dues_kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    party_id: Mapped[int] = mapped_column(ForeignKey("parties.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(15), nullable=False)
    ref_no: Mapped[str] = mapped_column(String(40), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    party: Mapped[Party] = relationship(lazy="joined")


class Receipt(TimestampMixin, Base):
    __tablename__ = "receipts"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_receipts_amount"),
        CheckConstraint("mode IN ('cash','upi','bank','cheque')", name="ck_receipts_mode"),
        CheckConstraint("status IN ('active','cancelled')", name="ck_receipts_status"),
        CheckConstraint(
            "(mode = 'cheque') = (cheque_status IS NOT NULL)", name="ck_receipts_cheque_status"
        ),
        CheckConstraint(
            "cheque_status IS NULL OR "
            "cheque_status IN ('received','deposited','cleared','bounced')",
            name="ck_receipts_cheque_status_values",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_no: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    client_ref: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    party_id: Mapped[int] = mapped_column(ForeignKey("parties.id"), nullable=False, index=True)
    receipt_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(10), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    reference: Mapped[str | None] = mapped_column(String(60))  # UTR / UPI ref
    cheque_no: Mapped[str | None] = mapped_column(String(20))
    cheque_date: Mapped[date | None] = mapped_column(Date)
    bank_name: Mapped[str | None] = mapped_column(String(60))
    cheque_status: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="active")
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    party: Mapped[Party] = relationship(lazy="joined")
    allocations: Mapped[list["ReceiptAllocation"]] = relationship(
        back_populates="receipt", order_by="ReceiptAllocation.id"
    )

    @property
    def is_live(self) -> bool:
        """Money we actually hold: not cancelled and not a bounced cheque."""
        return self.status == "active" and self.cheque_status != "bounced"


class ReceiptAllocation(Base):
    """How much of a receipt settles which bill/due. Released (not deleted) when undone."""

    __tablename__ = "receipt_allocations"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_allocations_amount"),
        CheckConstraint(
            "(invoice_id IS NULL) <> (other_due_id IS NULL)", name="ck_allocations_one_target"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id"), nullable=False, index=True)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("sales_invoices.id"), index=True)
    other_due_id: Mapped[int | None] = mapped_column(ForeignKey("other_dues.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    receipt: Mapped[Receipt] = relationship(back_populates="allocations")
