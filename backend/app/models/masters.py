from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin

# Money is always NUMERIC + Decimal. 12,2 covers up to ₹99,99,99,99,999.99.
Money = Numeric(12, 2)


class Brand(TimestampMixin, Base):
    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true(), nullable=False)

    products: Mapped[list["Product"]] = relationship(back_populates="brand")


class Product(TimestampMixin, Base):
    """A sellable item, e.g. "UltraTech PPC 50 kg". Stock and prices are kept per bag."""

    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("brand_id", "grade", "bag_kg", name="uq_products_brand_grade_kg"),
        CheckConstraint("bag_kg > 0", name="ck_products_bag_kg"),
        CheckConstraint("reorder_level >= 0", name="ck_products_reorder"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    grade: Mapped[str] = mapped_column(String(30), nullable=False)  # OPC 43, OPC 53, PPC, PSC
    bag_kg: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), server_default=text("50"), nullable=False
    )
    hsn_code: Mapped[str] = mapped_column(String(8), server_default="2523", nullable=False)
    reorder_level: Mapped[int] = mapped_column(Integer, server_default=text("0"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true(), nullable=False)

    brand: Mapped[Brand] = relationship(back_populates="products", lazy="joined")

    @property
    def brand_name(self) -> str:
        return self.brand.name

    @property
    def name(self) -> str:
        kg = format(self.bag_kg.normalize(), "f")  # 50.00 -> "50", 42.50 -> "42.5"
        return f"{self.brand.name} {self.grade} ({kg} kg)"


class GstRate(TimestampMixin, Base):
    """GST % per HSN code, valid from a date (a rate change is a new row, never an edit)."""

    __tablename__ = "gst_rates"
    __table_args__ = (
        UniqueConstraint("hsn_code", "effective_from", name="uq_gst_rates_hsn_from"),
        CheckConstraint("rate >= 0 AND rate <= 100", name="ck_gst_rates_rate"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    hsn_code: Mapped[str] = mapped_column(String(8), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)


class Godown(TimestampMixin, Base):
    __tablename__ = "godowns"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true(), nullable=False)


class Party(TimestampMixin, Base):
    """A customer, a supplier, or both."""

    __tablename__ = "parties"
    __table_args__ = (
        CheckConstraint("kind IN ('customer','supplier','both')", name="ck_parties_kind"),
        CheckConstraint("credit_limit >= 0", name="ck_parties_credit_limit"),
        CheckConstraint("credit_days >= 0", name="ck_parties_credit_days"),
        CheckConstraint("gstin IS NULL OR length(gstin) = 15", name="ck_parties_gstin_len"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    gstin: Mapped[str | None] = mapped_column(String(15), unique=True)
    state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    area: Mapped[str | None] = mapped_column(String(80))  # route / locality, for collections
    credit_limit: Mapped[Decimal] = mapped_column(Money, server_default=text("0"), nullable=False)
    credit_days: Mapped[int] = mapped_column(Integer, server_default=text("0"), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true(), nullable=False)


class Price(TimestampMixin, Base):
    """Selling rate per bag, GST inclusive (how the shop quotes), valid from a date.

    party_id NULL = the general rate card; a row with party_id is a special rate for that party.
    """

    __tablename__ = "prices"
    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "party_id",
            "effective_from",
            name="uq_prices_product_party_from",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint("rate > 0", name="ck_prices_rate"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    party_id: Mapped[int | None] = mapped_column(ForeignKey("parties.id"), index=True)
    rate: Mapped[Decimal] = mapped_column(Money, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
