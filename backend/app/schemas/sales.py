from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

Money = Decimal


class SaleLineIn(BaseModel):
    product_id: int
    qty: int = Field(gt=0, le=100_000)
    rate: Money = Field(gt=0, max_digits=12, decimal_places=2)  # per bag incl. GST


class BillDraft(BaseModel):
    """What the billing screen sends for a live preview."""

    invoice_date: date | None = None
    party_id: int | None = None
    customer_name: str | None = Field(default=None, max_length=120)
    payment_mode: Literal["cash", "credit"] = "cash"
    godown_id: int = 1
    delivery_charge: Money = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    lines: list[SaleLineIn] = Field(min_length=1, max_length=30)


class SaleIn(BillDraft):
    client_ref: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9-]+$")
    customer_phone: str | None = Field(default=None, max_length=20)
    vehicle_no: str | None = Field(default=None, max_length=20)
    delivery_address: str | None = None
    credit_override_reason: str | None = Field(default=None, max_length=500)
    notes: str | None = None


class PreviewLine(BaseModel):
    product_id: int
    product_name: str
    qty: int
    rate: Money
    gst_rate: Decimal
    gross: Money
    taxable: Money
    gst_amount: Money
    available: int
    cost_per_bag: Decimal | None
    margin: Money | None
    below_cost: bool


class PreviewOut(BaseModel):
    customer_name: str
    place_of_supply: str
    is_interstate: bool
    lines: list[PreviewLine]
    delivery_taxable: Money
    delivery_gst: Money
    taxable_total: Money
    cgst_total: Money
    sgst_total: Money
    igst_total: Money
    round_off: Money
    grand_total: Money
    total_bags: int
    outstanding: Money | None
    credit_limit: Money | None
    over_limit: bool
    margin: Money | None
    warnings: list[str]


class SaleLineOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    hsn_code: str
    qty: int
    qty_returned: int
    rate: Money
    gst_rate: Decimal
    taxable: Money
    gst_amount: Money
    cost_per_bag: Decimal | None


class ReturnLineOut(BaseModel):
    sales_line_id: int
    product_name: str
    qty: int
    taxable: Money
    gst_amount: Money


class ReturnOut(BaseModel):
    id: int
    return_no: str
    return_date: date
    reason: str
    taxable_total: Money
    cgst_total: Money
    sgst_total: Money
    igst_total: Money
    round_off: Money
    total: Money
    lines: list[ReturnLineOut]


class SaleSummary(BaseModel):
    id: int
    invoice_no: str
    invoice_date: date
    customer_name: str
    party_id: int | None
    payment_mode: Literal["cash", "credit"]
    total_bags: int
    grand_total: Money
    status: Literal["active", "cancelled"]
    has_returns: bool


class SaleOut(SaleSummary):
    customer_phone: str | None
    customer_gstin: str | None
    customer_address: str | None
    place_of_supply: str
    is_interstate: bool
    godown_id: int
    godown_name: str
    vehicle_no: str | None
    delivery_address: str | None
    delivery_charge: Money
    delivery_taxable: Money
    delivery_gst: Money
    taxable_total: Money
    cgst_total: Money
    sgst_total: Money
    igst_total: Money
    round_off: Money
    amount_in_words: str
    cost_total: Money | None
    margin: Money | None
    credit_override_reason: str | None
    notes: str | None
    cancel_reason: str | None
    cancelled_at: datetime | None
    created_at: datetime
    lines: list[SaleLineOut]
    returns: list[ReturnOut]


class ReturnItemIn(BaseModel):
    sales_line_id: int
    qty: int = Field(gt=0)


class ReturnIn(BaseModel):
    return_date: date | None = None
    reason: str = Field(min_length=3, max_length=500)
    items: list[ReturnItemIn] = Field(min_length=1)


class ShopOut(BaseModel):
    name: str
    address: str
    gstin: str
    phone: str
    bank: str
    state_code: str
    state_name: str
