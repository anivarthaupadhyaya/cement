"""Customer balances.

For now outstanding = credit bills - credit notes against them. Milestone 5 adds receipts
and a proper party ledger; callers only use these functions, so they won't change.
"""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import SalesInvoice, SalesReturn
from app.services.money import ZERO, q2


def party_outstanding(db: Session, party_id: int) -> Decimal:
    billed = db.scalar(
        select(func.coalesce(func.sum(SalesInvoice.grand_total), 0)).where(
            SalesInvoice.party_id == party_id,
            SalesInvoice.payment_mode == "credit",
            SalesInvoice.status == "active",
        )
    )
    returned = db.scalar(
        select(func.coalesce(func.sum(SalesReturn.total), 0))
        .join(SalesInvoice, SalesInvoice.id == SalesReturn.invoice_id)
        .where(
            SalesInvoice.party_id == party_id,
            SalesInvoice.payment_mode == "credit",
            SalesInvoice.status == "active",
        )
    )
    return q2(Decimal(billed or ZERO) - Decimal(returned or ZERO))
