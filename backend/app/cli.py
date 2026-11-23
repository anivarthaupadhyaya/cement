"""Admin commands (run from the backend folder).

python -m app.cli create-owner <username> "<Full Name>"
python -m app.cli reset-password <username>
"""

import getpass
import sys

from sqlalchemy import delete, select

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models import Role, User, UserSession


def _ask_password() -> str:
    password = getpass.getpass("New password (min 8 chars): ")
    if len(password) < 8:
        sys.exit("Password too short")
    if getpass.getpass("Repeat password: ") != password:
        sys.exit("Passwords don't match")
    return password


def create_owner(username: str, full_name: str) -> None:
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.username == username)):
            sys.exit(f"User {username!r} already exists")
        db.add(
            User(
                username=username,
                full_name=full_name,
                password_hash=hash_password(_ask_password()),
                role=Role.OWNER.value,
            )
        )
        db.commit()
    print(f"Owner {username!r} created.")


def reset_password(username: str) -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            sys.exit(f"No user named {username!r}")
        user.password_hash = hash_password(_ask_password())
        user.is_active = True
        db.execute(delete(UserSession).where(UserSession.user_id == user.id))
        db.commit()
    print(f"Password for {username!r} reset; all their sessions were logged out.")


def main(argv: list[str]) -> None:
    if len(argv) == 3 and argv[0] == "create-owner":
        create_owner(argv[1], argv[2])
    elif len(argv) == 2 and argv[0] == "reset-password":
        reset_password(argv[1])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
