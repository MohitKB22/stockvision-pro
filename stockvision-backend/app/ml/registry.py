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
import logging
from pathlib import Path

import joblib

from app.core.config import settings
from app.domain.enums import ModelAlgorithm, ModelTask

logger = logging.getLogger(__name__)


def artifact_path_for(name: str, version: int) -> Path:
    directory = Path(settings.MODEL_ARTIFACT_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{name}_v{version}.joblib"


def save_artifact(model_obj, name: str, version: int) -> str:
    path = artifact_path_for(name, version)
    joblib.dump(model_obj, path)
    return str(path)


def load_artifact(path: str):
    return joblib.load(path)


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
            mlflow.log_metrics({k: v for k, v in metrics.items() if isinstance(v, (int, float))})
            mlflow.log_artifact(artifact_path)
            return run.info.run_id
    except Exception as exc:
        logger.warning("MLflow logging skipped (tracking server unreachable?): %s", exc)
        return None


def generate_model_name(symbol: str, task: ModelTask) -> str:
    return f"{symbol.upper()}_{task.value}"
