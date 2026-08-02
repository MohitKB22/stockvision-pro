import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import ModelAlgorithm, ModelStage, ModelTask, SignalAction


class TrainModelRequest(BaseModel):
    symbol: str
    task: ModelTask = ModelTask.TREND_CLASSIFICATION
    algorithm: ModelAlgorithm = ModelAlgorithm.XGBOOST
    n_optuna_trials: int = Field(default=20, ge=1, le=200)
    n_walk_forward_splits: int = Field(default=5, ge=2, le=20)


class ModelMetrics(BaseModel):
    accuracy: float | None = None
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    roc_auc: float | None = None
    rmse: float | None = None
    mae: float | None = None
    r2: float | None = None
    n_train_samples: int
    n_test_samples: int
    n_walk_forward_splits: int


class TrainModelResponse(BaseModel):
    # `model_` is a protected Pydantic v2 namespace; these field names are part
    # of the public API contract, so we opt out of the guard rather than rename.
    model_config = ConfigDict(protected_namespaces=())

    model_id: uuid.UUID
    name: str
    version: int
    task: ModelTask
    algorithm: ModelAlgorithm
    stage: ModelStage
    best_hyperparameters: dict
    metrics: ModelMetrics
    top_features: list[dict]  # [{feature, mean_abs_shap}], sorted desc
    trained_at: datetime


class PredictionRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    symbol: str
    model_id: uuid.UUID | None = None  # defaults to latest PRODUCTION model for the task
    task: ModelTask = ModelTask.TREND_CLASSIFICATION


class ShapContribution(BaseModel):
    feature: str
    value: float
    contribution: float  # signed SHAP value for this prediction


class PredictionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: uuid.UUID
    stock_symbol: str
    model_name: str
    model_version: int
    predicted_value: float
    confidence: float
    shap_contributions: list[ShapContribution]
    generated_at: datetime


class SignalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    stock_symbol: str
    action: SignalAction
    confidence: float
    risk_score: float
    supporting_indicators: dict
    explanation: str
    llm_explanation: str | None
    shap_contributions: list[ShapContribution]
    generated_at: datetime


# --- v2.0 additions ------------------------------------------------------------
class ModelPublic(BaseModel):
    """A registry entry, as shown on the Prediction page's model table."""
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: uuid.UUID
    name: str
    version: int
    task: ModelTask
    algorithm: ModelAlgorithm
    stage: ModelStage
    metrics: dict
    hyperparameters: dict
    feature_count: int
    trained_at: datetime


class PredictionHistoryEntry(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: uuid.UUID
    model_name: str
    model_version: int
    predicted_value: float
    confidence: float
    actual_direction: int | None = Field(
        default=None, description="1 = price rose, 0 = fell, null = not yet verifiable."
    )
    correct: bool | None = Field(
        default=None,
        description="null when no later bar exists to score against — never counted as correct.",
    )
    generated_at: datetime


class ForecastPoint(BaseModel):
    day: int
    expected: float
    lower: float
    upper: float


class ForecastHistoricalPoint(BaseModel):
    timestamp: datetime
    close: float


class ForecastResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    symbol: str
    last_price: float
    horizon_days: int
    model_informed: bool = Field(
        description="False means no trained model contributed drift — the path is a pure random walk."
    )
    probability_up: float | None
    daily_volatility: float
    annualized_volatility: float
    expected_return_pct: float
    expected_price: float
    historical: list[ForecastHistoricalPoint]
    forecast: list[ForecastPoint]
