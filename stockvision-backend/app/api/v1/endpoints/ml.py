"""
Machine Learning & Signal endpoints.

CHANGE LOG (v2.0): auth removed. Added the forecast, prediction-history,
bulk-signal and model-registry endpoints the Prediction page and dashboard need —
previously the frontend had no way to read the registry at all, and generated
signals one HTTP request per symbol.
"""
from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import NotFoundException
from app.domain.enums import AuditAction, ModelStage
from app.repositories.market_repository import StockRepository
from app.repositories.ml_repository import MLModelRepository, SignalRepository
from app.schemas.ml import (
    ForecastResponse,
    ModelMetrics,
    ModelPublic,
    PredictionHistoryEntry,
    PredictionRequest,
    PredictionResponse,
    ShapContribution,
    SignalResponse,
    TrainModelRequest,
    TrainModelResponse,
)
from app.services.audit_service import AuditService
from app.services.ml_service import MLService
from app.services.signal_service import SignalService

router = APIRouter(tags=["Machine Learning & Signals"])


def _signal_response(signal, symbol: str) -> SignalResponse:
    return SignalResponse(
        id=signal.id,
        stock_symbol=symbol.upper(),
        action=signal.action,
        confidence=signal.confidence,
        risk_score=signal.risk_score,
        supporting_indicators=signal.supporting_indicators,
        explanation=signal.explanation,
        llm_explanation=signal.llm_explanation,
        shap_contributions=[ShapContribution(**c) for c in getattr(signal, "_shap_contributions", [])],
        generated_at=signal.created_at,
    )


def _model_public(model) -> ModelPublic:
    return ModelPublic(
        id=model.id, name=model.name, version=model.version, task=model.task,
        algorithm=model.algorithm, stage=ModelStage(model.stage),
        metrics=model.metrics or {}, hyperparameters=model.hyperparameters or {},
        feature_count=len(model.feature_names or []), trained_at=model.trained_at,
    )


# --- Model registry ------------------------------------------------------------
@router.get("/models", response_model=list[ModelPublic], summary="Model registry")
def list_models(limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)):
    return [_model_public(m) for m in MLModelRepository(db).list_models(limit=limit)]


@router.post("/models/train", response_model=TrainModelResponse, summary="Train a model version")
def train_model_endpoint(payload: TrainModelRequest, db: Session = Depends(get_db)):
    """
    Walk-forward CV + Optuna hyperparameter search + SHAP importances
    (app/ml/train.py), persisted to the DB-backed registry.

    Synchronous by design at this scale: training on the seeded history takes
    seconds, and an async job would add a queue, a polling endpoint and a status
    model for no user-visible benefit. For production-scale datasets the Celery
    task in app/worker.py is the intended path — documented rather than pretended.
    """
    model = MLService(db).train_for_symbol(
        symbol=payload.symbol,
        task=payload.task,
        algorithm=payload.algorithm,
        n_optuna_trials=payload.n_optuna_trials,
        n_walk_forward_splits=payload.n_walk_forward_splits,
    )
    return TrainModelResponse(
        model_id=model.id, name=model.name, version=model.version, task=model.task,
        algorithm=model.algorithm, stage=model.stage,
        best_hyperparameters=model.hyperparameters,
        metrics=ModelMetrics(**model.metrics),
        top_features=getattr(model, "_top_features", []),
        trained_at=model.trained_at,
    )


@router.post("/models/{model_id}/promote", response_model=ModelPublic, summary="Promote to production")
def promote_model(model_id: str, db: Session = Depends(get_db)):
    repo = MLModelRepository(db)
    model = repo.get(model_id)
    if not model:
        raise NotFoundException("Model version not found")
    return _model_public(repo.promote_to_production(model))


# --- Inference -------------------------------------------------------------------
@router.post("/predictions", response_model=PredictionResponse, summary="Predict from the latest bar")
def predict(payload: PredictionRequest, db: Session = Depends(get_db)):
    prediction = MLService(db).predict_latest(
        payload.symbol, task=payload.task, model_id=payload.model_id
    )
    model = getattr(prediction, "_model", None)
    AuditService(db).log(
        action=AuditAction.PREDICTION_REQUEST,
        resource=f"prediction:{prediction.id}",
        detail={"symbol": payload.symbol.upper(), "task": payload.task.value},
    )
    return PredictionResponse(
        id=prediction.id,
        stock_symbol=payload.symbol.upper(),
        model_name=model.name if model else "",
        model_version=model.version if model else 0,
        predicted_value=prediction.predicted_value,
        confidence=prediction.confidence,
        shap_contributions=[
            ShapContribution(**c) for c in getattr(prediction, "_shap_contributions", [])
        ],
        generated_at=prediction.created_at,
    )


@router.get("/predictions/{symbol}/history", response_model=list[PredictionHistoryEntry],
            summary="Past predictions scored against outcomes")
def prediction_history(
    symbol: str, limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)
):
    """
    Predictions with no subsequent bar to verify against return `correct: null` —
    never counted as correct, which is how accuracy dashboards end up quoting
    impossible numbers.
    """
    return MLService(db).prediction_history(symbol, limit=limit)


@router.get("/predictions/{symbol}/forecast", response_model=ForecastResponse,
            summary="Multi-day price forecast with confidence bands")
def forecast(
    symbol: str,
    horizon_days: int = Query(default=5, ge=1, le=60),
    db: Session = Depends(get_db),
):
    return MLService(db).forecast(symbol, horizon_days=horizon_days)


# --- Signals -----------------------------------------------------------------------
@router.get("/signals/recent", response_model=list[SignalResponse], summary="Recently generated signals")
def recent_signals(limit: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db)):
    """
    Declared BEFORE POST /signals/{symbol} would shadow it: FastAPI matches routes
    in registration order, and a literal path must be registered ahead of a
    same-shaped parameterised one.
    """
    return [
        _signal_response(s, s.stock.symbol if s.stock else "")
        for s in SignalRepository(db).list_recent(limit=limit)
    ]


@router.post("/signals", response_model=list[SignalResponse], summary="Generate signals in bulk")
def generate_signals_bulk(
    symbols: list[str] = Body(embed=True, max_length=25), db: Session = Depends(get_db)
):
    """
    One request for the dashboard's whole signal panel. Symbols that fail are
    skipped rather than failing the batch.
    """
    signals = SignalService(db).generate_bulk([s.upper() for s in symbols])
    stocks = {s.id: s for s in StockRepository(db).get_many_by_symbols(symbols)}
    return [
        _signal_response(s, stocks[s.stock_id].symbol if s.stock_id in stocks else "")
        for s in signals
    ]


@router.post("/signals/{symbol}", response_model=SignalResponse, summary="Generate an AI signal")
def generate_signal(symbol: str, db: Session = Depends(get_db)):
    """
    Blends technical-indicator rules with the ML model's probability into one
    BUY/SELL/HOLD call. Degrades to indicators-only when no model is trained.
    """
    signal = SignalService(db).generate_signal(symbol)
    AuditService(db).log(
        action=AuditAction.SIGNAL_REQUEST,
        resource=f"signal:{signal.id}",
        detail={"symbol": symbol.upper(), "action": str(signal.action)},
    )
    return _signal_response(signal, symbol)
