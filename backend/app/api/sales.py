from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, require_roles
from app.api.stock import sees_cost
from app.core.config import get_settings
from app.core.db import get_db
from app.models import Godown, Role, SalesInvoice, SalesReturn, User
from app.schemas.inventory import CancelIn
from app.schemas.sales import (
    BillDraft,
    PreviewOut,
    ReturnIn,
    SaleIn,
    SaleOut,
    SaleSummary,
    ShopOut,
)
from app.services import billing, ledger
from app.services.gst import STATE_CODES
from app.services.money import ZERO
from app.services.stock import InsufficientStock
from app.services.words import rupees_in_words

router = APIRouter(prefix="/api", tags=["sales"])

billers = require_roles(Role.OWNER, Role.ACCOUNTANT, Role.BILLING)
returns_staff = require_roles(Role.OWNER, Role.ACCOUNTANT)
owner_only = require_roles(Role.OWNER)


def _is_owner(user: User) -> bool:
    return user.role == Role.OWNER.value


def _bill_date(requested: date | None, user: User) -> date:
    today = date.today()
    on = requested or today
    if on > today:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Bill date is in the future")
    if on != today and not _is_owner(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can back-date a bill")
    return on


def _prepare(db: Session, body: BillDraft, on: date) -> billing.PreparedBill:
    godown = db.get(Godown, body.godown_id)
    if godown is None or not godown.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose an active godown")
    try:
        return billing.prepare_bill(
            db,
            on=on,
            party_id=body.party_id,
            customer_name=body.customer_name,
            payment_mode=body.payment_mode,
            godown_id=body.godown_id,
            lines=[billing.BillLineIn(ln.product_id, ln.qty, ln.rate) for ln in body.lines],
            delivery_charge=body.delivery_charge,
        )
    except billing.BillingError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


def _summary(inv: SalesInvoice) -> dict[str, Any]:
    return {
        "id": inv.id,
        "invoice_no": inv.invoice_no,
        "invoice_date": inv.invoice_date,
        "customer_name": inv.customer_name,
        "party_id": inv.party_id,
        "payment_mode": inv.payment_mode,
        "total_bags": sum(ln.qty for ln in inv.lines),
        "grand_total": inv.grand_total,
        "status": inv.status,
        "has_returns": bool(inv.returns),
    }


def _return_out(r: SalesReturn) -> dict[str, Any]:
    return {
        "id": r.id,
        "return_no": r.return_no,
        "return_date": r.return_date,
        "reason": r.reason,
        "taxable_total": r.taxable_total,
        "cgst_total": r.cgst_total,
        "sgst_total": r.sgst_total,
        "igst_total": r.igst_total,
        "round_off": r.round_off,
        "total": r.total,
        "lines": [
            {
                "sales_line_id": rl.sales_line_id,
                "product_name": rl.sales_line.product_name,
                "qty": rl.qty,
                "taxable": rl.taxable,
                "gst_amount": rl.gst_amount,
            }
            for rl in r.lines
        ],
    }


def _payment_status(db: Session, inv: SalesInvoice) -> dict[str, Decimal]:
    """Cash bills are paid at the counter; credit bills are paid by allocated receipts."""
    returned = sum((r.total for r in inv.returns), ZERO)
    net = inv.grand_total - returned
    if inv.status == "cancelled":
        return {"paid": ZERO, "balance_due": ZERO}
    if inv.payment_mode == "cash":
        return {"paid": net, "balance_due": ZERO}
    paid = ledger.invoice_paid(db, inv.id)
    return {"paid": paid, "balance_due": net - paid}


def _detail(db: Session, inv: SalesInvoice, user: User) -> dict[str, Any]:
    show_cost = sees_cost(user)
    goods_taxable = inv.taxable_total - inv.delivery_taxable
    out = _summary(inv)
    out.update(
        {
            "customer_phone": inv.customer_phone,
            "customer_gstin": inv.customer_gstin,
            "customer_address": inv.customer_address,
            "place_of_supply": inv.place_of_supply,
            "is_interstate": inv.is_interstate,
            "godown_id": inv.godown_id,
            "godown_name": inv.godown.name,
            "vehicle_no": inv.vehicle_no,
            "delivery_address": inv.delivery_address,
            "delivery_charge": inv.delivery_charge,
            "delivery_taxable": inv.delivery_taxable,
            "delivery_gst": inv.delivery_gst,
            "taxable_total": inv.taxable_total,
            "cgst_total": inv.cgst_total,
            "sgst_total": inv.sgst_total,
            "igst_total": inv.igst_total,
            "round_off": inv.round_off,
            "amount_in_words": rupees_in_words(inv.grand_total),
            **_payment_status(db, inv),
            "cost_total": inv.cost_total if show_cost else None,
            "margin": goods_taxable - inv.cost_total if show_cost else None,
            "credit_override_reason": inv.credit_override_reason,
            "notes": inv.notes,
            "cancel_reason": inv.cancel_reason,
            "cancelled_at": inv.cancelled_at,
            "created_at": inv.created_at,
            "lines": [
                {
                    "id": ln.id,
                    "product_id": ln.product_id,
                    "product_name": ln.product_name,
                    "hsn_code": ln.hsn_code,
                    "qty": ln.qty,
                    "qty_returned": ln.qty_returned,
                    "rate": ln.rate,
                    "gst_rate": ln.gst_rate,
                    "taxable": ln.taxable,
                    "gst_amount": ln.gst_amount,
                    "cost_per_bag": ln.cost_per_bag if show_cost else None,
                }
                for ln in inv.lines
            ],
            "returns": [_return_out(r) for r in inv.returns],
        }
    )
    return out


def _load(db: Session, invoice_id: int) -> SalesInvoice:
    inv = db.scalar(
        select(SalesInvoice)
        .where(SalesInvoice.id == invoice_id)
        .options(
            selectinload(SalesInvoice.lines),
            selectinload(SalesInvoice.returns).selectinload(SalesReturn.lines),
        )
        .execution_options(populate_existing=True)
    )
    if inv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bill not found")
    return inv


# ---- Routes -----------------------------------------------------------------------
@router.get("/shop", response_model=ShopOut)
def shop(_: User = Depends(get_current_user)) -> Any:
    s = get_settings()
    return {
        "name": s.shop_name,
        "address": s.shop_address,
        "gstin": s.shop_gstin,
        "phone": s.shop_phone,
        "bank": s.shop_bank,
        "state_code": s.shop_state_code,
        "state_name": STATE_CODES.get(s.shop_state_code, ""),
    }


@router.post("/sales/preview", response_model=PreviewOut)
def preview(body: BillDraft, db: Session = Depends(get_db), user: User = Depends(billers)) -> Any:
    """Live totals for the billing screen. Saves nothing."""
    bill = _prepare(db, body, _bill_date(body.invoice_date, user))
    db.rollback()
    show_cost = sees_cost(user)
    cgst, sgst, igst = billing.tax_split(bill.amounts.gst_total, bill.interstate)
    return {
        "customer_name": bill.customer_name,
        "place_of_supply": bill.place_of_supply,
        "is_interstate": bill.interstate,
        "lines": [
            {
                "product_id": ln.product.id,
                "product_name": ln.product.name,
                "qty": ln.qty,
                "rate": ln.rate,
                "gst_rate": ln.gst_rate,
                "gross": ln.amounts.gross,
                "taxable": ln.amounts.taxable,
                "gst_amount": ln.amounts.gst,
                "available": ln.available,
                "cost_per_bag": ln.avg_cost if show_cost else None,
                "margin": ln.margin if show_cost else None,
                "below_cost": ln.below_cost,
            }
            for ln in bill.lines
        ],
        "delivery_taxable": bill.amounts.delivery_taxable,
        "delivery_gst": bill.amounts.delivery_gst,
        "taxable_total": bill.amounts.taxable_total,
        "cgst_total": cgst,
        "sgst_total": sgst,
        "igst_total": igst,
        "round_off": bill.amounts.round_off,
        "grand_total": bill.amounts.grand_total,
        "total_bags": sum(ln.qty for ln in bill.lines),
        "outstanding": bill.outstanding,
        "credit_limit": bill.credit_limit,
        "over_limit": bill.over_limit,
        "margin": bill.margin if show_cost else None,
        "warnings": bill.warnings,
    }


@router.post("/sales", response_model=SaleOut, status_code=201)
def create_sale(body: SaleIn, db: Session = Depends(get_db), user: User = Depends(billers)) -> Any:
    # Double-click / retry after a network blip: hand back the bill already saved.
    existing = billing.find_by_client_ref(db, body.client_ref)
    if existing is not None:
        return _detail(db, _load(db, existing.id), user)

    bill = _prepare(db, body, _bill_date(body.invoice_date, user))
    try:
        invoice = billing.create_invoice(
            db,
            bill,
            client_ref=body.client_ref,
            is_owner=_is_owner(user),
            user_id=user.id,
            customer_phone=body.customer_phone,
            vehicle_no=(body.vehicle_no or "").strip().upper() or None,
            delivery_address=body.delivery_address,
            credit_override_reason=body.credit_override_reason,
            notes=body.notes,
        )
        db.commit()
    except billing.CreditLimitExceeded as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except billing.BillingError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except InsufficientStock as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except IntegrityError:
        # Two identical submissions raced past the client_ref check: return the winner.
        db.rollback()
        winner = billing.find_by_client_ref(db, body.client_ref)
        if winner is None:
            raise
        return _detail(db, _load(db, winner.id), user)
    return _detail(db, _load(db, invoice.id), user)


@router.get("/sales", response_model=list[SaleSummary])
def list_sales(
    q: str | None = Query(default=None, max_length=60),
    party_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    payment_mode: str | None = Query(default=None, pattern="^(cash|credit)$"),
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Any:
    stmt = (
        select(SalesInvoice)
        .options(selectinload(SalesInvoice.lines), selectinload(SalesInvoice.returns))
        .order_by(SalesInvoice.id.desc())
        .limit(limit)
    )
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(SalesInvoice.invoice_no.ilike(like), SalesInvoice.customer_name.ilike(like))
        )
    if party_id:
        stmt = stmt.where(SalesInvoice.party_id == party_id)
    if date_from:
        stmt = stmt.where(SalesInvoice.invoice_date >= date_from)
    if date_to:
        stmt = stmt.where(SalesInvoice.invoice_date <= date_to)
    if payment_mode:
        stmt = stmt.where(SalesInvoice.payment_mode == payment_mode)
    return [_summary(inv) for inv in db.scalars(stmt).unique()]


@router.get("/sales/{invoice_id}", response_model=SaleOut)
def get_sale(
    invoice_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Any:
    return _detail(db, _load(db, invoice_id), user)


@router.post("/sales/{invoice_id}/cancel", response_model=SaleOut)
def cancel_sale(
    invoice_id: int,
    body: CancelIn,
    db: Session = Depends(get_db),
    user: User = Depends(owner_only),
) -> Any:
    """The number stays used (gap-free series); the bags go back into stock."""
    inv = _load(db, invoice_id)
    try:
        billing.cancel_invoice(db, inv, body.reason, user.id)
        db.commit()
    except billing.BillingError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return _detail(db, _load(db, invoice_id), user)


@router.post("/sales/{invoice_id}/returns", response_model=SaleOut, status_code=201)
def create_return(
    invoice_id: int,
    body: ReturnIn,
    db: Session = Depends(get_db),
    user: User = Depends(returns_staff),
) -> Any:
    inv = _load(db, invoice_id)
    on = body.return_date or date.today()
    if on > date.today():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Return date is in the future")
    try:
        billing.create_return(
            db,
            inv,
            [(i.sales_line_id, i.qty) for i in body.items],
            body.reason,
            on,
            user.id,
        )
        db.commit()
    except billing.BillingError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return _detail(db, _load(db, invoice_id), user)
