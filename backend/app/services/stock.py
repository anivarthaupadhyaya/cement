"""Stock engine: every change is a movement row plus an update of the cached balance.

Costing is weighted average per product per godown:
  * inward  -> avg = (qty*avg + in_qty*in_cost) / (qty + in_qty)
  * outward -> goes out at the current avg; avg unchanged
  * reversal of an inward (e.g. cancelled purchase) -> takes that exact cost back out

The balance row is locked (SELECT ... FOR UPDATE) for the whole transaction, so two clerks
saving at the same moment are serialised instead of overwriting each other's numbers.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, lazyload

from app.models import StockBalance, StockMovement
from app.services.money import ZERO, q4


class InsufficientStock(Exception):
    def __init__(self, product_name: str, available: int, wanted: int) -> None:
        self.available = available
        self.wanted = wanted
        super().__init__(f"Only {available} bag(s) of {product_name} in stock; {wanted} needed")


@dataclass(frozen=True)
class Ref:
    kind: str  # movement kind, e.g. "purchase"
    ref_type: str | None = None  # e.g. "purchase"
    ref_id: int | None = None
    note: str | None = None


def _locked_balance(db: Session, product_id: int, godown_id: int) -> StockBalance:
    # Write any pending changes first: the locked re-read below must not discard them.
    db.flush()
    # Make sure the row exists, then lock it.
    db.execute(
        insert(StockBalance)
        .values(product_id=product_id, godown_id=godown_id, qty=0, avg_cost=0)
        .on_conflict_do_nothing()
    )
    bal = db.scalar(
        select(StockBalance)
        .where(StockBalance.product_id == product_id, StockBalance.godown_id == godown_id)
        .options(lazyload("*"))  # no joins: lock exactly this one row
        .with_for_update(of=StockBalance)
        .execution_options(populate_existing=True)
    )
    assert bal is not None
    return bal


def _record(
    db: Session,
    product_id: int,
    godown_id: int,
    qty: int,
    unit_cost: Decimal,
    ref: Ref,
    on: date,
    user_id: int | None,
) -> StockMovement:
    mv = StockMovement(
        product_id=product_id,
        godown_id=godown_id,
        qty=qty,
        unit_cost=q4(unit_cost),
        kind=ref.kind,
        ref_type=ref.ref_type,
        ref_id=ref.ref_id,
        note=ref.note,
        movement_date=on,
        user_id=user_id,
    )
    db.add(mv)
    return mv


def stock_in(
    db: Session,
    product_id: int,
    godown_id: int,
    qty: int,
    unit_cost: Decimal,
    ref: Ref,
    on: date,
    user_id: int | None = None,
) -> StockMovement:
    if qty <= 0:
        raise ValueError("Inward quantity must be positive")
    if unit_cost < 0:
        raise ValueError("Cost can't be negative")
    bal = _locked_balance(db, product_id, godown_id)
    new_qty = bal.qty + qty
    bal.avg_cost = q4((bal.qty * bal.avg_cost + qty * unit_cost) / new_qty)
    bal.qty = new_qty
    return _record(db, product_id, godown_id, qty, unit_cost, ref, on, user_id)


def stock_out(
    db: Session,
    product_id: int,
    godown_id: int,
    qty: int,
    ref: Ref,
    on: date,
    user_id: int | None = None,
    product_name: str = "this product",
) -> StockMovement:
    """Take bags out at the current average cost. Never lets stock go negative."""
    if qty <= 0:
        raise ValueError("Outward quantity must be positive")
    bal = _locked_balance(db, product_id, godown_id)
    if bal.qty < qty:
        raise InsufficientStock(product_name, bal.qty, qty)
    cost = bal.avg_cost
    bal.qty -= qty
    if bal.qty == 0:
        bal.avg_cost = ZERO
    return _record(db, product_id, godown_id, -qty, cost, ref, on, user_id)


def reverse_in(
    db: Session,
    product_id: int,
    godown_id: int,
    qty: int,
    unit_cost: Decimal,
    ref: Ref,
    on: date,
    user_id: int | None = None,
    product_name: str = "this product",
) -> StockMovement:
    """Undo an earlier inward at its own cost (keeps the average honest)."""
    bal = _locked_balance(db, product_id, godown_id)
    if bal.qty < qty:
        raise InsufficientStock(product_name, bal.qty, qty)
    remaining = bal.qty - qty
    if remaining == 0:
        bal.avg_cost = ZERO
    else:
        bal.avg_cost = max(ZERO, q4((bal.qty * bal.avg_cost - qty * unit_cost) / remaining))
    bal.qty = remaining
    return _record(db, product_id, godown_id, -qty, unit_cost, ref, on, user_id)


def available(db: Session, product_id: int, godown_id: int) -> int:
    return (
        db.scalar(
            select(StockBalance.qty).where(
                StockBalance.product_id == product_id, StockBalance.godown_id == godown_id
            )
        )
        or 0
    )


def verify_balances(db: Session) -> list[tuple[int, int, int, int]]:
    """Compare cached balances with SUM(movements). Returns mismatches (should be empty)."""
    sums = dict(
        (
            (row.product_id, row.godown_id),
            int(row.total),
        )
        for row in db.execute(
            select(
                StockMovement.product_id,
                StockMovement.godown_id,
                func.sum(StockMovement.qty).label("total"),
            ).group_by(StockMovement.product_id, StockMovement.godown_id)
        )
    )
    cached = {(b.product_id, b.godown_id): b.qty for b in db.scalars(select(StockBalance))}
    keys = set(sums) | set(cached)
    return [
        (p, g, cached.get((p, g), 0), sums.get((p, g), 0))
        for p, g in sorted(keys)
        if cached.get((p, g), 0) != sums.get((p, g), 0)
    ]
