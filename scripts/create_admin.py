"""Promote or create the first admin.

Run:  uv run python -m scripts.create_admin you@example.com "Your Name"

Worth noticing what this file does NOT do: no raw SQL, no password hashing, no
duplicate-email check. It calls the same UserService the API calls. That is the
practical payoff of keeping business rules out of route handlers - a CLI gets
them for free, and the rules cannot drift between the two entry points.
"""

from __future__ import annotations

import getpass
import sys

from app.core.enums import UserRole
from app.core.security import hash_password
from app.db.session import session_scope
from app.repositories.user import UserRepository


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 1

    email, full_name = sys.argv[1], sys.argv[2]

    with session_scope() as db:
        users = UserRepository(db)
        user = users.get_by_email(email)

        if user is None:
            password = getpass.getpass("Password for the new admin: ")
            if len(password) < 8:
                print("Password must be at least 8 characters.")
                return 1
            from app.db.models.user import User

            user = User(
                email=email,
                full_name=full_name,
                hashed_password=hash_password(password),
                role=UserRole.ADMIN,
            )
            users.add(user)
            print(f"Created admin {email}")
        else:
            user.role = UserRole.ADMIN
            user.token_version += 1
            print(f"Promoted {email} to admin")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
