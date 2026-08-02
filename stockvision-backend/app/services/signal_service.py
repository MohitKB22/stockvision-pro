"""
AI Signal Engine.

Design decision: the scoring math (indicator_score, risk_score,
score_to_action) is implemented as pure, DB-free functions so they can be
unit tested with hand-built inputs (tests/test_signal_service.py) completely
independently of the DB-backed orchestration in SignalService below, which
pulls real feature rows + a live model prediction and stitches everything
together into a persisted Signal row.

The composite score blends two independent sources of evidence:
  - `indicator_score` (rule-based, from classical TA — RSI/MACD/SuperTrend/
    ADX/Bollinger) -- transparent, doesn't require a trained model to exist.
  - `model_score` (derived from the ML Engine's predicted probability) --
    adaptive, learns from history, but only available once a model is trained.
If no trained model exists yet, the signal still degrades gracefully to a pure
indicator-based signal — the platform should never block a Signal just because a
model has not been trained for a symbol yet.

CHANGE LOG (v2.0):
  - `triggered_by` removed (no users).
  - BUG FIX: the bare `except Exception` around the model call swallowed EVERY
    error, including genuine bugs inside the ML path, and reported them to the
    user as "no model trained". It now catches only the two domain exceptions
    that legitimately mean "no model", and logs anything else loudly.
  - ADDED `generate_bulk`, so the dashboard's signal panel produces N signals in
    one service call instead of N HTTP round-trips from the browser.
"""
import logging

from sqlalchemy.orm import Session

from app.core.exceptions import InsufficientDataException, ModelNotTrainedException
from app.domain.enums import ModelTask, SignalAction
from app.models.ml import Signal
from app.repositories.ml_repository import SignalRepository
from app.services.feature_engineering_service import FeatureEngineeringService
from app.services.ml_service import MLService

INDICATOR_WEIGHT = 0.5
MODEL_WEIGHT = 0.5

# score_to_action thresholds. Kept as named constants (not magic numbers
# inline) so tests can assert against the exact boundary values.
STRONG_BUY_THRESHOLD = 0.6
BUY_THRESHOLD = 0.2
SELL_THRESHOLD = -0.2
STRONG_SELL_THRESHOLD = -0.6

logger = logging.getLogger(__name__)


def compute_indicator_score(indicators: dict) -> tuple[float, dict]:
    """
    Blend several classical TA signals into a single score in [-1, +1].
    Returns (score, breakdown) where breakdown records each sub-vote for
    the human-readable explanation and the API's `supporting_indicators` field.
    """
    votes: dict[str, float] = {}

    rsi = indicators.get("rsi_14")
    if rsi is not None:
        if rsi < 30:
            votes["rsi_14"] = 1.0  # oversold -> bullish
        elif rsi > 70:
            votes["rsi_14"] = -1.0  # overbought -> bearish
        else:
            votes["rsi_14"] = (50 - rsi) / 20  # mild linear tilt around neutral 50

    macd_hist = indicators.get("macd_hist")
    if macd_hist is not None:
        votes["macd_hist"] = 1.0 if macd_hist > 0 else (-1.0 if macd_hist < 0 else 0.0)

    supertrend_dir = indicators.get("supertrend_direction")
    if supertrend_dir is not None:
        votes["supertrend_direction"] = 1.0 if supertrend_dir > 0 else -1.0

    adx = indicators.get("adx")
    plus_di = indicators.get("plus_di")
    minus_di = indicators.get("minus_di")
    if adx is not None and plus_di is not None and minus_di is not None and adx > 20:
        # Only trust direction when ADX signals a real trend (>20); a weak
        # trend's +DI/-DI crossovers are noise, so we deliberately withhold
        # this vote (no key added) rather than injecting a low-confidence one.
        votes["adx_direction"] = 1.0 if plus_di > minus_di else -1.0

    close = indicators.get("close")
    bb_upper = indicators.get("bb_upper")
    bb_lower = indicators.get("bb_lower")
    if close is not None and bb_upper is not None and bb_lower is not None:
        if close >= bb_upper:
            votes["bollinger"] = -1.0  # price at/above upper band -> overbought
        elif close <= bb_lower:
            votes["bollinger"] = 1.0  # price at/below lower band -> oversold
        else:
            votes["bollinger"] = 0.0

    if not votes:
        return 0.0, votes
    return sum(votes.values()) / len(votes), votes


