"""
Model registry: persists trained model artifacts + metadata.

Design decision: the *source of truth* for "what models exist, what are
their metrics, which one is in production" is the `ml_models` Postgres table
(via MLModelRepository) — not MLflow. This means the rest of the platform
(prediction serving, the signals API) only ever depends on Postgres, which is
already a required piece of infrastructure, rather than also requiring an
MLflow tracking server to be up for basic model serving to work.

MLflow integration is additive: if `mlflow` is installed and
MLFLOW_TRACKING_URI is reachable, every training run is *also* logged there
for the experiment-comparison UI the brief asks for. If it isn't reachable
(e.g. no tracking server running, as in this sandbox), training still
succeeds — MLflow logging failures are caught and logged as a warning, never
allowed to fail the actual training job.
"""
import io
import logging
import threading
from collections import OrderedDict
from pathlib import Path

import joblib
from sqlalchemy.orm import Session

from app.core.storage import StorageCategory, is_database_locator, read_file, save_file
from app.domain.enums import ModelAlgorithm, ModelTask

logger = logging.getLogger(__name__)

# Artifacts are immutable once written (a retrain creates a new version, i.e. a
# new locator), so deserialized models can be cached safely. Without this every
# prediction re-read and re-unpickled the artifact — from the database, on hosts
# that use database storage.
_ARTIFACT_CACHE: OrderedDict[str, object] = OrderedDict()
_ARTIFACT_CACHE_SIZE = 8
_CACHE_LOCK = threading.Lock()


def save_artifact(db: Session, model_obj, name: str, version: int) -> str:
    """Serializes a trained model through app.core.storage; returns its locator.
    Compressed: a 400-tree random forest drops from ~11 MB to ~2.3 MB."""
    buffer = io.BytesIO()
    joblib.dump(model_obj, buffer, compress=3)
    return save_file(db, StorageCategory.MODEL, f"{name}_v{version}.joblib", buffer.getvalue())


def load_artifact(db: Session, locator: str):
    """Raises FileNotFoundError if the artifact's bytes no longer exist."""
    with _CACHE_LOCK:
        if locator in _ARTIFACT_CACHE:
            _ARTIFACT_CACHE.move_to_end(locator)
            return _ARTIFACT_CACHE[locator]
    model_obj = joblib.load(io.BytesIO(read_file(db, locator)))
    with _CACHE_LOCK:
        _ARTIFACT_CACHE[locator] = model_obj
        while len(_ARTIFACT_CACHE) > _ARTIFACT_CACHE_SIZE:
            _ARTIFACT_CACHE.popitem(last=False)
    return model_obj


def clear_artifact_cache() -> None:
    with _CACHE_LOCK:
        _ARTIFACT_CACHE.clear()


def try_log_to_mlflow(
    *,
    run_name: str,
    task: ModelTask,
    algorithm: ModelAlgorithm,
    params: dict,
    metrics: dict,
    artifact_path: str,
) -> str | None:
    """
    Best-effort MLflow experiment logging. Returns the mlflow run_id on
    success, or None if mlflow isn't installed / no tracking server is
    reachable — this must never raise, since training succeeds either way.
    """
    try:
        import mlflow
    except ImportError:
        logger.info("mlflow not installed — skipping experiment logging (model registry still works via Postgres).")
        return None

    try:
        mlflow.set_experiment("stockvision-pro")
        with mlflow.start_run(run_name=run_name) as run:
            mlflow.log_params({**params, "task": task.value, "algorithm": algorithm.value})
            mlflow.log_metrics({k: v for k, v in metrics.items() if isinstance(v, int | float)})
            # Only a real file can be attached; database-stored artifacts are
            # still fully tracked through the registry table.
            if not is_database_locator(artifact_path) and Path(artifact_path).exists():
                mlflow.log_artifact(artifact_path)
            return run.info.run_id
    except Exception as exc:
        logger.warning("MLflow logging skipped (tracking server unreachable?): %s", exc)
        return None


def generate_model_name(symbol: str, task: ModelTask) -> str:
    return f"{symbol.upper()}_{task.value}"
