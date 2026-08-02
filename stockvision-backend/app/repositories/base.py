"""
Generic repository base class.

This is the Repository Pattern's payoff — services depend on this interface,
never on `Session` or raw SQL. Swapping SQLite for Postgres, or the ORM
entirely, means touching this file and its subclasses only.

CHANGE LOG (v2.0):
  - ADDED `create_many` and an explicit `commit` flag. The old `create()`
    committed on every call, so seeding 5,000 price bars issued 5,000
    transactions; batch paths now commit once.
  - ADDED `count()` and `exists()` so callers stop pulling entire tables into
    Python just to call `len()` — the previous pattern in several services.

BUG FIX (caught by the CI import check, not by review): this class defines a
method named `list`, which shadows the `list` builtin FOR THE REST OF THE CLASS
BODY. Every subsequent `-> list[ModelType]` annotation therefore resolved to
that method object and raised `TypeError: 'function' object is not
subscriptable` at import time — the module could not be imported at all.
`from __future__ import annotations` makes annotations lazy strings, which fixes
it properly rather than by renaming a public method. It is safe here because
nothing introspects these annotations at runtime (unlike app/models/, where
SQLAlchemy genuinely evaluates `Mapped[...]`).
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    def __init__(self, db: Session, model: type[ModelType]) -> None:
        self.db = db
        self.model = model

    def get(self, id_: uuid.UUID | str) -> ModelType | None:
        return self.db.get(self.model, id_)

    def list(self, skip: int = 0, limit: int = 100) -> list[ModelType]:
        stmt = select(self.model).offset(skip).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def count(self) -> int:
        return int(self.db.execute(select(func.count()).select_from(self.model)).scalar_one())

    def exists(self, **filters: Any) -> bool:
        stmt = select(func.count()).select_from(self.model)
        for key, value in filters.items():
            stmt = stmt.where(getattr(self.model, key) == value)
        return int(self.db.execute(stmt).scalar_one()) > 0

    def create(self, obj: ModelType, *, commit: bool = True) -> ModelType:
        self.db.add(obj)
        if commit:
            self.db.commit()
            self.db.refresh(obj)
        else:
            self.db.flush()
        return obj

    def create_many(self, objs: Sequence[ModelType], *, commit: bool = True) -> list[ModelType]:
        self.db.add_all(objs)
        if commit:
            self.db.commit()
        else:
            self.db.flush()
        return list(objs)

    def update(self, obj: ModelType, **fields: Any) -> ModelType:
        for key, value in fields.items():
            setattr(obj, key, value)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def delete(self, obj: ModelType, *, commit: bool = True) -> None:
        self.db.delete(obj)
        if commit:
            self.db.commit()
