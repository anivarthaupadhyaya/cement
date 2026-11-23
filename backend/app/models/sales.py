from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin
from app.models.inventory import UnitCost
from app.models.masters import Godown, Money, Party, Product


class DocSeries(Base):
    """Next number per document type per financial year. Locked while a document is saved,
    so numbers are gap-free and never duplicated."""

    __tablename__ = "doc_series"
    __table_args__ = (UniqueConstraint("doc_type", "fy", name="uq_doc_series_type_fy"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    doc_type: Mapped[str] = mapped_column(String(10), nullable=False)
    fy: Mapped[str] = mapped_column(String(7), nullable=False)  # "2026-27"
    next_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))


class SalesInvoice(TimestampMixin, Base):
    __tablename__ = "sales_invoices"
    __table_args__ = (
        CheckConstraint("status IN ('active','cancelled')", name="ck_sales_status"),
        CheckConstraint("payment_mode IN ('cash','credit')", name="ck_sales_payment_mode"),
        CheckConstraint(
            "payment_mode = 'cash' OR party_id IS NOT NULL", name="ck_sales_credit_party"
        ),
        CheckConstraint("delivery_charge >= 0", name="ck_sales_delivery"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_no: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    client_ref: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    party_id: Mapped[int | None] = mapped_column(ForeignKey("parties.id"), index=True)
    # Snapshots: the bill must print the same forever, even if the party is edited later.
    customer_name: Mapped[str] = mapped_column(String(120), nullable=False)
    customer_phone: Mapped[str | None] = mapped_column(String(20))
    customer_gstin: Mapped[str | None] = mapped_column(String(15))
    customer_address: Mapped[str | None] = mapped_column(Text)
    place_of_supply: Mapped[str] = mapped_column(String(2), nullable=False)
    is_interstate: Mapped[bool] = mapped_column(nullable=False)

    payment_mode: Mapped[str] = mapped_column(String(10), nullable=False)
    godown_id: Mapped[int] = mapped_column(ForeignKey("godowns.id"), nullable=False)
    vehicle_no: Mapped[str | None] = mapped_column(String(20))
    delivery_address: Mapped[str | None] = mapped_column(Text)

    delivery_charge: Mapped[Decimal] = mapped_column(
        Money, nullable=False, server_default=text("0")
    )
    delivery_taxable: Mapped[Decimal] = mapped_column(
        Money, nullable=False, server_default=text("0")
    )
    delivery_gst: Mapped[Decimal] = mapped_column(Money, nullable=False, server_default=text("0"))

    taxable_total: Mapped[Decimal] = mapped_column(Money, nullable=False)
    cgst_total: Mapped[Decimal] = mapped_column(Money, nullable=False)
    sgst_total: Mapped[Decimal] = mapped_column(Money, nullable=False)
    igst_total: Mapped[Decimal] = mapped_column(Money, nullable=False)
    round_off: Mapped[Decimal] = mapped_column(Money, nullable=False)
    grand_total: Mapped[Decimal] = mapped_column(Money, nullable=False)
    cost_total: Mapped[Decimal] = mapped_column(Money, nullable=False)

    credit_override_reason: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="active")
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    party: Mapped[Party | None] = relationship(lazy="joined")
    godown: Mapped[Godown] = relationship(lazy="joined")
    lines: Mapped[list["SalesLine"]] = relationship(
        back_populates="invoice", order_by="SalesLine.id", cascade="all, delete-orphan"
    )
    returns: Mapped[list["SalesReturn"]] = relationship(
        back_populates="invoice", order_by="SalesReturn.id"
    )


class SalesLine(Base):
    __tablename__ = "sales_lines"
    __table_args__ = (
        CheckConstraint("qty > 0", name="ck_sales_lines_qty"),
        CheckConstraint("rate > 0", name="ck_sales_lines_rate"),
        CheckConstraint(
            "qty_returned >= 0 AND qty_returned <= qty", name="ck_sales_lines_returned"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("sales_invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    product_name: Mapped[str] = mapped_column(String(120), nullable=False)  # snapshot
    hsn_code: Mapped[str] = mapped_column(String(8), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    rate: Mapped[Decimal] = mapped_column(Money, nullable=False)  # per bag, GST inclusive
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    taxable: Mapped[Decimal] = mapped_column(Money, nullable=False)
    gst_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    cost_per_bag: Mapped[Decimal] = mapped_column(UnitCost, nullable=False)
    qty_returned: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    invoice: Mapped[SalesInvoice] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship(lazy="joined")


class SalesReturn(Base):
    """A credit note: bags coming back against an invoice."""

    __tablename__ = "sales_returns"

    id: Mapped[int] = mapped_column(primary_key=True)
    return_no: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("sales_invoices.id"), nullable=False, index=True
    )
    return_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    taxable_total: Mapped[Decimal] = mapped_column(Money, nullable=False)
    cgst_total: Mapped[Decimal] = mapped_column(Money, nullable=False)
    sgst_total: Mapped[Decimal] = mapped_column(Money, nullable=False)
    igst_total: Mapped[Decimal] = mapped_column(Money, nullable=False)
    round_off: Mapped[Decimal] = mapped_column(Money, nullable=False)
    total: Mapped[Decimal] = mapped_column(Money, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    invoice: Mapped[SalesInvoice] = relationship(back_populates="returns")
    lines: Mapped[list["SalesReturnLine"]] = relationship(
        back_populates="sales_return", order_by="SalesReturnLine.id", cascade="all, delete-orphan"
    )


class SalesReturnLine(Base):
    __tablename__ = "sales_return_lines"
    __table_args__ = (CheckConstraint("qty > 0", name="ck_sales_return_lines_qty"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    return_id: Mapped[int] = mapped_column(
        ForeignKey("sales_returns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sales_line_id: Mapped[int] = mapped_column(ForeignKey("sales_lines.id"), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    taxable: Mapped[Decimal] = mapped_column(Money, nullable=False)
    gst_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)

    sales_return: Mapped[SalesReturn] = relationship(back_populates="lines")
    sales_line: Mapped[SalesLine] = relationship(lazy="joined")
