from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AuditLog(Base):
    """Written only by the audit trigger (see migration). Rows can never be updated or deleted."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    table_name: Mapped[str] = mapped_column(String(63), nullable=False, index=True)
    record_id: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    user_id: Mapped[int | None] = mapped_column(Integer)
    old_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    new_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
