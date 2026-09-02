"""add task completed_at and comments table

Two things bundled in one migration because they're related: a new
nullable column, and a data migration that backfills it for rows that
already exist.

IMPORTANT - autogenerate false positives: `alembic revision --autogenerate`
also proposed dropping idx_tasks_project_status, ux_users_email_active, and
both CHECK constraints on tasks. That's wrong - those are real, currently
in use (see the baseline migration and run_day3.py). Autogenerate diffs the
live DB against SQLAlchemy's Table/Column metadata, and none of those four
objects are expressed as SQLAlchemy constructs (they were added with raw
op.execute() / op.create_check_constraint() calls), so from autogenerate's
point of view they simply don't exist on the "model" side, and anything
the DB has that the model doesn't is flagged as "should be removed". This
is exactly why autogenerate output always needs a read-through before
`alembic upgrade` - it is a draft, not a verdict. Those four drop_index /
drop_constraint calls were removed from upgrade() below (and the matching
recreate calls from downgrade()).

Revision ID: 9b9216ff21e1
Revises: 4598f949f3f1
Create Date: 2026-08-13 09:15:46.351961

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b9216ff21e1'
down_revision: Union[str, Sequence[str], None] = '4598f949f3f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "comments",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("author_id", sa.BigInteger(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Step 1 of the data migration: add the column nullable, with no
    # default. A NOT NULL column with no default would fail immediately on
    # a table that already has rows - there'd be nothing to put in it.
    op.add_column("tasks", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))

    # Step 2: backfill existing rows. Every task that's already 'done' gets
    # its completed_at set from updated_at - the closest fact already in
    # the table to "when it was actually finished". Plain SQL via
    # op.execute(), not the ORM: this runs once, as part of the DDL
    # transaction, against however many rows exist right now - no need to
    # load them into Python objects just to write one column.
    op.execute(
        """
        UPDATE tasks
        SET completed_at = updated_at
        WHERE status = 'done' AND completed_at IS NULL;
        """
    )

    # completed_at stays nullable going forward too: a 'todo' or
    # 'in_progress' task legitimately has no completion time.


def downgrade() -> None:
    """Downgrade schema."""
    # No data migration to reverse here - completed_at simply goes away,
    # taking its backfilled values with it. If this needed to be
    # recoverable, the values would need to be preserved somewhere else
    # first; that's not the case for a derived field like this one.
    op.drop_column("tasks", "completed_at")
    op.drop_table("comments")
