"""
ML registry repositories.

CHANGE LOG (v2.0):
  - `get_production_model` was scoped by task ONLY, which is a real correctness
    bug in a multi-symbol platform: a production model trained on RELIANCE would
    be served for a TCS prediction request, with no error and a plausible
    confidence score. Models are now scoped by (name, task), where name encodes
    the symbol.
  - ADDED `list_predictions_for_stock`, `get_latest_bulk` and `list_recent`,
    which back the prediction page's history panel and the dashboard's signal feed.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.domain.enums import ModelStage, ModelTask
from app.models.ml import MLModel, Prediction, Signal
from app.repositories.base import BaseRepository


class MLModelRepository(BaseRepository[MLModel]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, MLModel)

    def get_latest_version(self, name: str) -> int:
        latest = self.db.execute(
            select(MLModel).where(MLModel.name == name).order_by(MLModel.version.desc()).limit(1)
        ).scalar_one_or_none()
        return latest.version if latest else 0

    def get_production_model(self, task: ModelTask, name: str | None = None) -> MLModel | None:
        """
        The model that should serve live predictions.

        Bug fix: `name` (which encodes the symbol, e.g.
        "RELIANCE_trend_classification") is now part of the lookup. Without it
        the newest PRODUCTION model for the task was returned regardless of
        which symbol it was trained on.
        """
        stmt = select(MLModel).where(MLModel.task == task, MLModel.stage == ModelStage.PRODUCTION)
        if name:
            stmt = stmt.where(MLModel.name == name)
        return self.db.execute(stmt.order_by(MLModel.version.desc()).limit(1)).scalar_one_or_none()

    def list_models(self, limit: int = 100) -> list[MLModel]:
        return list(
            self.db.execute(
                select(MLModel).order_by(MLModel.trained_at.desc()).limit(limit)
            ).scalars().all()
        )

    def promote_to_production(self, model: MLModel) -> MLModel:
        """Archive the incumbent for the same (name, task), then promote this one."""
        self.db.query(MLModel).filter(
            MLModel.task == model.task,
            MLModel.name == model.name,
            MLModel.stage == ModelStage.PRODUCTION,
            MLModel.id != model.id,
        ).update({"stage": ModelStage.ARCHIVED}, synchronize_session=False)
        model.stage = ModelStage.PRODUCTION
        self.db.commit()
        self.db.refresh(model)
        return model


class PredictionRepository(BaseRepository[Prediction]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, Prediction)

    def list_for_stock(self, stock_id: uuid.UUID, limit: int = 50) -> list[Prediction]:
        return list(
            self.db.execute(
                select(Prediction)
                .options(selectinload(Prediction.model))
                .where(Prediction.stock_id == stock_id)
                .order_by(Prediction.created_at.desc())
                .limit(limit)
            ).scalars().all()
        )


class SignalRepository(BaseRepository[Signal]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, Signal)

    def get_latest_for_stock(self, stock_id: uuid.UUID) -> Signal | None:
        return self.db.execute(
            select(Signal)
            .where(Signal.stock_id == stock_id)
            .order_by(Signal.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    def get_latest_bulk(self, stock_ids: list[uuid.UUID]) -> dict[uuid.UUID, Signal]:
        """Latest signal per stock in one pass — the dashboard's 'Top AI Signals'
        card needs 6-10 of these and used to issue one query each."""
        if not stock_ids:
            return {}
        rows = self.db.execute(
            select(Signal)
            .where(Signal.stock_id.in_(stock_ids))
            .order_by(Signal.stock_id, Signal.created_at.desc())
        ).scalars().all()
        latest: dict[uuid.UUID, Signal] = {}
        for row in rows:
            latest.setdefault(row.stock_id, row)
        return latest

    def list_recent(self, limit: int = 20) -> list[Signal]:
        return list(
            self.db.execute(
                select(Signal)
                .options(selectinload(Signal.stock))
                .order_by(Signal.created_at.desc())
                .limit(limit)
            ).scalars().all()
        )
