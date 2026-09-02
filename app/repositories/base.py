"""A deliberately thin base.

It holds the session and offers add/flush - nothing more. There is no generic
CRUDRepository[Model] with get/list/update/delete, because that abstraction
tends to fit exactly one entity and then leak: the moment you need soft-delete
filtering, or a case-insensitive email lookup, or a count that ignores paging,
you write a bespoke method anyway.

The rule this file follows: repositories never commit. A commit is a decision
about a business operation ("the registration succeeded"), and that decision
belongs to the service. If repositories commit, a service can no longer make
two writes succeed or fail together.
"""

from __future__ import annotations

from sqlalchemy.orm import Session


class BaseRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, instance: object) -> None:
        """Stage an insert. Nothing hits the DB until flush or commit."""
        self.db.add(instance)

    def flush(self) -> None:
        """Send pending SQL now, without ending the transaction.

        Useful when you need a server-generated id inside the same unit of work
        but are not ready to commit.
        """
        self.db.flush()
