from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.config import get_settings
from app.core.db import get_db
from app.models import Brand, Godown, GstRate, Party, Product, Role, User
from app.schemas.masters import (
    BrandIn,
    BrandOut,
    BrandUpdate,
    GodownIn,
    GodownOut,
    GodownUpdate,
    GstRateIn,
    GstRateOut,
    PartyIn,
    PartyOut,
    PartyUpdate,
    ProductIn,
    ProductOut,
    ProductUpdate,
)

router = APIRouter(prefix="/api", tags=["masters"])

editors = require_roles(Role.OWNER, Role.ACCOUNTANT)
party_editors = require_roles(Role.OWNER, Role.ACCOUNTANT, Role.BILLING)


def _commit(db: Session, conflict_msg: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, conflict_msg) from exc


def _apply(obj: Any, body: BaseModel) -> None:
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)


def _get(db: Session, model: Any, obj_id: int, label: str) -> Any:
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} not found")
    return obj


# ---- Brands ----------------------------------------------------------------
@router.get("/brands", response_model=list[BrandOut])
def list_brands(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> Any:
    return db.scalars(select(Brand).order_by(Brand.name)).all()


@router.post("/brands", response_model=BrandOut, status_code=201)
def create_brand(body: BrandIn, db: Session = Depends(get_db), _: User = Depends(editors)) -> Any:
    brand = Brand(name=body.name.strip())
    db.add(brand)
    _commit(db, "A brand with this name already exists")
    return brand


@router.patch("/brands/{brand_id}", response_model=BrandOut)
def update_brand(
    brand_id: int, body: BrandUpdate, db: Session = Depends(get_db), _: User = Depends(editors)
) -> Any:
    brand = _get(db, Brand, brand_id, "Brand")
    _apply(brand, body)
    _commit(db, "A brand with this name already exists")
    return brand


# ---- Products --------------------------------------------------------------
@router.get("/products", response_model=list[ProductOut])
def list_products(
    active: bool | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Any:
    q = select(Product).join(Brand).order_by(Brand.name, Product.grade, Product.bag_kg)
    if active is not None:
        q = q.where(Product.is_active == active)
    return db.scalars(q).all()


@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(
    body: ProductIn, db: Session = Depends(get_db), _: User = Depends(editors)
) -> Any:
    _get(db, Brand, body.brand_id, "Brand")
    product = Product(**body.model_dump())
    db.add(product)
    _commit(db, "This brand already has a product with that grade and bag size")
    db.refresh(product)
    return product


@router.patch("/products/{product_id}", response_model=ProductOut)
def update_product(
    product_id: int, body: ProductUpdate, db: Session = Depends(get_db), _: User = Depends(editors)
) -> Any:
    product = _get(db, Product, product_id, "Product")
    _apply(product, body)
    _commit(db, "This brand already has a product with that grade and bag size")
    return product


# ---- Godowns ---------------------------------------------------------------
@router.get("/godowns", response_model=list[GodownOut])
def list_godowns(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> Any:
    return db.scalars(select(Godown).order_by(Godown.id)).all()


@router.post("/godowns", response_model=GodownOut, status_code=201)
def create_godown(body: GodownIn, db: Session = Depends(get_db), _: User = Depends(editors)) -> Any:
    godown = Godown(**body.model_dump())
    db.add(godown)
    _commit(db, "A godown with this name already exists")
    return godown


@router.patch("/godowns/{godown_id}", response_model=GodownOut)
def update_godown(
    godown_id: int, body: GodownUpdate, db: Session = Depends(get_db), _: User = Depends(editors)
) -> Any:
    godown = _get(db, Godown, godown_id, "Godown")
    _apply(godown, body)
    _commit(db, "A godown with this name already exists")
    return godown


# ---- Parties ---------------------------------------------------------------
def _guard_credit_terms(user: User, limit: Decimal | None, days: int | None) -> None:
    """Only the owner decides who gets credit; others can create cash customers."""
    if user.role == Role.OWNER.value:
        return
    if (limit is not None and limit > 0) or (days is not None and days > 0):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can set credit terms")


@router.get("/parties", response_model=list[PartyOut])
def list_parties(
    q: str | None = Query(default=None, max_length=80),
    kind: str | None = Query(default=None, pattern="^(customer|supplier)$"),
    active: bool | None = None,
    limit: int = Query(default=200, le=1000),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Any:
    stmt = select(Party).order_by(Party.name).limit(limit)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(Party.name.ilike(like), Party.phone.ilike(like), Party.gstin.ilike(like))
        )
    if kind:
        stmt = stmt.where(Party.kind.in_([kind, "both"]))
    if active is not None:
        stmt = stmt.where(Party.is_active == active)
    return db.scalars(stmt).all()


@router.get("/parties/{party_id}", response_model=PartyOut)
def get_party(
    party_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> Any:
    return _get(db, Party, party_id, "Party")


@router.post("/parties", response_model=PartyOut, status_code=201)
def create_party(
    body: PartyIn, db: Session = Depends(get_db), user: User = Depends(party_editors)
) -> Any:
    _guard_credit_terms(user, body.credit_limit, body.credit_days)
    data = body.model_dump()
    data["state_code"] = data["state_code"] or get_settings().shop_state_code
    party = Party(**data)
    db.add(party)
    _commit(db, "Another party already has this GSTIN")
    return party


@router.patch("/parties/{party_id}", response_model=PartyOut)
def update_party(
    party_id: int,
    body: PartyUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(party_editors),
) -> Any:
    _guard_credit_terms(user, body.credit_limit, body.credit_days)
    party = _get(db, Party, party_id, "Party")
    _apply(party, body)
    if body.gstin:
        party.state_code = body.gstin[:2]
    _commit(db, "Another party already has this GSTIN")
    return party


# ---- GST rates -------------------------------------------------------------
@router.get("/gst-rates", response_model=list[GstRateOut])
def list_gst_rates(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> Any:
    return db.scalars(
        select(GstRate).order_by(GstRate.hsn_code, GstRate.effective_from.desc())
    ).all()


@router.post("/gst-rates", response_model=GstRateOut, status_code=201)
def add_gst_rate(body: GstRateIn, db: Session = Depends(get_db), _: User = Depends(editors)) -> Any:
    """Rates are never edited: a change in law is a new row from its effective date."""
    rate = GstRate(**body.model_dump())
    db.add(rate)
    _commit(db, "A rate for this HSN code already starts on that date")
    return rate
