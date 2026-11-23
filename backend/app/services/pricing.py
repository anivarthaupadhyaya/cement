"""Effective-dated lookups: GST rate by HSN, and selling rate by product (+ optional party).

Rule for both: the row with the latest `effective_from` that is on or before the date wins.
A party-specific price beats the general rate card when both exist.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import GstRate, Price, Product


@dataclass(frozen=True)
class Quote:
    rate: Decimal
    source: str  # "party" | "list"
    effective_from: date


def gst_rate_on(db: Session, hsn_code: str, on: date) -> Decimal | None:
    return db.scalar(
        select(GstRate.rate)
        .where(GstRate.hsn_code == hsn_code, GstRate.effective_from <= on)
        .order_by(GstRate.effective_from.desc())
        .limit(1)
    )


def _latest_price(db: Session, product_id: int, party_id: int | None, on: date) -> Price | None:
    q = select(Price).where(Price.product_id == product_id, Price.effective_from <= on)
    q = q.where(Price.party_id.is_(None) if party_id is None else Price.party_id == party_id)
    return db.scalar(q.order_by(Price.effective_from.desc()).limit(1))


def quote(db: Session, product_id: int, party_id: int | None, on: date) -> Quote | None:
    if party_id is not None:
        special = _latest_price(db, product_id, party_id, on)
        if special is not None:
            return Quote(special.rate, "party", special.effective_from)
    general = _latest_price(db, product_id, None, on)
    if general is None:
        return None
    return Quote(general.rate, "list", general.effective_from)


def set_prices(
    db: Session,
    items: list[tuple[int, Decimal]],
    effective_from: date,
    party_id: int | None = None,
) -> list[Price]:
    """Create rate rows; re-setting the same product+date corrects that day's row instead."""
    out: list[Price] = []
    for product_id, rate in items:
        q = select(Price).where(
            Price.product_id == product_id, Price.effective_from == effective_from
        )
        q = q.where(Price.party_id.is_(None) if party_id is None else Price.party_id == party_id)
        row = db.scalar(q)
        if row is None:
            row = Price(
                product_id=product_id, party_id=party_id, rate=rate, effective_from=effective_from
            )
            db.add(row)
        else:
            row.rate = rate
        out.append(row)
    db.flush()
    return out


def rate_card(db: Session, on: date) -> list[dict[str, object]]:
    """Current general rate (and the one before it) for every active product."""
    products = db.scalars(
        select(Product).where(Product.is_active).order_by(Product.brand_id, Product.grade)
    ).all()
    rows: list[dict[str, object]] = []
    for p in products:
        history = db.scalars(
            select(Price)
            .where(Price.product_id == p.id, Price.party_id.is_(None), Price.effective_from <= on)
            .order_by(Price.effective_from.desc())
            .limit(2)
        ).all()
        current = history[0] if history else None
        previous = history[1] if len(history) > 1 else None
        rows.append(
            {
                "product_id": p.id,
                "product_name": p.name,
                "hsn_code": p.hsn_code,
                "gst_rate": gst_rate_on(db, p.hsn_code, on),
                "rate": current.rate if current else None,
                "effective_from": current.effective_from if current else None,
                "previous_rate": previous.rate if previous else None,
            }
        )
    return rows
