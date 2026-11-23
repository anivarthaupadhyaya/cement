from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, require_roles
from app.core.db import get_db
from app.models import OtherDue, Party, Receipt, Role, SalesInvoice, User
from app.schemas.credit import (
    AgeingOut,
    ChequeActionIn,
    OpeningDueIn,
    OpenItemOut,
    ReceiptDraft,
    ReceiptIn,
    ReceiptOut,
    ReceiptPreviewOut,
    StatementOut,
)
from app.schemas.inventory import CancelIn
from app.services import ledger
from app.services import receipts as svc
from app.services.money import ZERO, q2
from app.services.words import rupees_in_words

router = APIRouter(prefix="/api", tags=["receipts"])

collectors = require_roles(Role.OWNER, Role.ACCOUNTANT, Role.BILLING)
accounts = require_roles(Role.OWNER, Role.ACCOUNTANT)
owner_only = require_roles(Role.OWNER)


def _party(db: Session, party_id: int) -> Party:
    party = db.get(Party, party_id)
    if party is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    return party


def _items_out(items: list[ledger.OpenItem], today: date) -> list[dict[str, Any]]:
    return [
        {
            "kind": i.kind,
            "id": i.id,
            "ref_no": i.ref_no,
            "date": i.on,
            "age_days": (today - i.on).days,
            "amount": i.amount,
            "paid": i.paid,
            "balance": i.balance,
        }
        for i in items
    ]


def _receipt_out(db: Session, r: Receipt) -> dict[str, Any]:
    active = [a for a in r.allocations if a.released_at is None]
    inv_nos = dict(
        db.execute(
            select(SalesInvoice.id, SalesInvoice.invoice_no).where(
                SalesInvoice.id.in_([a.invoice_id for a in active if a.invoice_id])
            )
        ).all()
    )
    due_nos = dict(
        db.execute(
            select(OtherDue.id, OtherDue.ref_no).where(
                OtherDue.id.in_([a.other_due_id for a in active if a.other_due_id])
            )
        ).all()
    )
    allocated = sum((a.amount for a in active), ZERO)
    return {
        "id": r.id,
        "receipt_no": r.receipt_no,
        "receipt_date": r.receipt_date,
        "party_id": r.party_id,
        "party_name": r.party.name,
        "mode": r.mode,
        "amount": r.amount,
        "reference": r.reference,
        "cheque_no": r.cheque_no,
        "cheque_date": r.cheque_date,
        "bank_name": r.bank_name,
        "cheque_status": r.cheque_status,
        "status": r.status,
        "cancel_reason": r.cancel_reason,
        "notes": r.notes,
        "allocated": allocated,
        "unallocated": r.amount - allocated if r.is_live else ZERO,
        "allocations": [
            {
                "kind": "invoice" if a.invoice_id else "due",
                "id": a.invoice_id or a.other_due_id,
                "ref_no": inv_nos.get(a.invoice_id)
                if a.invoice_id
                else due_nos.get(a.other_due_id or 0),
                "amount": a.amount,
            }
            for a in active
        ],
        "balance_after": ledger.party_outstanding(db, r.party_id),
        "amount_in_words": rupees_in_words(r.amount),
        "created_at": r.created_at,
    }


def _load(db: Session, receipt_id: int) -> Receipt:
    r = db.scalar(
        select(Receipt)
        .where(Receipt.id == receipt_id)
        .options(selectinload(Receipt.allocations))
        .execution_options(populate_existing=True)
    )
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Receipt not found")
    return r


# ---- Receipts -------------------------------------------------------------------------
@router.post("/receipts/preview", response_model=ReceiptPreviewOut)
def preview(
    body: ReceiptDraft, db: Session = Depends(get_db), _: User = Depends(collectors)
) -> Any:
    """Open bills and how this amount would settle them (oldest first). Saves nothing."""
    party = _party(db, body.party_id)
    items = ledger.open_items(db, party.id)
    adv = ledger.advance(db, party.id)
    plan = ledger.plan_fifo(items, body.amount)
    used = sum((amt for _, amt in plan), ZERO)
    return {
        "outstanding": ledger.party_outstanding(db, party.id),
        "open_items": _items_out(items, date.today()),
        "plan": [
            {"kind": i.kind, "id": i.id, "ref_no": i.ref_no, "amount": amt} for i, amt in plan
        ],
        "advance_after": adv + body.amount - used,
        "bounced_cheques": svc.bounce_count(db, party.id),
    }


