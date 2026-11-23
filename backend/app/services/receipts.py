"""Payments received from customers, and the cheque lifecycle.

received -> deposited -> cleared
        \\-> bounced (from received or deposited): reverses the payment, optional charge
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import OtherDue, Party, Receipt
from app.services import ledger
from app.services.ledger import OpenItem
from app.services.money import ZERO, q2
from app.services.numbering import next_number


class ReceiptError(Exception):
    pass


CHEQUE_FLOW = {
    "deposit": ({"received"}, "deposited"),
    "clear": ({"received", "deposited"}, "cleared"),
    "bounce": ({"received", "deposited"}, "bounced"),
}


def find_by_client_ref(db: Session, client_ref: str) -> Receipt | None:
    return db.scalar(select(Receipt).where(Receipt.client_ref == client_ref))


def create_receipt(
    db: Session,
    *,
    party: Party,
    amount: Decimal,
    mode: str,
    on: date,
    client_ref: str,
    allocations: list[tuple[str, int, Decimal]] | None = None,
    reference: str | None = None,
    cheque_no: str | None = None,
    cheque_date: date | None = None,
    bank_name: str | None = None,
    notes: str | None = None,
    user_id: int | None = None,
) -> Receipt:
    """allocations: [("invoice"|"due", id, amount)]; None = settle oldest bills first."""
    if party.kind == "supplier":
        raise ReceiptError("Receipts are taken from customers")
    if mode == "cheque" and not cheque_no:
        raise ReceiptError("Enter the cheque number")
    ledger.lock_party(db, party.id)

    receipt = Receipt(
        receipt_no=next_number(db, "RCPT", "RCPT", on),
        client_ref=client_ref,
        party_id=party.id,
        receipt_date=on,
        mode=mode,
        amount=q2(amount),
        reference=reference,
        cheque_no=cheque_no if mode == "cheque" else None,
        cheque_date=cheque_date if mode == "cheque" else None,
        bank_name=bank_name if mode == "cheque" else None,
        cheque_status="received" if mode == "cheque" else None,
        notes=notes,
        created_by=user_id,
    )
    db.add(receipt)
    db.flush()
    label = {"cash": "Cash", "upi": "UPI", "bank": "Bank transfer", "cheque": "Cheque"}[mode]
    detail = f" no. {cheque_no}" if mode == "cheque" else (f" ref {reference}" if reference else "")
    ledger.post(
        db,
        party.id,
        on,
        "receipt",
        credit=receipt.amount,
        ref_type="receipt",
        ref_id=receipt.id,
        ref_no=receipt.receipt_no,
        narration=f"{label} received{detail}",
        user_id=user_id,
    )

    if allocations is None:
        ledger.allocate_fifo(db, party.id)
    else:
        items = {i.key: i for i in ledger.open_items(db, party.id)}
        total = sum((a for _, _, a in allocations), ZERO)
        if total > receipt.amount:
            raise ReceiptError("Allocated more than the amount received")
        for kind, item_id, amt in allocations:
            item: OpenItem | None = items.get((kind, item_id))
            if item is None:
                raise ReceiptError("That bill isn't open for this customer")
            if amt <= 0 or amt > item.balance:
                raise ReceiptError(f"{item.ref_no}: only {item.balance} is due")
            ledger.allocate(db, receipt, item, q2(amt))
        db.flush()
    return receipt


def cancel_receipt(db: Session, receipt: Receipt, reason: str, user_id: int | None) -> Receipt:
    if receipt.status == "cancelled":
        raise ReceiptError("This receipt is already cancelled")
    if receipt.cheque_status == "bounced":
        raise ReceiptError("A bounced cheque is already reversed")
    ledger.lock_party(db, receipt.party_id)
    ledger.release_receipt(db, receipt.id)
    receipt.status = "cancelled"
    receipt.cancel_reason = reason
    ledger.post(
        db,
        receipt.party_id,
        date.today(),
        "receipt_cancel",
        debit=receipt.amount,
        ref_type="receipt",
        ref_id=receipt.id,
        ref_no=receipt.receipt_no,
        narration=f"Receipt cancelled: {reason}",
        user_id=user_id,
    )
    db.flush()
    return receipt


def cheque_action(
    db: Session,
    receipt: Receipt,
    action: str,
    on: date,
    charge: Decimal = ZERO,
    user_id: int | None = None,
) -> Receipt:
    if receipt.mode != "cheque" or receipt.status != "active":
        raise ReceiptError("Not an active cheque receipt")
    allowed_from, to = CHEQUE_FLOW[action]
    if receipt.cheque_status not in allowed_from:
        raise ReceiptError(f"Can't {action} a cheque that is {receipt.cheque_status}")
    receipt.cheque_status = to
    if action == "bounce":
        ledger.lock_party(db, receipt.party_id)
        ledger.release_receipt(db, receipt.id)  # the bills it paid are open again
        ledger.post(
            db,
            receipt.party_id,
            on,
            "cheque_bounce",
            debit=receipt.amount,
            ref_type="receipt",
            ref_id=receipt.id,
            ref_no=receipt.receipt_no,
            narration=f"Cheque {receipt.cheque_no} bounced",
            user_id=user_id,
        )
        if charge > 0:
            due = OtherDue(
                party_id=receipt.party_id,
                kind="bounce_charge",
                ref_no=f"BOUNCE-{receipt.receipt_no}",
                due_date=on,
                amount=q2(charge),
                notes=f"Charge for bounced cheque {receipt.cheque_no}",
                created_by=user_id,
            )
            db.add(due)
            db.flush()
            ledger.post(
                db,
                receipt.party_id,
                on,
                "bounce_charge",
                debit=due.amount,
                ref_type="other_due",
                ref_id=due.id,
                ref_no=due.ref_no,
                narration="Cheque bounce charge",
                user_id=user_id,
            )
        ledger.allocate_fifo(db, receipt.party_id)
    db.flush()
    return receipt


def add_opening_due(
    db: Session,
    party: Party,
    ref_no: str,
    due_date: date,
    amount: Decimal,
    notes: str | None,
    user_id: int | None,
) -> OtherDue:
    """Old udhaar from before go-live, entered bill by bill so ageing stays true."""
    ledger.lock_party(db, party.id)
    due = OtherDue(
        party_id=party.id,
        kind="opening",
        ref_no=ref_no,
        due_date=due_date,
        amount=q2(amount),
        notes=notes,
        created_by=user_id,
    )
    db.add(due)
    db.flush()
    ledger.post(
        db,
        party.id,
        due_date,
        "opening",
        debit=due.amount,
        ref_type="other_due",
        ref_id=due.id,
        ref_no=ref_no,
        narration="Opening balance (before go-live)",
        user_id=user_id,
    )
    ledger.allocate_fifo(db, party.id)
    return due


def bounce_count(db: Session, party_id: int) -> int:
    return int(
        db.scalar(
            select(func.count(Receipt.id)).where(
                Receipt.party_id == party_id, Receipt.cheque_status == "bounced"
            )
        )
        or 0
    )
