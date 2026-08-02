"""
ML lifecycle models: MLModel (registry), Prediction, Signal.

Design decision: `MLModel` is our lightweight, DB-backed model registry.
It tracks exactly what MLflow's model registry tracks (name, version, stage,
metrics, artifact location) but persists it in the same Postgres instance as
everything else, so a single query can join "which model produced this
prediction" -> "what were its validation metrics" -> "who trained it".
An MLflow tracking server can be layered on top later (see app/ml/registry.py)
without changing this schema — mlflow_run_id is reserved for exactly that.
"""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.enums import ModelAlgorithm, ModelStage, ModelTask, SignalAction
from app.models.base import GUID, IDMixin, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover
    # Imported for typing only. A runtime import would be circular
    # (market -> ... -> ml -> market); SQLAlchemy resolves the string form
    # "Stock" from its own class registry, so the annotation never needs the
    # real symbol at runtime. Declaring it under TYPE_CHECKING is what makes
    # the forward reference legible to linters and type checkers too — ruff
    # flagged it as F821 (undefined name) before this.
    from app.models.market import Stock


class MLModel(Base, IDMixin, TimestampMixin):
    __tablename__ = "ml_models"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    task: Mapped[ModelTask] = mapped_column(String(50), nullable=False)
    algorithm: Mapped[ModelAlgorithm] = mapped_column(String(50), nullable=False)
    stage: Mapped[ModelStage] = mapped_column(String(20), default=ModelStage.STAGING)

    artifact_path: Mapped[str] = mapped_column(String(500), nullable=False)
    hyperparameters: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)  # accuracy, f1, sharpe_uplift, etc.
    feature_names: Mapped[list] = mapped_column(JSON, default=list)
    mlflow_run_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:
        return f"<MLModel {self.name} v{self.version} [{self.stage}]>"


class Prediction(Base, IDMixin, TimestampMixin):
    __tablename__ = "predictions"

    model_id: Mapped[str] = mapped_column(GUID(), ForeignKey("ml_models.id", ondelete="CASCADE"))
    stock_id: Mapped[str] = mapped_column(GUID(), ForeignKey("stocks.id", ondelete="CASCADE"))

    predicted_value: Mapped[float] = mapped_column(Float, nullable=False)
    # For classification tasks this is the positive-class probability;
    # for regression tasks (next-day return) this is the predicted value itself.
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    shap_values: Mapped[dict] = mapped_column(JSON, default=dict)  # {feature_name: contribution}

    model: Mapped["MLModel"] = relationship()
    stock: Mapped["Stock"] = relationship()

    def __repr__(self) -> str:
        return f"<Prediction {self.stock_id} = {self.predicted_value:.4f}>"


class Signal(Base, IDMixin, TimestampMixin):
    __tablename__ = "signals"

    stock_id: Mapped[str] = mapped_column(GUID(), ForeignKey("stocks.id", ondelete="CASCADE"))
    prediction_id: Mapped[str | None] = mapped_column(
        GUID(), ForeignKey("predictions.id", ondelete="SET NULL"), nullable=True
    )

    action: Mapped[SignalAction] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)  # 0 (low) - 1 (high)

    supporting_indicators: Mapped[dict] = mapped_column(JSON, default=dict)
    explanation: Mapped[str] = mapped_column(String(2000), default="")
    llm_explanation: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # ^ populated by the Phase-2 LLM copilot; NULL until that module is wired up

    stock: Mapped["Stock"] = relationship()
    prediction: Mapped["Prediction | None"] = relationship()

    def __repr__(self) -> str:
        return f"<Signal {self.stock_id} {self.action} ({self.confidence:.0%})>"
