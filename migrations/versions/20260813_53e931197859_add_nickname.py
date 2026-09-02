"""Add nickname

Revision ID: 53e931197859
Revises: 9b9216ff21e1
Create Date: 2026-08-13 22:16:25.201466

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '53e931197859'
down_revision: Union[str, Sequence[str], None] = '9b9216ff21e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
