from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import hash_token
from app.models import Role, User, UserSession

settings = get_settings()


def get_current_user(
    db: Session = Depends(get_db),
    token: str | None = Cookie(default=None, alias=settings.cookie_name),
) -> User:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not logged in")
    row = db.execute(
        select(UserSession, User)
        .join(User, User.id == UserSession.user_id)
        .where(UserSession.token_hash == hash_token(token))
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    sess, user = row
    if sess.expires_at < datetime.now(UTC) or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    # Tag this transaction for the audit trigger; the session's after_begin hook
    # re-applies it to any later transaction (e.g. after a commit) in this request.
    db.info["user_id"] = user.id
    db.execute(text("SELECT set_config('app.user_id', :uid, true)"), {"uid": str(user.id)})
    return user


def require_roles(*roles: Role) -> Callable[..., User]:
    allowed = {r.value for r in roles}

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have access to this")
        return user

    return checker
