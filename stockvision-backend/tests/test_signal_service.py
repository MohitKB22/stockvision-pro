
from app.domain.enums import SignalAction
from app.services.signal_service import (
    BUY_THRESHOLD,
    SELL_THRESHOLD,
    STRONG_BUY_THRESHOLD,
    STRONG_SELL_THRESHOLD,
    compute_indicator_score,
    compute_risk_score,
    score_to_action,
)


class TestComputeIndicatorScore:
    def test_all_bullish_signals_gives_positive_score(self):
        indicators = {
            "rsi_14": 25,  # oversold -> bullish
            "macd_hist": 1.5,  # positive -> bullish
            "supertrend_direction": 1,  # uptrend -> bullish
            "adx": 30, "plus_di": 25, "minus_di": 10,  # strong uptrend -> bullish
            "close": 95, "bb_upper": 110, "bb_lower": 100,  # below lower band -> bullish
        }
        score, votes = compute_indicator_score(indicators)
        assert score > 0
        assert all(v > 0 for v in votes.values())

    def test_all_bearish_signals_gives_negative_score(self):
        indicators = {
            "rsi_14": 80,  # overbought -> bearish
            "macd_hist": -1.5,  # negative -> bearish
            "supertrend_direction": -1,  # downtrend -> bearish
            "adx": 30, "plus_di": 10, "minus_di": 25,  # strong downtrend -> bearish
            "close": 115, "bb_upper": 110, "bb_lower": 100,  # above upper band -> bearish
        }
        score, votes = compute_indicator_score(indicators)
        assert score < 0
        assert all(v < 0 for v in votes.values())

    def test_missing_indicators_are_skipped_not_treated_as_zero_votes(self):
        """An indicator with no data shouldn't silently count as a neutral
        vote diluting the average -- it should be absent from `votes` entirely."""
        _score, votes = compute_indicator_score({"rsi_14": 20})
        assert "macd_hist" not in votes
        assert "rsi_14" in votes

    def test_weak_trend_adx_below_20_withholds_directional_vote(self):
        """ADX < 20 means no real trend -- +DI/-DI crossing shouldn't vote at all."""
        indicators = {"adx": 15, "plus_di": 25, "minus_di": 10}
        _, votes = compute_indicator_score(indicators)
        assert "adx_direction" not in votes

    def test_empty_indicators_gives_neutral_zero_score(self):
        score, votes = compute_indicator_score({})
        assert score == 0.0
        assert votes == {}


class TestScoreToAction:
    def test_threshold_boundaries(self):
        assert score_to_action(STRONG_BUY_THRESHOLD) == SignalAction.STRONG_BUY
        assert score_to_action(BUY_THRESHOLD) == SignalAction.BUY
        assert score_to_action(0.0) == SignalAction.HOLD
        assert score_to_action(SELL_THRESHOLD) == SignalAction.SELL
        assert score_to_action(STRONG_SELL_THRESHOLD) == SignalAction.STRONG_SELL

    def test_just_below_strong_buy_is_regular_buy(self):
        assert score_to_action(STRONG_BUY_THRESHOLD - 0.01) == SignalAction.BUY

    def test_monotonicity(self):
        """A strictly higher score must never map to a 'less bullish' action."""
        ordering = [
            SignalAction.STRONG_SELL, SignalAction.SELL, SignalAction.HOLD,
            SignalAction.BUY, SignalAction.STRONG_BUY,
        ]
        scores = [-0.9, -0.4, 0.0, 0.4, 0.9]
        actions = [score_to_action(s) for s in scores]
        assert [ordering.index(a) for a in actions] == sorted(ordering.index(a) for a in actions)


class TestComputeRiskScore:
    def test_unknown_inputs_default_to_medium_risk_not_zero(self):
        """Missing data must never be reported as 'zero risk' -- that's an
        unsafe default for a trading system."""
        assert compute_risk_score(None, None, None) == 0.5

    def test_high_volatility_and_atr_gives_high_risk(self):
        score = compute_risk_score(volatility_20d=1.2, atr_14=8.0, close=100.0)
        assert score > 0.8

    def test_low_volatility_and_atr_gives_low_risk(self):
        score = compute_risk_score(volatility_20d=0.05, atr_14=0.2, close=100.0)
        assert score < 0.2

    def test_risk_score_always_bounded_0_to_1(self):
        extreme = compute_risk_score(volatility_20d=50.0, atr_14=500.0, close=1.0)
        assert 0.0 <= extreme <= 1.0
