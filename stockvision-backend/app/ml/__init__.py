"""Machine-learning pipeline: features, training, registry and explanations."""
from app.ml.native import ensure_openmp_runtime

# Before any submodule imports LightGBM or unpickles a LightGBM model.
ensure_openmp_runtime()
