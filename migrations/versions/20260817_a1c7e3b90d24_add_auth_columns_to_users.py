"""add auth columns to users

Adds the three columns Day 7 needs:
  hashed_password - argon2 hash, NULL for accounts made before auth existed
  role            - 'user' or 'admin', guarded by a CHECK constraint
  token_version   - bumped on logout/password change to revoke old JWTs

Revision ID: a1c7e3b90d24
Revises: bcd8197aab4f
Create Date: 2026-08-17

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1c7e3b90d24'
down_revision: Union[str, Sequence[str], None] = 'bcd8197aab4f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable on purpose: existing rows have no password. They simply cannot
    # log in until someone sets one. A NOT NULL here would fail on any DB that
    # already has users in it.
    op.add_column("users", sa.Column("hashed_password", sa.Text(), nullable=True))

    # server_default lets Postgres fill existing rows in one pass, so the
    # column can be NOT NULL immediately.
    op.add_column(
        "users",
        sa.Column(
            "role", sa.Text(), nullable=False, server_default=sa.text("'user'")
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "token_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    # The database is the real guard on allowed roles - same approach as the
    # existing ck_tasks_status_valid constraint in the baseline migration.
    op.create_check_constraint(
        "ck_users_role_valid",
        "users",
        "role in ('user', 'admin')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_role_valid", "users", type_="check")
    op.drop_column("users", "token_version")
    op.drop_column("users", "role")
    op.drop_column("users", "hashed_password")
