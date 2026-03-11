from kade.market.alpaca_client import MockAlpacaClient
from kade.market.market_loop import MarketStateLoop
from kade.market.state_builder import MentalModelBuilder
from kade.market.structure import Bar

MENTAL_MODEL_CONFIG = {
    "trend_slope": {"bullish": 0.04, "bearish": -0.04},
    "momentum_rsi": {"bullish": 58, "bearish": 42},
    "momentum_macd_hist": {"bullish": 0.02, "bearish": -0.02},
    "volume_acceleration": {"strong": 0.2, "weak": -0.1},
    "confidence": {"high_min": 0.7, "moderate_min": 0.45},
    "regime": {
        "baseline_strong_slope": 0.08,
        "baseline_range_slope_max": 0.02,
        "trend_slope_min": 0.05,
        "momentum_slope_min": 0.08,
        "range_slope_max": 0.02,
    },
    "breadth": {
        "bullish_ratio_min": 0.6,
        "bearish_ratio_max": 0.4,
        "exclude_symbols": ["QQQ"],
    },
    "trap_detection": {
        "weak_vwap_break_distance_max": 0.003,
        "failed_reclaim_buffer": 0.004,
        "low_volume_breakout_acceleration_max": 0.05,
        "moderate_signal_count_min": 1,
        "high_signal_count_min": 2,
    },
}


def _bars(symbol: str, closes: list[float], volumes: list[float]) -> list[Bar]:
    bars: list[Bar] = []
    for idx, close in enumerate(closes):
        bars.append(
            Bar(
                symbol=symbol,
                timestamp=MockAlpacaClient().get_latest_trade(symbol).timestamp,
                open=close - 0.3,
                high=close + 0.4,
                low=close - 0.4,
                close=close,
                volume=volumes[idx],
            )
        )
    return bars


def test_market_loop_populates_ticker_state_fields() -> None:
    loop = MarketStateLoop(
        market_client=MockAlpacaClient(),
        watchlist=["NVDA", "MSFT", "QQQ", "SPY", "META", "AMD"],
        timeframes={"trigger": "1m", "bias": "5m", "context": "15m"},
        bars_limit=60,
        mental_model_config=MENTAL_MODEL_CONFIG,
    )

    states, debug_values = loop.update_once()

    assert set(states.keys()) == {"NVDA", "MSFT", "QQQ", "SPY", "META", "AMD"}
    nvda = states["NVDA"]
    assert nvda.last_price is not None
    assert nvda.vwap is not None
    assert nvda.trend in {"bullish", "neutral", "bearish", "unknown"}
    assert nvda.structure is not None
    assert nvda.momentum is not None
    assert nvda.volume_state is not None
    assert nvda.qqq_confirmation is not None
    assert nvda.regime in {"trend", "range", "momentum", "slow", "unknown"}
    assert nvda.trap_risk in {"low", "moderate", "high", "unknown"}
    assert nvda.confidence_label in {"high", "moderate", "low"}
    assert isinstance(nvda.confidence_reason, str)
    assert nvda.updated_at is not None
    assert "confidence_score_internal" in debug_values["NVDA"]
    assert "breadth_bias" in debug_values["NVDA"]
    assert loop.latest_breadth["bias"] in {"risk_on", "risk_off", "mixed", "unknown"}


def test_mental_model_labels_bullish_and_confident() -> None:
    builder = MentalModelBuilder(MENTAL_MODEL_CONFIG)
    closes = [100 + (0.8 * i) for i in range(30)]
    trigger_volumes = [100] * 10 + [200, 220, 240, 260, 280] + [300] * 15
    result = builder.build(
        symbol="NVDA",
        bars_trigger=_bars("NVDA", closes, trigger_volumes),
        bars_bias=_bars("NVDA", closes, trigger_volumes),
        bars_context=_bars("NVDA", closes, trigger_volumes),
        qqq_trend="bullish",
    )

    assert result.state.trend == "bullish"
    assert result.state.momentum in {"strong_up", "up_bias"}
    assert result.state.qqq_confirmation == "confirmed"
    assert result.state.confidence_label in {"high", "moderate"}


def test_confidence_explanation_contains_positive_and_cautionary_reasons() -> None:
    builder = MentalModelBuilder(MENTAL_MODEL_CONFIG)
    closes = [100 + (0.3 * i) for i in range(30)]
    contracting_volumes = [500] * 25 + [200, 180, 170, 160, 150]
    result = builder.build(
        symbol="NVDA",
        bars_trigger=_bars("NVDA", closes, contracting_volumes),
        bars_bias=_bars("NVDA", closes, contracting_volumes),
        bars_context=_bars("NVDA", closes, contracting_volumes),
        qqq_trend="bullish",
    )

    assert result.state.confidence_reason is not None
    assert "Confidence is" in result.state.confidence_reason
    assert "but" in result.state.confidence_reason
    assert "volume expansion is weaker than typical winning setups" in result.state.confidence_reason
