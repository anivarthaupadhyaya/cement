from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_roles
from app.core.db import get_db
from app.models import Godown, Party, Purchase, Role, User
from app.schemas.inventory import CancelIn, PurchaseIn, PurchaseOut, PurchaseSummary
from app.services import purchases as svc
from app.services.stock import InsufficientStock

router = APIRouter(prefix="/api/purchases", tags=["purchases"])

viewers = require_roles(Role.OWNER, Role.ACCOUNTANT, Role.GODOWN)
owner_only = require_roles(Role.OWNER)

_DETAIL_FIELDS = (
    "godown_id",
    "vehicle_no",
    "lr_no",
    "is_interstate",
    "freight",
    "unloading",
    "other_charges",
    "taxable_total",
    "cgst_total",
    "sgst_total",
    "igst_total",
    "round_off",
    "notes",
    "cancel_reason",
    "created_at",
)


def _summary(p: Purchase) -> dict[str, Any]:
    return {
        "id": p.id,
        "supplier_id": p.supplier_id,
        "supplier_name": p.supplier.name,
        "supplier_invoice_no": p.supplier_invoice_no,
        "invoice_date": p.invoice_date,
        "received_date": p.received_date,
        "godown_name": p.godown.name,
        "total_bags": sum(ln.qty_invoiced for ln in p.lines),
        "invoice_total": p.invoice_total,
        "status": p.status,
    }


def _detail(p: Purchase) -> dict[str, Any]:
    out = _summary(p)
    out.update({c: getattr(p, c) for c in _DETAIL_FIELDS})
    out["lines"] = [
        {
            "id": ln.id,
            "product_id": ln.product_id,
            "product_name": ln.product.name,
            "qty_invoiced": ln.qty_invoiced,
            "qty_received": ln.qty_received,
            "qty_damaged": ln.qty_damaged,
            "qty_short": ln.qty_short,
            "rate": ln.rate,
            "gst_rate": ln.gst_rate,
            "taxable": ln.taxable,
            "gst_amount": ln.gst_amount,
            "charges": ln.charges,
            "landed_cost": ln.landed_cost,
        }
        for ln in p.lines
    ]
    return out


def _load(db: Session, purchase_id: int) -> Purchase:
    p = db.scalar(
        select(Purchase).where(Purchase.id == purchase_id).options(selectinload(Purchase.lines))
    )
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Purchase not found")
    return p


@router.get("", response_model=list[PurchaseSummary])
def list_purchases(
    supplier_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    include_cancelled: bool = True,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(viewers),
) -> Any:
    q = (
        select(Purchase)
        .options(selectinload(Purchase.lines))
        .order_by(Purchase.invoice_date.desc(), Purchase.id.desc())
        .limit(limit)
    )
    if supplier_id:
        q = q.where(Purchase.supplier_id == supplier_id)
    if date_from:
        q = q.where(Purchase.invoice_date >= date_from)
    if date_to:
        q = q.where(Purchase.invoice_date <= date_to)
    if not include_cancelled:
        q = q.where(Purchase.status == "active")
    return [_summary(p) for p in db.scalars(q).unique()]


@router.get("/{purchase_id}", response_model=PurchaseOut)
def get_purchase(
    purchase_id: int, db: Session = Depends(get_db), _: User = Depends(viewers)
) -> Any:
    return _detail(_load(db, purchase_id))


@router.post("", response_model=PurchaseOut, status_code=201)
def create_purchase(
    body: PurchaseIn, db: Session = Depends(get_db), user: User = Depends(viewers)
) -> Any:
    supplier = db.get(Party, body.supplier_id)
    if supplier is None or supplier.kind == "customer":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose a supplier")
    godown = db.get(Godown, body.godown_id)
    if godown is None or not godown.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose an active godown")
    try:
        purchase = svc.create_purchase(
            db,
            supplier=supplier,
            supplier_invoice_no=body.supplier_invoice_no,
            invoice_date=body.invoice_date,
            received_date=body.received_date or body.invoice_date,
            godown_id=body.godown_id,
            lines=[
                svc.LineInput(
                    ln.product_id, ln.qty_invoiced, ln.qty_received or 0, ln.qty_damaged, ln.rate
                )
                for ln in body.lines
            ],
            freight=body.freight,
            unloading=body.unloading,
            other_charges=body.other_charges,
            vehicle_no=body.vehicle_no,
            lr_no=body.lr_no,
            notes=body.notes,
            user_id=user.id,
        )
        db.commit()
    except svc.PurchaseError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This supplier bill number is already entered"
        ) from exc
    return _detail(_load(db, purchase.id))


@router.post("/{purchase_id}/cancel", response_model=PurchaseOut)
def cancel_purchase(
    purchase_id: int,
    body: CancelIn,
    db: Session = Depends(get_db),
    user: User = Depends(owner_only),
) -> Any:
    purchase = _load(db, purchase_id)
    try:
        svc.cancel_purchase(db, purchase, body.reason, date.today(), user.id)
        db.commit()
    except svc.PurchaseError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except InsufficientStock as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Can't cancel: some of these bags are already sold. {exc}",
        ) from exc
    return _detail(_load(db, purchase_id))
