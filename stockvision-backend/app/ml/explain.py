"""
Explainable AI: SHAP wrapper for tree-based models.

Design decision: we use shap.TreeExplainer specifically (not KernelExplainer
or the generic shap.Explainer auto-selector) because it's exact and fast for
tree ensembles (XGBoost/LightGBM/RandomForest) — no sampling approximation,
no background-dataset choice to worry about, and it's what the brief's
"SHAP" + "Feature Importance" + "Prediction Explanation" requirements
actually need for these model types.
"""
import numpy as np
import pandas as pd
import shap


class ShapExplainer:
    def __init__(self, model, feature_names: list[str]):
        self.feature_names = feature_names
        self._explainer = shap.TreeExplainer(model)

    def global_importance(self, X: pd.DataFrame) -> list[dict]:
        """Mean |SHAP value| per feature across a dataset — 'what does this
        model rely on overall', used for the model card / training report."""
        shap_values = self._explainer.shap_values(X)
        shap_values = self._as_positive_class_array(shap_values)
        mean_abs = np.abs(shap_values).mean(axis=0)
        ranked = sorted(
            zip(self.feature_names, mean_abs), key=lambda pair: pair[1], reverse=True
        )
        return [{"feature": name, "mean_abs_shap": float(val)} for name, val in ranked]

    def explain_single(self, x_row: pd.DataFrame) -> list[dict]:
        """Per-prediction SHAP contributions — 'why did the model say this
        for THIS stock, right now', used in the Signal/Prediction API responses."""
        shap_values = self._explainer.shap_values(x_row)
        shap_values = self._as_positive_class_array(shap_values)
        row_values = shap_values[0]
        contributions = [
            {
                "feature": name,
                "value": float(x_row.iloc[0][name]),
                "contribution": float(contribution),
            }
            for name, contribution in zip(self.feature_names, row_values)
        ]
        return sorted(contributions, key=lambda c: abs(c["contribution"]), reverse=True)

    @staticmethod
    def _as_positive_class_array(shap_values) -> np.ndarray:
        """
        Normalizes shap's output across library/version quirks: binary
        classifiers can return either a single array or a
        [n_samples, n_features, n_classes] array / a list of two arrays
        (one per class) depending on the shap version and model backend.
        We always want the positive-class (index 1) contributions.
        """
        if isinstance(shap_values, list):
            return shap_values[1] if len(shap_values) > 1 else shap_values[0]
        if isinstance(shap_values, np.ndarray) and shap_values.ndim == 3:
            return shap_values[:, :, 1]
        return shap_values
