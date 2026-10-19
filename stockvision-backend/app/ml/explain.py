"""
Explainable AI: exact TreeSHAP attributions for the three tree ensembles.

Design decision: the values are the same *path-dependent TreeSHAP* values that
`shap.TreeExplainer` produces (Lundberg et al., 2018) — exact, no sampling, no
background dataset — but they are computed by the C++ TreeSHAP implementations
that ship inside the model libraries themselves, not by the `shap` package:

  * XGBoost   -> `Booster.predict(..., pred_contribs=True)`
  * LightGBM  -> `predict(..., pred_contrib=True)`
  * scikit-learn RandomForest -> the forest is translated, node for node, into an
    equivalent XGBoost tree ensemble (same splits, same leaf values, same node
    covers), and XGBoost's TreeSHAP is run on that.

Why not `shap` itself: it hard-depends on numba, and numba's LLVM runtime alone
is ~190 MB. That put the API over the 500 MB function limit of the free hosting
tier it is deployed on, and computing the same numbers natively costs nothing.
`tests/test_explain.py` checks every model type against `shap.TreeExplainer`
(installed with the dev requirements) so the two can never silently diverge.

Output space matches shap's TreeExplainer defaults: log-odds for XGBoost and
LightGBM classifiers, positive-class probability for the RandomForest classifier
(a forest averages probabilities), and raw prediction units for regressors.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable

import numpy as np
import pandas as pd


class ShapExplainer:
    def __init__(self, model, feature_names: list[str]):
        self.feature_names = list(feature_names)
        self._contributions = _contribution_function(model)

    def shap_values(self, X: pd.DataFrame) -> np.ndarray:
        """SHAP values, shape (n_samples, n_features) — the bias column dropped."""
        contributions = self._contributions(X[self.feature_names])
        return contributions[:, : len(self.feature_names)]

    def expected_value(self, X: pd.DataFrame) -> float:
        """The base value the SHAP values are offsets from (same for every row)."""
        return float(self._contributions(X[self.feature_names].head(1))[0, -1])

    def global_importance(self, X: pd.DataFrame) -> list[dict]:
        """Mean |SHAP value| per feature across a dataset — 'what does this
        model rely on overall', used for the model card / training report."""
        mean_abs = np.abs(self.shap_values(X)).mean(axis=0)
        ranked = sorted(
            zip(self.feature_names, mean_abs), key=lambda pair: pair[1], reverse=True
        )
        return [{"feature": name, "mean_abs_shap": float(val)} for name, val in ranked]

    def explain_single(self, x_row: pd.DataFrame) -> list[dict]:
        """Per-prediction SHAP contributions — 'why did the model say this
        for THIS stock, right now', used in the Signal/Prediction API responses."""
        row_values = self.shap_values(x_row)[0]
        contributions = [
            {
                "feature": name,
                "value": float(x_row.iloc[0][name]),
                "contribution": float(contribution),
            }
            for name, contribution in zip(self.feature_names, row_values)
        ]
        return sorted(contributions, key=lambda c: abs(c["contribution"]), reverse=True)


# --- dispatch -------------------------------------------------------------------
def _contribution_function(model) -> Callable[[pd.DataFrame], np.ndarray]:
    """Returns X -> (n_samples, n_features + 1) contributions, bias last."""
    module = type(model).__module__

    if module.startswith("xgboost"):
        import xgboost

        booster = model.get_booster()
        return lambda X: np.asarray(
            booster.predict(xgboost.DMatrix(X), pred_contribs=True), dtype=np.float64
        )

    if module.startswith("lightgbm"):
        def lightgbm_contributions(X: pd.DataFrame) -> np.ndarray:
            out = model.predict(X, pred_contrib=True)
            # Multiclass returns a list per class; this platform's classifiers are
            # binary, where LightGBM returns a single (n, f + 1) array already.
            return np.asarray(out[-1] if isinstance(out, list) else out, dtype=np.float64)

        return lightgbm_contributions

    if module.startswith("sklearn.ensemble") and hasattr(model, "estimators_"):
        import xgboost

        booster = forest_to_xgboost(model)
        return lambda X: np.asarray(
            booster.predict(
                xgboost.DMatrix(np.asarray(X, dtype=np.float32)), pred_contribs=True
            ),
            dtype=np.float64,
        )

    raise TypeError(f"No TreeSHAP implementation for model type {type(model).__name__}.")


# --- RandomForest -> XGBoost ------------------------------------------------------
_ROOT_PARENT = 2147483647  # XGBoost's "no parent" sentinel


def _xgboost_split_condition(threshold: float) -> np.float32:
    """
    The float32 c for which XGBoost's `x < c` selects exactly the rows that
    scikit-learn's `x <= threshold` sends left.

    scikit-learn compares float32 inputs against a float64 threshold. For a float32
    x, `x <= t` holds exactly when `x <= f`, where f is the largest float32 not
    above t — and that is `x < nextafter(f, +inf)`.
    """
    f = np.float32(threshold)
    if float(f) > threshold:
        f = np.nextafter(f, np.float32(-np.inf))
    return np.nextafter(f, np.float32(np.inf))


