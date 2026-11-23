"""Admin commands.  Usage:  python -m app.cli create-owner <username> "<Full Name>" """

import getpass
import sys

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models import Role, User


def create_owner(username: str, full_name: str) -> None:
    password = getpass.getpass("Password (min 8 chars): ")
    if len(password) < 8:
        sys.exit("Password too short")
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.username == username)):
            sys.exit(f"User {username!r} already exists")
        db.add(
            User(
                username=username,
                full_name=full_name,
                password_hash=hash_password(password),
                role=Role.OWNER.value,
            )
        )
        db.commit()
    print(f"Owner {username!r} created.")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "create-owner":
        create_owner(sys.argv[2], sys.argv[3])
    else:
        sys.exit(__doc__)
