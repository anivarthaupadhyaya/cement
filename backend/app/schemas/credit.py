from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Money = Decimal
PayMode = Literal["cash", "upi", "bank", "cheque"]


class AllocationIn(BaseModel):
    kind: Literal["invoice", "due"]
    id: int
    amount: Money = Field(gt=0, max_digits=12, decimal_places=2)


class ReceiptDraft(BaseModel):
    party_id: int
    amount: Money = Field(gt=0, max_digits=12, decimal_places=2)


class ReceiptIn(ReceiptDraft):
    client_ref: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9-]+$")
    receipt_date: date | None = None
    mode: PayMode
    reference: str | None = Field(default=None, max_length=60)
    cheque_no: str | None = Field(default=None, max_length=20)
    cheque_date: date | None = None
    bank_name: str | None = Field(default=None, max_length=60)
    notes: str | None = None
    allocations: list[AllocationIn] | None = None  # None = oldest bills first

    @model_validator(mode="after")
    def _cheque(self) -> "ReceiptIn":
        if self.mode == "cheque" and not (self.cheque_no or "").strip():
            raise ValueError("Enter the cheque number")
        return self


class OpenItemOut(BaseModel):
    kind: Literal["invoice", "due"]
    id: int
    ref_no: str
    date: date
    age_days: int
    amount: Money
    paid: Money
    balance: Money


class PlanLine(BaseModel):
    kind: Literal["invoice", "due"]
    id: int
    ref_no: str
    amount: Money


class ReceiptPreviewOut(BaseModel):
    outstanding: Money
    open_items: list[OpenItemOut]
    plan: list[PlanLine]
    advance_after: Money
    bounced_cheques: int


class AllocationOut(BaseModel):
    kind: Literal["invoice", "due"]
    id: int
    ref_no: str
    amount: Money


class ReceiptOut(BaseModel):
    id: int
    receipt_no: str
    receipt_date: date
    party_id: int
    party_name: str
    mode: PayMode
    amount: Money
    reference: str | None
    cheque_no: str | None
    cheque_date: date | None
    bank_name: str | None
    cheque_status: Literal["received", "deposited", "cleared", "bounced"] | None
    status: Literal["active", "cancelled"]
    cancel_reason: str | None
    notes: str | None
    allocated: Money
    unallocated: Money
    allocations: list[AllocationOut]
    balance_after: Money
    amount_in_words: str
    created_at: datetime


class ChequeActionIn(BaseModel):
    action: Literal["deposit", "clear", "bounce"]
    on: date | None = None
    charge: Money = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)


class OpeningDueIn(BaseModel):
    ref_no: str = Field(min_length=1, max_length=40)
    due_date: date
    amount: Money = Field(gt=0, max_digits=12, decimal_places=2)
    notes: str | None = None


class StatementLineOut(BaseModel):
    id: int
    date: date
    kind: str
    ref_no: str | None
    narration: str | None
    debit: Money
    credit: Money
    balance: Money


class StatementOut(BaseModel):
    party_id: int
    party_name: str
    phone: str | None
    date_from: date
    date_to: date
    opening: Money
    lines: list[StatementLineOut]
    closing: Money
    total_debit: Money
    total_credit: Money


class AgeingRow(BaseModel):
    party_id: int
    party_name: str
    phone: str | None
    area: str | None
    credit_limit: Money
    credit_days: int
    b0_30: Money
    b31_60: Money
    b61_90: Money
    b90_plus: Money
    due: Money
    advance: Money
    net: Money
    overdue: Money
    oldest_days: int
    open_bills: int


class AgeingOut(BaseModel):
    as_of: date
    rows: list[AgeingRow]
    totals: dict[str, Money]
