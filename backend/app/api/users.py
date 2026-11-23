from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.db import get_db
from app.core.security import hash_password
from app.models import AuditLog, Role, User, UserSession
from app.schemas.auth import AuditOut, UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/api", tags=["admin"])
owner_only = require_roles(Role.OWNER)


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(owner_only)) -> list[User]:
    return list(db.scalars(select(User).order_by(User.id)))


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreate, db: Session = Depends(get_db), _: User = Depends(owner_only)
) -> User:
    if db.scalar(select(User.id).where(User.username == body.username)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already taken")
    user = User(
        username=body.username,
        full_name=body.full_name,
        password_hash=hash_password(body.password),
        role=body.role.value,
    )
    db.add(user)
    db.commit()
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserUpdate,
    db: Session = Depends(get_db),
    me: User = Depends(owner_only),
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if user.id == me.id and (body.is_active is False or (body.role and body.role != Role.OWNER)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't demote or disable yourself")
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.role is not None:
        user.role = body.role.value
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.password is not None:
        user.password_hash = hash_password(body.password)
    if body.is_active is False or body.password is not None:
        db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.commit()
    return user


@router.get("/audit", response_model=list[AuditOut])
def list_audit(
    table: str | None = None,
    record_id: str | None = None,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(owner_only),
) -> list[AuditLog]:
    q = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if table:
        q = q.where(AuditLog.table_name == table)
    if record_id:
        q = q.where(AuditLog.record_id == record_id)
    return list(db.scalars(q))
