"""Re-export every model.

This file is load-bearing twice over:

1. SQLAlchemy resolves relationship targets by class name at mapper-configure
   time. Splitting models across files only works if every file has been
   imported first - importing this package does that.
2. Alembic's autogenerate compares Base.metadata against the live database. A
   model class that was never imported is not in the metadata, and autogenerate
   will happily write a migration that DROPS its table.

So: new model file -> add it here, immediately.
"""

from app.db.base import Base
from app.db.models.project import Project
from app.db.models.tag import Tag, task_tags
from app.db.models.task import Comment, Task, TaskHistory
from app.db.models.user import User

__all__ = [
    "Base",
    "Comment",
    "Project",
    "Tag",
    "Task",
    "TaskHistory",
    "User",
    "task_tags",
]
