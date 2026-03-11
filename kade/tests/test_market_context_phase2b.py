from datetime import datetime, timezone

from kade.market.context_intelligence import MarketContextIntelligence
from kade.market.structure import Bar, TickerState

CONFIG = {
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


def _state(symbol: str, **kwargs: str | float | None) -> TickerState:
    base = {
        "symbol": symbol,
        "trend": "neutral",
        "momentum": "mixed",
        "volume_state": "stable",
        "structure": "range_or_mixed",
        "last_price": 100.0,
        "vwap": 99.8,
        "updated_at": datetime.now(timezone.utc),
    }
    base.update(kwargs)
    return TickerState(**base)


def _bars(symbol: str, prices: list[float]) -> list[Bar]:
    now = datetime.now(timezone.utc)
    return [
        Bar(symbol=symbol, timestamp=now, open=price - 0.1, high=price + 0.2, low=price - 0.2, close=price, volume=100)
        for price in prices
    ]


def test_baseline_and_ticker_regime_classification() -> None:
    intel = MarketContextIntelligence(CONFIG)
    qqq_state = _state("QQQ", momentum="strong_up", trend="bullish")
    spy_state = _state("SPY", trend="bullish")

    baseline = intel.baseline_regime(
        qqq_state=qqq_state,
        spy_state=spy_state,
        qqq_debug={"trend_slope": 0.09},
        spy_debug={"trend_slope": 0.07},
    )
    ticker_regime = intel.ticker_regime(
        baseline_regime=baseline,
        state=_state("NVDA", momentum="strong_up", structure="trend_continuation_up"),
        debug={"trend_slope": 0.10},
    )

    assert baseline == "trend"
    assert ticker_regime == "momentum"


def test_breadth_outputs_risk_on_with_advancers() -> None:
    intel = MarketContextIntelligence(CONFIG)
    states = {
        "QQQ": _state("QQQ", trend="bullish"),
        "NVDA": _state("NVDA", trend="bullish"),
        "MSFT": _state("MSFT", trend="bullish"),
        "META": _state("META", trend="bullish"),
        "AMD": _state("AMD", trend="bearish"),
    }

    breadth = intel.breadth_snapshot(states)

    assert breadth.bias == "risk_on"
    assert breadth.confirmation == "advancers_lead"
    assert breadth.advancing_ratio is not None and breadth.advancing_ratio >= 0.6


def test_trap_detection_identifies_high_risk_low_volume_breakout() -> None:
    intel = MarketContextIntelligence(CONFIG)
    state = _state("NVDA", last_price=100.0, vwap=99.9)
    bars = _bars("NVDA", [99.7, 99.8, 99.9, 100.0])
    risk = intel.trap_risk(
        state=state,
        debug={"volume_acceleration": 0.02, "structure_breakout": "breakout_up"},
        bars_trigger=bars,
    )

    assert risk == "high"
