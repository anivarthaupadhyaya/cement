"""Gap-free document numbers per financial year: INV/2026-27/0001, CN/2026-27/0001, ...

The counter row is locked with SELECT ... FOR UPDATE inside the same transaction that saves
the document. If the save fails the whole transaction rolls back, so no number is skipped;
two clerks saving at once simply wait for each other.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import DocSeries


def financial_year(d: date) -> str:
    """Indian FY runs April-March: 15 Nov 2026 -> '2026-27', 10 Feb 2027 -> '2026-27'."""
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def next_number(db: Session, doc_type: str, prefix: str, on: date) -> str:
    fy = financial_year(on)
    db.execute(
        insert(DocSeries).values(doc_type=doc_type, fy=fy, next_no=1).on_conflict_do_nothing()
    )
    series = db.scalar(
        select(DocSeries)
        .where(DocSeries.doc_type == doc_type, DocSeries.fy == fy)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assert series is not None
    number = series.next_no
    series.next_no = number + 1
    db.flush()
    return f"{prefix}/{fy}/{number:04d}"
