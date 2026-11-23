from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.gst import STATE_CODES, validate_gstin

PartyKind = Literal["customer", "supplier", "both"]


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- Brands ----------------------------------------------------------------
class BrandIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class BrandUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    is_active: bool | None = None


class BrandOut(_Out):
    id: int
    name: str
    is_active: bool


# ---- Products --------------------------------------------------------------
class ProductIn(BaseModel):
    brand_id: int
    grade: str = Field(min_length=1, max_length=30)
    bag_kg: Decimal = Field(default=Decimal("50"), gt=0, max_digits=6, decimal_places=2)
    hsn_code: str = Field(default="2523", pattern=r"^\d{4,8}$")
    reorder_level: int = Field(default=0, ge=0)


class ProductUpdate(BaseModel):
    grade: str | None = Field(default=None, min_length=1, max_length=30)
    bag_kg: Decimal | None = Field(default=None, gt=0, max_digits=6, decimal_places=2)
    hsn_code: str | None = Field(default=None, pattern=r"^\d{4,8}$")
    reorder_level: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ProductOut(_Out):
    id: int
    brand_id: int
    brand_name: str
    name: str
    grade: str
    bag_kg: Decimal
    hsn_code: str
    reorder_level: int
    is_active: bool


# ---- Godowns ---------------------------------------------------------------
class GodownIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    address: str | None = None


class GodownUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    address: str | None = None
    is_active: bool | None = None


class GodownOut(_Out):
    id: int
    name: str
    address: str | None
    is_active: bool


# ---- Parties ---------------------------------------------------------------
def _clean_gstin(v: str | None) -> str | None:
    if v is None or not v.strip():
        return None
    return validate_gstin(v)


def _check_state(v: str | None) -> str | None:
    if v is not None and v not in STATE_CODES:
        raise ValueError("Unknown state code")
    return v


class PartyIn(BaseModel):
    kind: PartyKind = "customer"
    name: str = Field(min_length=1, max_length=120)
    phone: str | None = Field(default=None, pattern=r"^[0-9+\- ]{6,20}$")
    gstin: str | None = None
    state_code: str | None = None
    address: str | None = None
    area: str | None = Field(default=None, max_length=80)
    credit_limit: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    credit_days: int = Field(default=0, ge=0, le=365)
    notes: str | None = None

    _gstin = field_validator("gstin")(_clean_gstin)
    _state = field_validator("state_code")(_check_state)

    @model_validator(mode="after")
    def _state_from_gstin(self) -> "PartyIn":
        # The GSTIN's first two digits are the party's state; it wins over a typed value.
        if self.gstin:
            self.state_code = self.gstin[:2]
        return self


class PartyUpdate(BaseModel):
    kind: PartyKind | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = Field(default=None, pattern=r"^[0-9+\- ]{6,20}$")
    gstin: str | None = None
    state_code: str | None = None
    address: str | None = None
    area: str | None = Field(default=None, max_length=80)
    credit_limit: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    credit_days: int | None = Field(default=None, ge=0, le=365)
    notes: str | None = None
    is_active: bool | None = None

    _gstin = field_validator("gstin")(_clean_gstin)
    _state = field_validator("state_code")(_check_state)


class PartyOut(_Out):
    id: int
    kind: PartyKind
    name: str
    phone: str | None
    gstin: str | None
    state_code: str
    address: str | None
    area: str | None
    credit_limit: Decimal
    credit_days: int
    notes: str | None
    is_active: bool


# ---- GST rates -------------------------------------------------------------
class GstRateIn(BaseModel):
    hsn_code: str = Field(pattern=r"^\d{4,8}$")
    rate: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)
    effective_from: date


class GstRateOut(_Out):
    id: int
    hsn_code: str
    rate: Decimal
    effective_from: date


# ---- Prices ----------------------------------------------------------------
class PriceItem(BaseModel):
    product_id: int
    rate: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class PriceSetIn(BaseModel):
    """Set rates for one or more products from a date (defaults to today)."""

    effective_from: date | None = None
    party_id: int | None = None
    items: list[PriceItem] = Field(min_length=1)


class PriceOut(_Out):
    id: int
    product_id: int
    party_id: int | None
    rate: Decimal
    effective_from: date


class RateCardRow(BaseModel):
    product_id: int
    product_name: str
    hsn_code: str
    gst_rate: Decimal | None
    rate: Decimal | None
    effective_from: date | None
    previous_rate: Decimal | None


class QuoteOut(BaseModel):
    product_id: int
    party_id: int | None
    rate: Decimal
    source: Literal["party", "list"]
    effective_from: date
    gst_rate: Decimal
