"""
Machine Learning Engine: end-to-end training pipeline.

Pipeline stages (see train_model() at the bottom, which orchestrates all of
this — this is the function app/services/ml_service.py and
scripts/train_model.py both call):

  1. Feature engineering  (app.ml.indicators.build_feature_matrix)
  2. Label construction    (next-day direction, for trend_classification)
  3. Walk-forward CV + Optuna hyperparameter search (no random K-fold — see
     app.ml.walk_forward for why)
  4. Refit on full history with the best hyperparameters found
  5. SHAP explainability on the final model
  6. Return everything the service layer needs to persist to the registry

Design decision: classification (not regression) is implemented fully here
for `trend_classification` because it is the task the Signal Engine actually
consumes (BUY/SELL/HOLD needs a class + probability, not a raw return
number). `next_day_return` (regression) uses the same feature pipeline and
walk-forward machinery with a swapped objective/metric set — implemented
below via `task`-conditional branching rather than a second parallel pipeline,
so the two tasks can never silently drift out of sync on feature engineering.
"""
import logging
from dataclasses import dataclass, field

import numpy as np
import optuna
import pandas as pd
from lightgbm import LGBMClassifier, LGBMRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)
from xgboost import XGBClassifier, XGBRegressor

from app.domain.enums import ModelAlgorithm, ModelTask
from app.ml.explain import ShapExplainer
from app.ml.indicators import FEATURE_COLUMNS, build_feature_matrix
from app.ml.walk_forward import walk_forward_splits

optuna.logging.set_verbosity(optuna.logging.WARNING)
logger = logging.getLogger(__name__)


@dataclass
class TrainingResult:
    model: object
    feature_names: list[str]
    best_params: dict
    metrics: dict
    top_features: list[dict] = field(default_factory=list)
    n_train_samples: int = 0
    n_test_samples: int = 0
    n_walk_forward_splits: int = 0


def build_labels(feat: pd.DataFrame, task: ModelTask) -> pd.Series:
    """
    Construct the prediction target.

    trend_classification: 1 if next bar's close > this bar's close, else 0.
    next_day_return:       (next_close - close) / close, a continuous return.

    Both are shifted by -1 (tomorrow's outcome attached to today's feature
    row) — the *last* row therefore has no label (we haven't seen tomorrow
    yet) and is dropped, which is also exactly the row used for live
    inference in ml_service.py.
    """
    next_close = feat["close"].shift(-1)
    if task == ModelTask.TREND_CLASSIFICATION:
        return (next_close > feat["close"]).astype(int)
    if task == ModelTask.NEXT_DAY_RETURN:
        return (next_close - feat["close"]) / feat["close"]
    raise NotImplementedError(f"Task {task} is not implemented in this training pipeline yet.")


def _make_estimator(algorithm: ModelAlgorithm, task: ModelTask, params: dict):
    is_classification = task == ModelTask.TREND_CLASSIFICATION
    if algorithm == ModelAlgorithm.XGBOOST:
        cls = XGBClassifier if is_classification else XGBRegressor
        return cls(
            **params,
            n_jobs=-1,
            random_state=42,
            eval_metric="logloss" if is_classification else "rmse",
        )
    if algorithm == ModelAlgorithm.LIGHTGBM:
        cls = LGBMClassifier if is_classification else LGBMRegressor
        return cls(**params, n_jobs=-1, random_state=42, verbosity=-1)
    if algorithm == ModelAlgorithm.RANDOM_FOREST:
        cls = RandomForestClassifier if is_classification else RandomForestRegressor
        return cls(**params, n_jobs=-1, random_state=42)
    raise NotImplementedError(f"Algorithm {algorithm} is not implemented.")


def _suggest_params(trial: optuna.Trial, algorithm: ModelAlgorithm) -> dict:
    if algorithm in (ModelAlgorithm.XGBOOST, ModelAlgorithm.LIGHTGBM):
        return {
            "n_estimators": trial.suggest_int("n_estimators", 50, 400),
            "max_depth": trial.suggest_int("max_depth", 2, 8),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "subsample": trial.suggest_float("subsample", 0.5, 1.0),
            # Both XGBoost and LightGBM accept `colsample_bytree`, so this key is
            # unconditional. It was previously written as a ternary whose two
            # branches were identical — dead logic that read as if the two
            # algorithms needed different parameter names.
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
        }
    # RandomForest
    return {
        "n_estimators": trial.suggest_int("n_estimators", 50, 400),
        "max_depth": trial.suggest_int("max_depth", 2, 16),
        "min_samples_leaf": trial.suggest_int("min_samples_leaf", 1, 10),
    }


def _score_fold(y_true, y_pred, y_proba, task: ModelTask) -> float:
    """Single scalar the Optuna objective maximizes: F1 for classification
    (robust to class imbalance in up/down day counts), negative RMSE for
    regression (so 'higher is better' holds for both tasks uniformly)."""
    if task == ModelTask.TREND_CLASSIFICATION:
        return f1_score(y_true, y_pred, zero_division=0)
    return -mean_squared_error(y_true, y_pred)


