"""
ML Service: orchestrates the training pipeline (app.ml.train) and inference
against the DB-backed model registry (app.ml.registry).

This layer turns "a pure function that trains a model" into "a platform
capability" — pulling price history from the repository, persisting the
resulting MLModel/Prediction rows, and promoting new models to production when
they are the first of their kind.

CHANGE LOG (v2.0):
  - `triggered_by` (a user id) removed from every signature.
  - BUG FIX: production-model lookup is now scoped by model NAME as well as
    task. Previously `get_production_model(task)` returned the newest production
    model for the task regardless of which symbol it was trained on — so a
    prediction for TCS could be served by the RELIANCE model, with no error and
    a plausible-looking confidence score. This was the most serious correctness
    defect in the ML path, and there is now a regression test for it
    (tests/test_stocks_api.py::test_a_models_predictions_are_scoped_to_its_own_symbol).
  - ADDED `forecast()` (multi-day price path with confidence bands) and
    `prediction_history()`, which back the Prediction page's forecast chart and
    accuracy panel. Both were rendered from literals in the old UI.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import InsufficientDataException, ModelNotTrainedException, NotFoundException
from app.domain.enums import AuditAction, ModelAlgorithm, ModelStage, ModelTask
from app.ml.explain import ShapExplainer
from app.ml.indicators import FEATURE_COLUMNS, build_feature_matrix
from app.ml.registry import generate_model_name, load_artifact, save_artifact, try_log_to_mlflow
from app.ml.train import train_model
from app.models.ml import MLModel, Prediction
from app.repositories.market_repository import PriceRepository, StockRepository
from app.repositories.ml_repository import MLModelRepository, PredictionRepository
from app.services.audit_service import AuditService


class MLService:
    def __init__(self, db: Session):
        self.db = db
        self.stocks = StockRepository(db)
        self.prices = PriceRepository(db)
        self.ml_models = MLModelRepository(db)
        self.predictions = PredictionRepository(db)
        self.audit = AuditService(db)

    def train_for_symbol(
        self,
        symbol: str,
        task: ModelTask,
        algorithm: ModelAlgorithm,
        n_optuna_trials: int,
        n_walk_forward_splits: int,
    ) -> MLModel:
        stock = self.stocks.get_by_symbol(symbol)
        if not stock:
            raise NotFoundException(f"Stock {symbol} not found")

        ohlcv = self.prices.get_price_series(stock.id, limit=5000)
        if len(ohlcv) < 100:
            raise InsufficientDataException(
                f"Only {len(ohlcv)} price bars loaded for {symbol}; need at least ~100 for training."
            )

        result = train_model(
            ohlcv=ohlcv,
            task=task,
            algorithm=algorithm,
            n_optuna_trials=n_optuna_trials,
            n_walk_forward_splits=n_walk_forward_splits,
        )

        name = generate_model_name(symbol, task)
        version = self.ml_models.get_latest_version(name) + 1
        artifact_path = save_artifact(result.model, name, version)

        mlflow_run_id = try_log_to_mlflow(
            run_name=f"{name}_v{version}",
            task=task,
            algorithm=algorithm,
            params=result.best_params,
            metrics={k: v for k, v in result.metrics.items() if isinstance(v, (int, float))},
            artifact_path=artifact_path,
        )

        ml_model = MLModel(
            name=name,
            version=version,
            task=task,
            algorithm=algorithm,
            stage=ModelStage.STAGING,
            artifact_path=artifact_path,
            hyperparameters=result.best_params,
            metrics=result.metrics,
            feature_names=result.feature_names,
            mlflow_run_id=mlflow_run_id,
            trained_at=datetime.now(timezone.utc),
        )
        ml_model = self.ml_models.create(ml_model)

        # First model ever trained for this task goes straight to production;
        # later versions require an explicit promotion call (see
        # MLModelRepository.promote_to_production), so a newly trained but
        # unevaluated model can't silently start serving live signals.
        if self.ml_models.get_production_model(task, name=name) is None:
            ml_model = self.ml_models.promote_to_production(ml_model)

        self.audit.log(
            action=AuditAction.MODEL_TRAINED,
            resource=f"ml_model:{ml_model.id}",
            detail={"symbol": symbol, "task": task.value, "algorithm": algorithm.value, "metrics": result.metrics},
        )

        # Stash top_features on the returned object for the API layer without
        # adding a column we don't otherwise need to persist redundantly —
        # SHAP importances are cheap to recompute but expensive to keep
        # migrating the schema for, so we surface them via this transient
        # attribute rather than a DB column.
        ml_model._top_features = result.top_features
        return ml_model

    def predict_latest(
        self, symbol: str, task: ModelTask = ModelTask.TREND_CLASSIFICATION, model_id: uuid.UUID | None = None
    ) -> Prediction:
        stock = self.stocks.get_by_symbol(symbol)
        if not stock:
            raise NotFoundException(f"Stock {symbol} not found")

        # Scoped by name (which encodes the symbol) — see module CHANGE LOG.
        expected_name = generate_model_name(symbol, task)
        ml_model = (
            self.ml_models.get(model_id) if model_id
            else self.ml_models.get_production_model(task, name=expected_name)
        )
        if not ml_model:
            raise ModelNotTrainedException(
                f"No trained model is available for {symbol.upper()} ({task.value}). "
                "Train one from the Prediction page first.",
                context={"symbol": symbol.upper(), "task": task.value},
            )

        ohlcv = self.prices.get_price_series(stock.id, limit=500)
        if ohlcv.empty:
            raise InsufficientDataException(f"No price history for {symbol}")

        feat = build_feature_matrix(ohlcv)
        latest_row = feat.dropna(subset=FEATURE_COLUMNS).tail(1)
        if latest_row.empty:
            raise InsufficientDataException(
                f"Not enough history for {symbol} to compute all indicators (need enough bars "
                "to clear every warm-up window, e.g. 50+ for SMA-50)."
            )

        model_obj = load_artifact(ml_model.artifact_path)
        X = latest_row[FEATURE_COLUMNS]

        if task == ModelTask.TREND_CLASSIFICATION:
            proba = model_obj.predict_proba(X)[0, 1]
            predicted_value = float(proba)
            confidence = float(max(proba, 1 - proba))
        else:
            predicted_value = float(model_obj.predict(X)[0])
            confidence = 0.5  # regression tasks don't have a natural [0,1] confidence; see docs

        explainer = ShapExplainer(model_obj, FEATURE_COLUMNS)
        contributions = explainer.explain_single(X)

        prediction = Prediction(
            model_id=ml_model.id,
            stock_id=stock.id,
            predicted_value=predicted_value,
            confidence=confidence,
            shap_values={c["feature"]: c["contribution"] for c in contributions},
        )
        prediction = self.predictions.create(prediction)
        prediction._shap_contributions = contributions
        prediction._model = ml_model
        return prediction

    # --- v2.0 additions ---------------------------------------------------------
    def prediction_history(self, symbol: str, limit: int = 50) -> list[dict]:
        """
        Past predictions for a symbol, each scored against what the price
        actually did next — the Prediction page's accuracy panel.

        A prediction is only marked correct/incorrect when a LATER bar exists to
        check it against; pending ones return `correct=None` rather than being
        silently counted as correct, which is how prediction dashboards end up
        quoting impossible accuracy figures.
        """
        stock = self.stocks.get_by_symbol(symbol)
        if not stock:
            raise NotFoundException(f"Stock {symbol.upper()} not found")

        records = self.predictions.list_for_stock(stock.id, limit=limit)
        bars = self.prices.list_bars(stock.id, limit=1000)
        by_time = sorted(((b.timestamp, b.close) for b in bars), key=lambda x: x[0])

        out: list[dict] = []
        for record in records:
            created = record.created_at.replace(tzinfo=None) if record.created_at.tzinfo else record.created_at
            before = [c for t, c in by_time if t <= created]
            after = [c for t, c in by_time if t > created]

            actual_direction = None
            correct = None
            if before and after:
                actual_direction = 1 if after[0] > before[-1] else 0
                correct = actual_direction == (1 if record.predicted_value >= 0.5 else 0)

            out.append({
                "id": record.id,
                "model_name": record.model.name if record.model else "",
                "model_version": record.model.version if record.model else 0,
                "predicted_value": record.predicted_value,
                "confidence": record.confidence,
                "actual_direction": actual_direction,
                "correct": correct,
                "generated_at": record.created_at,
            })
        return out

    def forecast(self, symbol: str, horizon_days: int = 5) -> dict:
        """
        Multi-day price path with confidence bands.

        Drift comes from the trained classifier's next-day probability, so the
        forecast genuinely reflects the model rather than just history; band
        width comes from realized volatility scaled by sqrt(t), the standard
        random-walk uncertainty growth. When no model exists the drift term is
        zero and `model_informed` is False — the response states which it is
        instead of presenting an unconditional random walk as a prediction.
        """
        import math

        stock = self.stocks.get_by_symbol(symbol)
        if not stock:
            raise NotFoundException(f"Stock {symbol.upper()} not found")

        df = self.prices.get_price_series(stock.id, limit=400)
        if len(df) < 30:
            raise InsufficientDataException(
                f"Need at least 30 price bars to build a forecast for {symbol.upper()}."
            )

        closes = df["close"]
        last_price = float(closes.iloc[-1])
        sigma = float(closes.pct_change().dropna().std())

        probability = None
        model_informed = False
        try:
            prediction = self.predict_latest(symbol, task=ModelTask.TREND_CLASSIFICATION)
            probability = float(prediction.predicted_value)
            model_informed = True
        except (ModelNotTrainedException, InsufficientDataException):
            # Expected on a symbol with no model yet — degrade, do not fail.
            pass

        # Map P(up) in [0,1] onto a daily drift bounded by one historical
        # standard deviation: a model that is 100% confident still cannot move
        # the forecast further than realized volatility justifies.
        drift = ((probability - 0.5) * 2 * sigma) if probability is not None else 0.0

        points = []
        price = last_price
        for day in range(1, horizon_days + 1):
            price = price * (1 + drift)
            spread = sigma * math.sqrt(day) * 1.96  # 95% band
            points.append({
                "day": day, "expected": price,
                "lower": price * (1 - spread), "upper": price * (1 + spread),
            })

        return {
            "symbol": stock.symbol,
            "last_price": last_price,
            "horizon_days": horizon_days,
            "model_informed": model_informed,
            "probability_up": probability,
            "daily_volatility": sigma,
            "annualized_volatility": sigma * math.sqrt(252),
            "expected_return_pct": (points[-1]["expected"] / last_price - 1.0) if points else 0.0,
            "expected_price": points[-1]["expected"] if points else last_price,
            "historical": [
                {"timestamp": ts, "close": float(c)}
                for ts, c in zip(df["timestamp"].tail(60), closes.tail(60))
            ],
            "forecast": points,
        }