def compute_risk_score(volatility_20d: float | None, atr_14: float | None, close: float | None) -> float:
    """
    Risk score in [0, 1] — higher means riskier. Combines annualized rolling
    volatility (already annualized by app.ml.indicators.rolling_volatility)
    with ATR-as-percent-of-price, then squashes into [0, 1] with a simple
    capped linear scale. This is intentionally simple and monotonic (not a
    black box) since risk_score feeds directly into a human-facing number.
    """
    if volatility_20d is None or atr_14 is None or close is None or close <= 0:
        return 0.5  # unknown risk defaults to medium, never to 0 (falsely "safe")

    vol_component = min(volatility_20d / 0.80, 1.0)  # 80%+ annualized vol -> maxed out
    atr_pct = atr_14 / close
    atr_component = min(atr_pct / 0.05, 1.0)  # ATR >= 5% of price -> maxed out
    return round(0.6 * vol_component + 0.4 * atr_component, 4)


def score_to_action(score: float) -> SignalAction:
    if score >= STRONG_BUY_THRESHOLD:
        return SignalAction.STRONG_BUY
    if score >= BUY_THRESHOLD:
        return SignalAction.BUY
    if score <= STRONG_SELL_THRESHOLD:
        return SignalAction.STRONG_SELL
    if score <= SELL_THRESHOLD:
        return SignalAction.SELL
    return SignalAction.HOLD


def build_explanation(action: SignalAction, indicator_votes: dict, model_proba: float | None) -> str:
    bullish = [k for k, v in indicator_votes.items() if v > 0]
    bearish = [k for k, v in indicator_votes.items() if v < 0]
    parts = [f"Composite signal: {action.value.upper().replace('_', ' ')}."]
    if bullish:
        parts.append(f"Bullish signals from: {', '.join(bullish)}.")
    if bearish:
        parts.append(f"Bearish signals from: {', '.join(bearish)}.")
    if model_proba is not None:
        parts.append(f"ML model estimates a {model_proba:.0%} probability of a next-day price increase.")
    return " ".join(parts)


class SignalService:
    def __init__(self, db: Session):
        self.db = db
        self.signals = SignalRepository(db)
        self.features = FeatureEngineeringService(db)
        self.ml = MLService(db)

    def generate_signal(self, symbol: str) -> Signal:
        snapshots = self.features.compute_features(symbol, limit=500)
        latest = next((s for s in reversed(snapshots) if all(v is not None for v in s.indicators.values())), None)
        if latest is None:
            latest = snapshots[-1]  # fall back to most recent row even with some NaNs

        indicators = {**latest.indicators, "close": latest.close}
        indicator_score, votes = compute_indicator_score(indicators)

        model_proba = None
        model_score = 0.0
        try:
            prediction = self.ml.predict_latest(symbol, task=ModelTask.TREND_CLASSIFICATION)
            model_proba = prediction.predicted_value
            model_score = (model_proba - 0.5) * 2  # map [0,1] -> [-1,1]
            prediction_id = prediction.id
            shap_contributions = getattr(prediction, "_shap_contributions", [])
        except (ModelNotTrainedException, InsufficientDataException):
            # The two conditions that genuinely mean "no model for this symbol
            # yet" — degrade to a pure indicator signal.
            prediction_id = None
            shap_contributions = []
        except Exception:
            # Anything else is a real defect. Still degrade (the user gets a
            # signal), but make it loud in the logs instead of invisible.
            logger.exception("Unexpected failure in the ML path while generating a signal for %s", symbol)
            prediction_id = None
            shap_contributions = []

        if model_proba is not None:
            composite = INDICATOR_WEIGHT * indicator_score + MODEL_WEIGHT * model_score
        else:
            composite = indicator_score

        action = score_to_action(composite)
        confidence = min(abs(composite), 1.0)
        risk_score = compute_risk_score(
            latest.indicators.get("volatility_20d"), latest.indicators.get("atr_14"), latest.close
        )
        explanation = build_explanation(action, votes, model_proba)

        stock = self.features.stocks.get_by_symbol(symbol)
        signal = Signal(
            stock_id=stock.id,
            prediction_id=prediction_id,
            action=action,
            confidence=confidence,
            risk_score=risk_score,
            supporting_indicators=votes,
            explanation=explanation,
            llm_explanation=None,  # populated by the Phase-2 LLM copilot
        )
        signal = self.signals.create(signal)
        signal._shap_contributions = shap_contributions
        return signal

    def generate_bulk(self, symbols: list[str]) -> list[Signal]:
        """
        Generate signals for many symbols, skipping any that fail.

        One bad symbol (no price history, say) must not fail the dashboard's
        entire signal panel — which is what happened when the frontend fired N
        independent requests and rendered an error for the whole card if any one
        of them rejected.
        """
        out: list[Signal] = []
        for symbol in symbols:
            try:
                out.append(self.generate_signal(symbol))
            except Exception:
                logger.warning("Skipping signal generation for %s", symbol, exc_info=True)
        return out
