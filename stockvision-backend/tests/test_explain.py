"""
The native TreeSHAP explainer must agree with `shap.TreeExplainer` exactly.

`app/ml/explain.py` computes SHAP values with the model libraries' own C++
TreeSHAP (and, for scikit-learn forests, by translating the forest into an
equivalent XGBoost ensemble). These tests are the contract that makes that
substitution safe: for every algorithm the platform trains, both classification
and regression, the values must match shap's to floating-point tolerance, and
they must add up to the model's own prediction.

`shap` is a dev-only dependency; the comparison tests skip without it, but the
additivity tests always run.
"""
import numpy as np
import pandas as pd
import pytest
from lightgbm import LGBMClassifier, LGBMRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from xgboost import XGBClassifier, XGBRegressor

from app.ml.explain import ShapExplainer, _xgboost_split_condition
from app.ml.indicators import FEATURE_COLUMNS, build_feature_matrix
from scripts.generate_synthetic_data import generate_synthetic_ohlcv

FEATURES = FEATURE_COLUMNS


@pytest.fixture(scope="module")
def dataset():
    """Real feature matrix from the production indicator pipeline (not toy data),
    so ties, repeated values and float32 rounding all occur as they do live."""
    ohlcv = generate_synthetic_ohlcv(symbol="EXPL", n_days=420, seed=7)
    feat = build_feature_matrix(ohlcv)
    feat["up"] = (feat["close"].shift(-1) > feat["close"]).astype(int)
    feat["ret"] = feat["close"].pct_change().shift(-1)
    clean = feat.dropna(subset=[*FEATURES, "up", "ret"]).reset_index(drop=True)
    return clean[FEATURES], clean["up"], clean["ret"]


MODELS = {
    "xgboost-clf": lambda: XGBClassifier(n_estimators=60, max_depth=4, random_state=1, eval_metric="logloss"),
    "xgboost-reg": lambda: XGBRegressor(n_estimators=60, max_depth=4, random_state=1),
    "lightgbm-clf": lambda: LGBMClassifier(n_estimators=60, max_depth=4, random_state=1, verbosity=-1),
    "lightgbm-reg": lambda: LGBMRegressor(n_estimators=60, max_depth=4, random_state=1, verbosity=-1),
    "forest-clf": lambda: RandomForestClassifier(n_estimators=40, max_depth=12, min_samples_leaf=2, random_state=1),
    "forest-reg": lambda: RandomForestRegressor(n_estimators=40, max_depth=12, min_samples_leaf=2, random_state=1),
}


def _fit(name, dataset):
    X, up, ret = dataset
    model = MODELS[name]()
    model.fit(X, up if name.endswith("clf") else ret)
    return model


def _model_output(model, X):
    """What TreeSHAP decomposes: raw margin for boosted classifiers, probability
    for a forest classifier, the prediction for regressors."""
    if isinstance(model, RandomForestClassifier):
        return model.predict_proba(X)[:, 1]
    if isinstance(model, XGBClassifier):
        return model.predict(X, output_margin=True)
    if isinstance(model, LGBMClassifier):
        return model.predict(X, raw_score=True)
    return model.predict(X)


@pytest.mark.parametrize("name", list(MODELS))
def test_contributions_add_up_to_the_prediction(name, dataset):
    X = dataset[0]
    model = _fit(name, dataset)
    explainer = ShapExplainer(model, FEATURES)
    sample = X.iloc[::7]
    total = explainer.shap_values(sample).sum(axis=1) + explainer.expected_value(sample)
    np.testing.assert_allclose(total, _model_output(model, sample), rtol=1e-4, atol=1e-4)


@pytest.mark.parametrize("name", list(MODELS))
def test_matches_shap_tree_explainer(name, dataset):
    shap = pytest.importorskip("shap")
    X = dataset[0]
    model = _fit(name, dataset)
    sample = X.iloc[::5]

    reference = shap.TreeExplainer(model).shap_values(sample)
    if isinstance(reference, list):
        reference = reference[1] if len(reference) > 1 else reference[0]
    reference = np.asarray(reference)
    if reference.ndim == 3:
        reference = reference[:, :, 1]

    ours = ShapExplainer(model, FEATURES).shap_values(sample)
    np.testing.assert_allclose(ours, reference, rtol=1e-4, atol=1e-5)


def test_explain_single_and_global_importance_shapes(dataset):
    X = dataset[0]
    explainer = ShapExplainer(_fit("forest-clf", dataset), FEATURES)

    single = explainer.explain_single(X.tail(1))
    assert {c["feature"] for c in single} == set(FEATURES)
    magnitudes = [abs(c["contribution"]) for c in single]
    assert magnitudes == sorted(magnitudes, reverse=True)

    ranked = explainer.global_importance(X.sample(80, random_state=0))
    assert [r["feature"] for r in ranked] and all(r["mean_abs_shap"] >= 0 for r in ranked)


@pytest.mark.parametrize("threshold", [0.0, 1.5, -2.25, 0.1, 1e-8, 123456.789, -0.30000000000000004])
def test_split_condition_reproduces_sklearn_less_or_equal(threshold):
    """Every float32 around the threshold must go the same way in both libraries."""
    condition = _xgboost_split_condition(threshold)
    center = np.float32(threshold)
    probes = [center]
    lo = hi = center
    for _ in range(4):
        lo = np.nextafter(lo, np.float32(-np.inf))
        hi = np.nextafter(hi, np.float32(np.inf))
        probes += [lo, hi]
    for x in probes:
        assert (x < condition) == (float(x) <= threshold), (x, threshold, condition)


def test_unsupported_model_is_rejected():
    from sklearn.linear_model import LogisticRegression

    model = LogisticRegression().fit(pd.DataFrame({"a": [0, 1, 2, 3]}), [0, 0, 1, 1])
    with pytest.raises(TypeError):
        ShapExplainer(model, ["a"])