def _objective(
    trial: optuna.Trial,
    X: pd.DataFrame,
    y: pd.Series,
    algorithm: ModelAlgorithm,
    task: ModelTask,
    n_splits: int,
) -> float:
    params = _suggest_params(trial, algorithm)
    splits = walk_forward_splits(len(X), n_splits=n_splits)
    fold_scores = []
    for split in splits:
        model = _make_estimator(algorithm, task, params)
        X_train, y_train = X.iloc[split.train_idx], y.iloc[split.train_idx]
        X_test, y_test = X.iloc[split.test_idx], y.iloc[split.test_idx]
        model.fit(X_train, y_train)

        if task == ModelTask.TREND_CLASSIFICATION:
            y_pred = model.predict(X_test)
            y_proba = model.predict_proba(X_test)[:, 1]
        else:
            y_pred = model.predict(X_test)
            y_proba = None
        fold_scores.append(_score_fold(y_test, y_pred, y_proba, task))
    return float(np.mean(fold_scores))


def train_model(
    ohlcv: pd.DataFrame,
    task: ModelTask,
    algorithm: ModelAlgorithm,
    n_optuna_trials: int = 20,
    n_walk_forward_splits: int = 5,
) -> TrainingResult:
    """
    Full training pipeline entry point. `ohlcv` must be sorted ascending by
    timestamp with columns [timestamp, open, high, low, close, volume].
    """
    feat = build_feature_matrix(ohlcv)
    feat["label"] = build_labels(feat, task)

    # Drop warm-up NaNs (indicator windows) and the final unlabeled row.
    clean = feat.dropna(subset=[*FEATURE_COLUMNS, "label"]).reset_index(drop=True)
    if len(clean) < 60:
        raise ValueError(
            f"Only {len(clean)} usable rows after feature/label construction — "
            "need at least 60 for a meaningful walk-forward split. Load more history."
        )

    X = clean[FEATURE_COLUMNS]
    y = clean["label"]

    study = optuna.create_study(direction="maximize")
    study.optimize(
        lambda trial: _objective(trial, X, y, algorithm, task, n_walk_forward_splits),
        n_trials=n_optuna_trials,
        show_progress_bar=False,
    )
    best_params = study.best_params

    # Re-run walk-forward CV one final time with the *best* params to report
    # honest out-of-sample metrics (Optuna's internal best value is the same
    # number, but we recompute per-fold predictions here to build a full
    # metrics dict, not just the single scalar objective).
    splits = walk_forward_splits(len(X), n_splits=n_walk_forward_splits)
    all_y_true, all_y_pred, all_y_proba = [], [], []
    for split in splits:
        model = _make_estimator(algorithm, task, best_params)
        model.fit(X.iloc[split.train_idx], y.iloc[split.train_idx])
        X_test = X.iloc[split.test_idx]
        y_pred = model.predict(X_test)
        all_y_true.extend(y.iloc[split.test_idx].tolist())
        all_y_pred.extend(y_pred.tolist())
        if task == ModelTask.TREND_CLASSIFICATION:
            all_y_proba.extend(model.predict_proba(X_test)[:, 1].tolist())

    metrics = _compute_metrics(all_y_true, all_y_pred, all_y_proba, task)
    metrics["n_train_samples"] = len(X)
    metrics["n_test_samples"] = len(all_y_true)
    metrics["n_walk_forward_splits"] = len(splits)

    # Final production model: refit on the FULL history with the tuned
    # hyperparameters. This is standard practice — walk-forward CV exists to
    # pick hyperparameters and estimate generalization honestly, not to
    # withhold data from the model that actually gets deployed.
    final_model = _make_estimator(algorithm, task, best_params)
    final_model.fit(X, y)

    explainer = ShapExplainer(final_model, FEATURE_COLUMNS)
    top_features = explainer.global_importance(X.sample(min(len(X), 200), random_state=42))

    return TrainingResult(
        model=final_model,
        feature_names=FEATURE_COLUMNS,
        best_params=best_params,
        metrics=metrics,
        top_features=top_features,
        n_train_samples=len(X),
        n_test_samples=len(all_y_true),
        n_walk_forward_splits=len(splits),
    )


def _compute_metrics(y_true: list, y_pred: list, y_proba: list, task: ModelTask) -> dict:
    if task == ModelTask.TREND_CLASSIFICATION:
        metrics = {
            "accuracy": accuracy_score(y_true, y_pred),
            "precision": precision_score(y_true, y_pred, zero_division=0),
            "recall": recall_score(y_true, y_pred, zero_division=0),
            "f1": f1_score(y_true, y_pred, zero_division=0),
        }
        # ROC-AUC is undefined with only one class present in y_true (can
        # happen on short/degenerate test windows) — guard rather than crash.
        if y_proba and len(set(y_true)) > 1:
            metrics["roc_auc"] = roc_auc_score(y_true, y_proba)
        else:
            metrics["roc_auc"] = None
        return metrics
    return {
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "r2": float(r2_score(y_true, y_pred)) if len(set(y_true)) > 1 else None,
    }
