from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Money = Decimal


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- Purchases ----------------------------------------------------------------
class PurchaseLineIn(BaseModel):
    product_id: int
    qty_invoiced: int = Field(gt=0, le=100_000)
    qty_received: int | None = Field(default=None, ge=0)  # defaults to billed - damaged
    qty_damaged: int = Field(default=0, ge=0)
    rate: Money = Field(gt=0, max_digits=12, decimal_places=2)  # per bag, before GST

    @model_validator(mode="after")
    def _received(self) -> "PurchaseLineIn":
        if self.qty_received is None:
            self.qty_received = self.qty_invoiced - self.qty_damaged
        if self.qty_received + self.qty_damaged > self.qty_invoiced:
            raise ValueError("Good + damaged bags can't be more than bags billed")
        if self.qty_received < 0:
            raise ValueError("More damaged bags than billed")
        return self


class PurchaseIn(BaseModel):
    supplier_id: int
    supplier_invoice_no: str = Field(min_length=1, max_length=40)
    invoice_date: date
    received_date: date | None = None
    godown_id: int
    vehicle_no: str | None = Field(default=None, max_length=20)
    lr_no: str | None = Field(default=None, max_length=40)
    freight: Money = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    unloading: Money = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    other_charges: Money = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    notes: str | None = None
    lines: list[PurchaseLineIn] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def _dates(self) -> "PurchaseIn":
        if self.received_date is None:
            self.received_date = self.invoice_date
        if self.received_date < self.invoice_date:
            raise ValueError("Goods can't arrive before the bill date")
        if self.invoice_date > date.today():
            raise ValueError("Bill date is in the future")
        return self


class PurchaseLineOut(_Out):
    id: int
    product_id: int
    product_name: str
    qty_invoiced: int
    qty_received: int
    qty_damaged: int
    qty_short: int
    rate: Money
    gst_rate: Decimal
    taxable: Money
    gst_amount: Money
    charges: Money
    landed_cost: Decimal


class PurchaseSummary(_Out):
    id: int
    supplier_id: int
    supplier_name: str
    supplier_invoice_no: str
    invoice_date: date
    received_date: date
    godown_name: str
    total_bags: int
    invoice_total: Money
    status: Literal["active", "cancelled"]


class PurchaseOut(PurchaseSummary):
    godown_id: int
    vehicle_no: str | None
    lr_no: str | None
    is_interstate: bool
    freight: Money
    unloading: Money
    other_charges: Money
    taxable_total: Money
    cgst_total: Money
    sgst_total: Money
    igst_total: Money
    round_off: Money
    notes: str | None
    cancel_reason: str | None
    created_at: datetime
    lines: list[PurchaseLineOut]


class CancelIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


# ---- Stock --------------------------------------------------------------------
class StockRow(BaseModel):
    product_id: int
    product_name: str
    godown_id: int
    godown_name: str
    qty: int
    reorder_level: int
    low: bool
    avg_cost: Decimal | None  # hidden from roles that shouldn't see cost
    value: Money | None


class MovementOut(BaseModel):
    id: int
    movement_date: date
    product_name: str
    godown_name: str
    qty: int
    kind: str
    ref_type: str | None
    ref_id: int | None
    note: str | None
    unit_cost: Decimal | None
    created_at: datetime


class AdjustmentIn(BaseModel):
    product_id: int
    godown_id: int
    kind: Literal["damage", "adjustment"]
    qty: int = Field(description="Bags: negative removes, positive adds (adjustment only)")
    reason: str = Field(min_length=3, max_length=500)
    on: date | None = None

    @model_validator(mode="after")
    def _sign(self) -> "AdjustmentIn":
        if self.qty == 0:
            raise ValueError("Quantity can't be zero")
        if self.kind == "damage" and self.qty > 0:
            raise ValueError("Damage removes bags; use a negative quantity")
        return self


class OpeningItem(BaseModel):
    product_id: int
    qty: int = Field(gt=0)
    unit_cost: Decimal = Field(ge=0, max_digits=12, decimal_places=4)


class OpeningIn(BaseModel):
    godown_id: int
    on: date
    items: list[OpeningItem] = Field(min_length=1)