def _leaf_values(tree, n_trees: int, positive_class: int | None) -> np.ndarray:
    value = tree.value[:, 0, :]
    if positive_class is None:  # regressor
        out = value[:, 0]
    else:  # classifier: per-node class probabilities (normalised; sklearn < 1.4 stored counts)
        totals = value.sum(axis=1)
        out = np.divide(value[:, positive_class], totals, out=np.zeros_like(totals), where=totals > 0)
    return out / n_trees  # a forest predicts the MEAN of its trees


def _breadth_first_order(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """Node ids in breadth-first order.

    scikit-learn numbers nodes depth-first (a left child is always parent + 1).
    XGBoost's CPU predictor lays the top of each tree out as an array that assumes
    its own breadth-first numbering; loaded in depth-first order, the trees
    deserialize without complaint but route rows to the wrong leaves.
    """
    order = [0]
    head = 0
    while head < len(order):
        node = order[head]
        head += 1
        if left[node] != -1:
            order += [int(left[node]), int(right[node])]
    return np.asarray(order, dtype=np.int64)


def _tree_to_xgboost_json(tree, tree_id: int, n_trees: int, n_features: int,
                          positive_class: int | None) -> dict:
    order = _breadth_first_order(tree.children_left, tree.children_right)
    new_id = np.empty_like(order)
    new_id[order] = np.arange(len(order))

    left_old = tree.children_left[order]
    right_old = tree.children_right[order]
    is_leaf = left_old == -1
    left = np.where(is_leaf, -1, new_id[np.where(is_leaf, 0, left_old)])
    right = np.where(is_leaf, -1, new_id[np.where(is_leaf, 0, right_old)])

    parents = np.full(len(order), _ROOT_PARENT, dtype=np.int64)
    internal = np.flatnonzero(~is_leaf)
    parents[left[internal]] = internal
    parents[right[internal]] = internal

    node_values = _leaf_values(tree, n_trees, positive_class)[order]
    thresholds = tree.threshold[order]
    conditions = np.array(
        [value if leaf else _xgboost_split_condition(threshold)
         for value, threshold, leaf in zip(node_values, thresholds, is_leaf)],
        dtype=np.float32,
    )
    missing_left = getattr(tree, "missing_go_to_left", None)
    default_left = (
        np.where(is_leaf, 0, missing_left[order]).astype(int) if missing_left is not None
        else np.zeros(len(order), dtype=int)
    )
    n_nodes = len(order)
    return {
        "base_weights": node_values.astype(float).tolist(),
        "categories": [], "categories_nodes": [],
        "categories_segments": [], "categories_sizes": [],
        "default_left": default_left.tolist(),
        "id": tree_id,
        "left_children": left.astype(int).tolist(),
        "loss_changes": [0.0] * n_nodes,
        "parents": parents.astype(int).tolist(),
        "right_children": right.astype(int).tolist(),
        "split_conditions": conditions.astype(float).tolist(),
        "split_indices": np.where(is_leaf, 0, tree.feature[order]).astype(int).tolist(),
        "split_type": [0] * n_nodes,
        "sum_hessian": tree.weighted_n_node_samples[order].astype(float).tolist(),
        "tree_param": {
            "num_deleted": "0", "num_feature": str(n_features),
            "num_nodes": str(n_nodes), "size_leaf_vector": "1",
        },
    }


def forest_to_xgboost(forest):
    """Translates a fitted RandomForest{Classifier,Regressor} into an XGBoost
    Booster whose raw prediction equals the forest's prediction (positive-class
    probability for a classifier) and whose node covers equal the forest's
    weighted sample counts — the inputs path-dependent TreeSHAP uses."""
    import xgboost

    if hasattr(forest, "classes_"):
        classes = list(forest.classes_)
        positive_class = classes.index(1) if 1 in classes else len(classes) - 1
    else:
        positive_class = None

    n_trees = len(forest.estimators_)
    n_features = int(forest.n_features_in_)
    trees = [
        _tree_to_xgboost_json(estimator.tree_, tree_id, n_trees, n_features, positive_class)
        for tree_id, estimator in enumerate(forest.estimators_)
    ]

    model = {
        "learner": {
            "attributes": {}, "feature_names": [], "feature_types": [],
            "gradient_booster": {
                "model": {
                    "gbtree_model_param": {"num_parallel_tree": "1", "num_trees": str(n_trees)},
                    "iteration_indptr": list(range(n_trees + 1)),
                    "tree_info": [0] * n_trees,
                    "trees": trees,
                },
                "name": "gbtree",
            },
            "learner_model_param": {
                "base_score": "0E0", "boost_from_average": "0", "num_class": "0",
                "num_feature": str(n_features), "num_target": "1",
            },
            "objective": {"name": "reg:squarederror", "reg_loss_param": {"scale_pos_weight": "1"}},
        },
        "version": [int(re.match(r"\d+", part).group()) for part in xgboost.__version__.split(".")[:3]],
    }
    booster = xgboost.Booster()
    booster.load_model(bytearray(json.dumps(model).encode("utf-8")))
    return booster
