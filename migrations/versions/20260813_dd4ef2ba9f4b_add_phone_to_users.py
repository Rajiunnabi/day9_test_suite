"""Add phone to users

Revision ID: dd4ef2ba9f4b
Revises: 9b9216ff21e1
Create Date: 2026-08-13 16:32:41.317698

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'dd4ef2ba9f4b'
down_revision: Union[str, Sequence[str], None] = '9b9216ff21e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('phone', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'phone')