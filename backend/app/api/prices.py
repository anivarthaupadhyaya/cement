from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.db import get_db
from app.models import Party, Price, Product, Role, User
from app.schemas.masters import PriceOut, PriceSetIn, QuoteOut, RateCardRow
from app.services import pricing

router = APIRouter(prefix="/api/prices", tags=["prices"])
owner_only = require_roles(Role.OWNER)


@router.get("/card", response_model=list[RateCardRow])
def rate_card(
    on: date | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> Any:
    return pricing.rate_card(db, on or date.today())


@router.get("/quote", response_model=QuoteOut)
def quote(
    product_id: int,
    party_id: int | None = None,
    on: date | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Any:
    on = on or date.today()
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    q = pricing.quote(db, product_id, party_id, on)
    if q is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No rate set for this product yet")
    gst = pricing.gst_rate_on(db, product.hsn_code, on)
    if gst is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No GST rate for HSN {product.hsn_code}")
    return QuoteOut(
        product_id=product_id,
        party_id=party_id,
        rate=q.rate,
        source=q.source,
        effective_from=q.effective_from,
        gst_rate=gst,
    )


@router.get("/history", response_model=list[PriceOut])
def history(
    product_id: int,
    party_id: int | None = None,
    limit: int = Query(default=60, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Any:
    q = select(Price).where(Price.product_id == product_id)
    q = q.where(Price.party_id.is_(None) if party_id is None else Price.party_id == party_id)
    return db.scalars(q.order_by(Price.effective_from.desc()).limit(limit)).all()


@router.get("/special", response_model=list[PriceOut])
def special_rates(
    party_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> Any:
    """All special-rate rows for one party, newest first."""
    return db.scalars(
        select(Price).where(Price.party_id == party_id).order_by(Price.effective_from.desc())
    ).all()


@router.post("", response_model=list[PriceOut], status_code=201)
def set_prices(
    body: PriceSetIn, db: Session = Depends(get_db), _: User = Depends(owner_only)
) -> Any:
    ids = {i.product_id for i in body.items}
    if len(ids) != len(body.items):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A product appears twice")
    found = set(db.scalars(select(Product.id).where(Product.id.in_(ids))))
    if missing := ids - found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown product(s): {sorted(missing)}")
    if body.party_id is not None and db.get(Party, body.party_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Party not found")

    rows = pricing.set_prices(
        db,
        [(i.product_id, i.rate) for i in body.items],
        body.effective_from or date.today(),
        body.party_id,
    )
    db.commit()
    return rows