@router.post("/receipts", response_model=ReceiptOut, status_code=201)
def create_receipt(
    body: ReceiptIn, db: Session = Depends(get_db), user: User = Depends(collectors)
) -> Any:
    existing = svc.find_by_client_ref(db, body.client_ref)
    if existing is not None:
        return _receipt_out(db, _load(db, existing.id))
    if user.role == Role.BILLING.value and body.mode in ("cheque", "bank"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Cheque and bank receipts are entered by the office"
        )
    on = body.receipt_date or date.today()
    if on > date.today():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Receipt date is in the future")
    if on != date.today() and user.role != Role.OWNER.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can back-date a receipt")
    try:
        receipt = svc.create_receipt(
            db,
            party=_party(db, body.party_id),
            amount=body.amount,
            mode=body.mode,
            on=on,
            client_ref=body.client_ref,
            allocations=(
                [(a.kind, a.id, a.amount) for a in body.allocations]
                if body.allocations is not None
                else None
            ),
            reference=(body.reference or "").strip() or None,
            cheque_no=(body.cheque_no or "").strip() or None,
            cheque_date=body.cheque_date,
            bank_name=(body.bank_name or "").strip() or None,
            notes=body.notes,
            user_id=user.id,
        )
        db.commit()
    except svc.ReceiptError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except IntegrityError:
        db.rollback()
        winner = svc.find_by_client_ref(db, body.client_ref)
        if winner is None:
            raise
        return _receipt_out(db, _load(db, winner.id))
    return _receipt_out(db, _load(db, receipt.id))


@router.get("/receipts", response_model=list[ReceiptOut])
def list_receipts(
    party_id: int | None = None,
    q: str | None = Query(default=None, max_length=60),
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Any:
    stmt = (
        select(Receipt)
        .join(Party, Party.id == Receipt.party_id)
        .options(selectinload(Receipt.allocations))
        .order_by(Receipt.id.desc())
        .limit(limit)
    )
    if party_id:
        stmt = stmt.where(Receipt.party_id == party_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Receipt.receipt_no.ilike(like),
                Party.name.ilike(like),
                Receipt.cheque_no.ilike(like),
            )
        )
    if date_from:
        stmt = stmt.where(Receipt.receipt_date >= date_from)
    if date_to:
        stmt = stmt.where(Receipt.receipt_date <= date_to)
    return [_receipt_out(db, r) for r in db.scalars(stmt).unique()]


