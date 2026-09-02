"""merging heads

Revision ID: bcd8197aab4f
Revises: 53e931197859, dd4ef2ba9f4b
Create Date: 2026-08-13 22:17:12.348899

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bcd8197aab4f'
down_revision: Union[str, Sequence[str], None] = ('53e931197859', 'dd4ef2ba9f4b')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
