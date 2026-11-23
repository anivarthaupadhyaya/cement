from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.db import get_db
from app.models import Godown, Product, Role, StockBalance, StockMovement, User
from app.schemas.inventory import AdjustmentIn, MovementOut, OpeningIn, StockRow
from app.services import stock
from app.services.money import ZERO, q2

router = APIRouter(prefix="/api/stock", tags=["stock"])

stock_keepers = require_roles(Role.OWNER, Role.ACCOUNTANT, Role.GODOWN)
owner_only = require_roles(Role.OWNER)


def sees_cost(user: User) -> bool:
    return user.role in (Role.OWNER.value, Role.ACCOUNTANT.value)


@router.get("", response_model=list[StockRow])
def stock_summary(
    godown_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Any:
    """Every active product in every active godown (zero rows included, so gaps are visible)."""
    q = (
        select(Product, Godown, StockBalance.qty, StockBalance.avg_cost)
        .select_from(Product)
        .join(Godown, Godown.is_active.is_(True))
        .outerjoin(
            StockBalance,
            and_(StockBalance.product_id == Product.id, StockBalance.godown_id == Godown.id),
        )
        .where(Product.is_active.is_(True))
        .order_by(Godown.id, Product.brand_id, Product.grade)
    )
    if godown_id:
        q = q.where(Godown.id == godown_id)
    show_cost = sees_cost(user)
    rows = []
    for product, godown, bal_qty, bal_cost in db.execute(q).unique():
        qty = bal_qty or 0
        avg = bal_cost
        rows.append(
            {
                "product_id": product.id,
                "product_name": product.name,
                "godown_id": godown.id,
                "godown_name": godown.name,
                "qty": qty,
                "reorder_level": product.reorder_level,
                "low": qty <= product.reorder_level,
                "avg_cost": avg if show_cost else None,
                "value": q2(qty * avg) if (show_cost and avg is not None) else None,
            }
        )
    return rows


@router.get("/movements", response_model=list[MovementOut])
def movements(
    product_id: int | None = None,
    godown_id: int | None = None,
    limit: int = Query(default=100, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Any:
    q = select(StockMovement).order_by(StockMovement.id.desc()).limit(limit)
    if product_id:
        q = q.where(StockMovement.product_id == product_id)
    if godown_id:
        q = q.where(StockMovement.godown_id == godown_id)
    show_cost = sees_cost(user)
    return [
        {
            "id": m.id,
            "movement_date": m.movement_date,
            "product_name": m.product.name,
            "godown_name": m.godown.name,
            "qty": m.qty,
            "kind": m.kind,
            "ref_type": m.ref_type,
            "ref_id": m.ref_id,
            "note": m.note,
            "unit_cost": m.unit_cost if show_cost else None,
            "created_at": m.created_at,
        }
        for m in db.scalars(q)
    ]


@router.post("/adjustments", response_model=MovementOut, status_code=201)
def adjust(
    body: AdjustmentIn, db: Session = Depends(get_db), user: User = Depends(stock_keepers)
) -> Any:
    product = db.get(Product, body.product_id)
    godown = db.get(Godown, body.godown_id)
    if product is None or godown is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product or godown not found")
    on = body.on or date.today()
    ref = stock.Ref(body.kind, note=body.reason)
    try:
        if body.qty < 0:
            mv = stock.stock_out(
                db, product.id, godown.id, -body.qty, ref, on, user.id, product_name=product.name
            )
        else:
            # Found extra bags: value them at the current average so margins aren't skewed.
            bal = db.get(StockBalance, (product.id, godown.id))
            cost = bal.avg_cost if bal else ZERO
            mv = stock.stock_in(db, product.id, godown.id, body.qty, cost, ref, on, user.id)
        db.commit()
    except stock.InsufficientStock as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    db.refresh(mv)
    return {
        "id": mv.id,
        "movement_date": mv.movement_date,
        "product_name": product.name,
        "godown_name": godown.name,
        "qty": mv.qty,
        "kind": mv.kind,
        "ref_type": mv.ref_type,
        "ref_id": mv.ref_id,
        "note": mv.note,
        "unit_cost": mv.unit_cost if sees_cost(user) else None,
        "created_at": mv.created_at,
    }


@router.post("/opening", status_code=201)
def opening_stock(
    body: OpeningIn, db: Session = Depends(get_db), user: User = Depends(owner_only)
) -> dict[str, int]:
    """Load the stock that was already in the godown on the go-live date."""
    if db.get(Godown, body.godown_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Godown not found")
    for item in body.items:
        if db.get(Product, item.product_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown product {item.product_id}")
        stock.stock_in(
            db,
            item.product_id,
            body.godown_id,
            item.qty,
            item.unit_cost,
            stock.Ref("opening", note="Opening stock"),
            body.on,
            user.id,
        )
    db.commit()
    return {"added": len(body.items)}


@router.get("/verify")
def verify(db: Session = Depends(get_db), _: User = Depends(owner_only)) -> dict[str, Any]:
    """Self-check: cached balances must equal the sum of movements."""
    mismatches = stock.verify_balances(db)
    return {
        "ok": not mismatches,
        "mismatches": [
            {"product_id": p, "godown_id": g, "cached": c, "from_movements": m}
            for p, g, c, m in mismatches
        ],
    }