@router.get("/receipts/{receipt_id}", response_model=ReceiptOut)
def get_receipt(
    receipt_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> Any:
    return _receipt_out(db, _load(db, receipt_id))


@router.post("/receipts/{receipt_id}/cancel", response_model=ReceiptOut)
def cancel_receipt(
    receipt_id: int, body: CancelIn, db: Session = Depends(get_db), user: User = Depends(owner_only)
) -> Any:
    try:
        svc.cancel_receipt(db, _load(db, receipt_id), body.reason, user.id)
        db.commit()
    except svc.ReceiptError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return _receipt_out(db, _load(db, receipt_id))


@router.post("/receipts/{receipt_id}/cheque", response_model=ReceiptOut)
def cheque_action(
    receipt_id: int,
    body: ChequeActionIn,
    db: Session = Depends(get_db),
    user: User = Depends(accounts),
) -> Any:
    try:
        svc.cheque_action(
            db, _load(db, receipt_id), body.action, body.on or date.today(), body.charge, user.id
        )
        db.commit()
    except svc.ReceiptError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return _receipt_out(db, _load(db, receipt_id))


@router.get("/cheques", response_model=list[ReceiptOut])
def cheques(
    status_: str | None = Query(
        default=None, alias="status", pattern="^(received|deposited|cleared|bounced|pending)$"
    ),
    db: Session = Depends(get_db),
    _: User = Depends(accounts),
) -> Any:
    """'pending' = received or deposited, i.e. not yet cleared."""
    stmt = (
        select(Receipt)
        .where(Receipt.mode == "cheque", Receipt.status == "active")
        .options(selectinload(Receipt.allocations))
        .order_by(Receipt.cheque_date.nulls_last(), Receipt.id)
    )
    if status_ == "pending":
        stmt = stmt.where(Receipt.cheque_status.in_(["received", "deposited"]))
    elif status_:
        stmt = stmt.where(Receipt.cheque_status == status_)
    return [_receipt_out(db, r) for r in db.scalars(stmt).unique()]


# ---- Customer account -------------------------------------------------------------------
@router.get("/parties/{party_id}/open-bills", response_model=list[OpenItemOut])
def open_bills(
    party_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> Any:
    _party(db, party_id)
    return _items_out(ledger.open_items(db, party_id), date.today())


@router.get("/parties/{party_id}/ledger", response_model=StatementOut)
def party_statement(
    party_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Any:
    party = _party(db, party_id)
    today = date.today()
    d_to = date_to or today
    d_from = date_from or date(d_to.year if d_to.month >= 4 else d_to.year - 1, 4, 1)  # FY start
    if d_from > d_to:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "From date is after to date")
    opening, lines, closing = ledger.statement(db, party.id, d_from, d_to)
    return {
        "party_id": party.id,
        "party_name": party.name,
        "phone": party.phone,
        "date_from": d_from,
        "date_to": d_to,
        "opening": opening,
        "lines": [
            {
                "id": ln.id,
                "date": ln.on,
                "kind": ln.kind,
                "ref_no": ln.ref_no,
                "narration": ln.narration,
                "debit": ln.debit,
                "credit": ln.credit,
                "balance": ln.balance,
            }
            for ln in lines
        ],
        "closing": closing,
        "total_debit": sum((ln.debit for ln in lines), ZERO),
        "total_credit": sum((ln.credit for ln in lines), ZERO),
    }


@router.post("/parties/{party_id}/opening-dues", response_model=list[OpenItemOut], status_code=201)
def add_opening_due(
    party_id: int, body: OpeningDueIn, db: Session = Depends(get_db), user: User = Depends(accounts)
) -> Any:
    party = _party(db, party_id)
    if body.due_date > date.today():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Date is in the future")
    svc.add_opening_due(
        db, party, body.ref_no.strip(), body.due_date, body.amount, body.notes, user.id
    )
    db.commit()
    return _items_out(ledger.open_items(db, party_id), date.today())


# ---- Reports -----------------------------------------------------------------------------
@router.get("/reports/outstanding", response_model=AgeingOut)
def outstanding(
    area: str | None = Query(default=None, max_length=80),
    as_of: date | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Any:
    on = as_of or date.today()
    rows = []
    for r in ledger.ageing(db, on, area):
        b = r.pop("buckets")
        rows.append(
            {
                **r,
                "b0_30": b["0-30"],
                "b31_60": b["31-60"],
                "b61_90": b["61-90"],
                "b90_plus": b["90+"],
            }
        )
    keys = ["b0_30", "b31_60", "b61_90", "b90_plus", "due", "advance", "net", "overdue"]
    totals: dict[str, Decimal] = {k: q2(sum((row[k] for row in rows), ZERO)) for k in keys}
    rows.sort(key=lambda row: row["net"], reverse=True)
    return {"as_of": on, "rows": rows, "totals": totals}


@router.get("/reports/ledger-check")
def ledger_check(db: Session = Depends(get_db), _: User = Depends(owner_only)) -> dict[str, Any]:
    """Self-check: every customer's ledger balance equals their open bills minus advance."""
    bad = []
    for pid in db.scalars(select(Party.id)):
        bal, items = ledger.check_party(db, pid)
        if bal != items:
            bad.append({"party_id": pid, "ledger": str(bal), "open_items": str(items)})
    return {"ok": not bad, "mismatches": bad}
