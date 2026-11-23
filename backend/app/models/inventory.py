from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin
from app.models.masters import Godown, Money, Party, Product

UnitCost = Numeric(12, 4)

MOVEMENT_KINDS = (
    "opening",
    "purchase",
    "purchase_cancel",
    "sale",
    "sale_return",
    "sale_cancel",
    "damage",
    "adjustment",
)


class StockMovement(Base):
    """Append-only record of every bag that moved. Stock = SUM(qty)."""

    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint("qty <> 0", name="ck_stock_movements_qty"),
        CheckConstraint(
            "kind IN (" + ",".join(f"'{k}'" for k in MOVEMENT_KINDS) + ")",
            name="ck_stock_movements_kind",
        ),
        Index("ix_stock_movements_product_godown", "product_id", "godown_id", "id"),
        Index("ix_stock_movements_ref", "ref_type", "ref_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    godown_id: Mapped[int] = mapped_column(ForeignKey("godowns.id"), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)  # bags; + in, - out
    unit_cost: Mapped[Decimal] = mapped_column(UnitCost, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    ref_type: Mapped[str | None] = mapped_column(String(20))
    ref_id: Mapped[int | None] = mapped_column(Integer)
    movement_date: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    product: Mapped[Product] = relationship(lazy="joined")
    godown: Mapped[Godown] = relationship(lazy="joined")


class StockBalance(Base):
    """Cached running balance + weighted average cost per product per godown.

    Always derivable from stock_movements (see services.stock.verify_balances).
    """

    __tablename__ = "stock_balances"
    __table_args__ = (
        CheckConstraint("qty >= 0", name="ck_stock_balances_non_negative"),
        CheckConstraint("avg_cost >= 0", name="ck_stock_balances_cost"),
    )

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), primary_key=True)
    godown_id: Mapped[int] = mapped_column(ForeignKey("godowns.id"), primary_key=True)
    qty: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    avg_cost: Mapped[Decimal] = mapped_column(UnitCost, nullable=False, server_default=text("0"))

    product: Mapped[Product] = relationship(lazy="joined")
    godown: Mapped[Godown] = relationship(lazy="joined")


class Purchase(TimestampMixin, Base):
    """A supplier's bill as received. Never edited: cancel (with a reason) and re-enter."""

    __tablename__ = "purchases"
    __table_args__ = (
        CheckConstraint("status IN ('active','cancelled')", name="ck_purchases_status"),
        CheckConstraint(
            "freight >= 0 AND unloading >= 0 AND other_charges >= 0", name="ck_purchases_charges"
        ),
        # The same supplier bill can't be entered twice (cancelled ones don't count).
        Index(
            "uq_purchases_supplier_invoice_active",
            "supplier_id",
            "supplier_invoice_no",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("parties.id"), nullable=False, index=True)
    supplier_invoice_no: Mapped[str] = mapped_column(String(40), nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    received_date: Mapped[date] = mapped_column(Date, nullable=False)
    godown_id: Mapped[int] = mapped_column(ForeignKey("godowns.id"), nullable=False)
    vehicle_no: Mapped[str | None] = mapped_column(String(20))
    lr_no: Mapped[str | None] = mapped_column(String(40))
    is_interstate: Mapped[bool] = mapped_column(nullable=False)

    freight: Mapped[Decimal] = mapped_column(Money, nullable=False, server_default=text("0"))
    unloading: Mapped[Decimal] = mapped_column(Money, nullable=False, server_default=text("0"))
    other_charges: Mapped[Decimal] = mapped_column(Money, nullable=False, server_default=text("0"))

    taxable_total: Mapped[Decimal] = mapped_column(Money, nullable=False)
    cgst_total: Mapped[Decimal] = mapped_column(Money, nullable=False)
    sgst_total: Mapped[Decimal] = mapped_column(Money, nullable=False)
    igst_total: Mapped[Decimal] = mapped_column(Money, nullable=False)
    round_off: Mapped[Decimal] = mapped_column(Money, nullable=False)
    invoice_total: Mapped[Decimal] = mapped_column(Money, nullable=False)

    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="active")
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    supplier: Mapped[Party] = relationship(lazy="joined")
    godown: Mapped[Godown] = relationship(lazy="joined")
    lines: Mapped[list["PurchaseLine"]] = relationship(
        back_populates="purchase", order_by="PurchaseLine.id", cascade="all, delete-orphan"
    )


class PurchaseLine(Base):
    __tablename__ = "purchase_lines"
    __table_args__ = (
        CheckConstraint("qty_invoiced > 0", name="ck_purchase_lines_qty"),
        CheckConstraint(
            "qty_received >= 0 AND qty_damaged >= 0 AND qty_received + qty_damaged <= qty_invoiced",
            name="ck_purchase_lines_received",
        ),
        CheckConstraint("rate > 0", name="ck_purchase_lines_rate"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_id: Mapped[int] = mapped_column(
        ForeignKey("purchases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    qty_invoiced: Mapped[int] = mapped_column(Integer, nullable=False)
    qty_received: Mapped[int] = mapped_column(Integer, nullable=False)  # good bags into stock
    qty_damaged: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    rate: Mapped[Decimal] = mapped_column(Money, nullable=False)  # per bag, before GST
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    taxable: Mapped[Decimal] = mapped_column(Money, nullable=False)
    gst_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    charges: Mapped[Decimal] = mapped_column(Money, nullable=False)  # share of freight etc.
    landed_cost: Mapped[Decimal] = mapped_column(UnitCost, nullable=False)  # per good bag

    purchase: Mapped[Purchase] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship(lazy="joined")

    @property
    def qty_short(self) -> int:
        return self.qty_invoiced - self.qty_received - self.qty_damaged
