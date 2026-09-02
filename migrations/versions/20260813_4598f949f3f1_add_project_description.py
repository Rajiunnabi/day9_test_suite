"""add project description

A small, additive, backward-compatible change - the kind of migration you
want most of the time. Nullable with no default means every existing
project row is valid the instant this column appears; nothing to backfill.

Revision ID: 4598f949f3f1
Revises: 0f4f2ddf22f3
Create Date: 2026-08-13 09:15:06.838703

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4598f949f3f1'
down_revision: Union[str, Sequence[str], None] = '0f4f2ddf22f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("projects", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("projects", "description")
