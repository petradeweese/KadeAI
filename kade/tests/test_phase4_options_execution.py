from kade.execution.guardrails import ExecutionGuardrails
from kade.execution.models import OrderRequest
from kade.execution.paper import PaperExecutionEngine
from kade.options.models import OptionContract, TradeIntent
from kade.options.pipeline import OptionsSelectionPipeline
from kade.options.selector import OptionSelector
from kade.options.sizing import SplitSizer

EXECUTION_CONFIG = {
    "mode": "paper",
    "paper_mode_only": True,
    "order_type": "limit",
    "limit_orders_only": True,
    "option_selection": {
        "default_profile": "balanced",
        "profiles": {
            "balanced": {
                "min_days_to_expiration": 3,
                "max_days_to_expiration": 21,
                "target_days_to_expiration": 7,
                "min_open_interest": 400,
                "min_volume": 150,
                "max_spread_pct": 0.15,
                "target_delta_call": {"min": 0.35, "max": 0.60},
                "target_delta_put": {"min": -0.60, "max": -0.35},
                "affordability_weight": 1.0,
                "liquidity_weight": 1.3,
                "spread_weight": 1.1,
                "expiration_weight": 0.9,
                "delta_weight": 1.0,
            }
        },
        "split_sizing": {
            "enabled": True,
            "max_legs": 2,
            "max_contracts_per_leg": 3,
            "neighboring_strike_distance": 1,
            "min_contracts_per_leg": 1,
        },
    },
    "paper_simulation": {
        "max_slippage_per_contract": 0.10,
        "slippage_bps": 8,
        "allow_partial_fills": True,
        "partial_fill_ratio": 0.6,
        "adaptive_nudging_enabled": True,
        "nudge_step": 0.02,
    },
    "guardrails": {
        "max_trades_per_day": 5,
        "daily_loss_limit_usd": 3000,
        "max_slippage_cap_per_contract": 0.12,
    },
}


def _intent() -> TradeIntent:
    return TradeIntent(
        symbol="NVDA",
        direction="long",
        style="intraday",
        desired_position_size_usd=1200,
        max_hold_minutes=30,
    )


def _contracts() -> list[OptionContract]:
    return [
        OptionContract("NVDA", "NVDA-C-100", "call", 100, 7, 1.8, 2.0, delta=0.5, volume=500, open_interest=1200),
        OptionContract("NVDA", "NVDA-C-102", "call", 102, 7, 1.7, 1.85, delta=0.42, volume=450, open_interest=1000),
        OptionContract("NVDA", "NVDA-C-WIDE", "call", 103, 7, 1.0, 1.4, delta=0.4, volume=550, open_interest=1200),
        OptionContract("NVDA", "NVDA-C-LOWOI", "call", 100, 7, 1.9, 2.0, delta=0.48, volume=300, open_interest=100),
        OptionContract("NVDA", "NVDA-P-100", "put", 100, 7, 1.8, 2.0, delta=-0.5, volume=500, open_interest=1200),
    ]


def test_option_filtering_applies_balanced_thresholds() -> None:
    selector = OptionSelector(EXECUTION_CONFIG["option_selection"])
    ranked = selector.select_candidates(_intent(), _contracts())

    symbols = [candidate.contract.option_symbol for candidate in ranked]
    assert "NVDA-C-WIDE" not in symbols
    assert "NVDA-C-LOWOI" not in symbols
    assert "NVDA-P-100" not in symbols


def test_option_ranking_prefers_liquidity_and_spread_quality() -> None:
    selector = OptionSelector(EXECUTION_CONFIG["option_selection"])
    ranked = selector.select_candidates(_intent(), _contracts())

    assert ranked[0].contract.option_symbol in {"NVDA-C-100", "NVDA-C-102"}
    assert ranked[0].total_score >= ranked[1].total_score


def test_balanced_profile_prefers_near_target_delta() -> None:
    selector = OptionSelector(EXECUTION_CONFIG["option_selection"])
    contracts = [
        OptionContract("NVDA", "C-IDEAL", "call", 100, 7, 1.9, 2.0, delta=0.5, volume=500, open_interest=1300),
        OptionContract("NVDA", "C-SPEC", "call", 108, 7, 0.8, 0.9, delta=0.15, volume=500, open_interest=1300),
    ]
    ranked = selector.select_candidates(_intent(), contracts)

    assert ranked[0].contract.option_symbol == "C-IDEAL"


def test_split_sizing_generates_multi_leg_plan() -> None:
    selector = OptionSelector(EXECUTION_CONFIG["option_selection"])
    ranked = selector.select_candidates(_intent(), _contracts())
    sizer = SplitSizer(EXECUTION_CONFIG["option_selection"]["split_sizing"])

    plan = sizer.build_plan(_intent(), ranked, profile="balanced")

    assert plan.target_contracts >= 1
    assert len(plan.allocations) == 2
    assert sum(alloc.contracts for alloc in plan.allocations) == plan.target_contracts


def test_guardrail_rejects_non_paper_or_non_limit_and_trade_caps() -> None:
    guardrails = ExecutionGuardrails(EXECUTION_CONFIG)
    bad_mode = OrderRequest("NVDA", "NVDA-C-100", 1, "buy", 2.0, "live", "limit")
    assert guardrails.validate(bad_mode, 0, 0.0, requested_slippage=0.01)

    bad_type = OrderRequest("NVDA", "NVDA-C-100", 1, "buy", 2.0, "paper", "market")
    assert guardrails.validate(bad_type, 0, 0.0, requested_slippage=0.01)

    cap_hit = OrderRequest("NVDA", "NVDA-C-100", 1, "buy", 2.0, "paper", "limit")
    failure = guardrails.validate(cap_hit, 5, 0.0, requested_slippage=0.01)
    assert failure and failure.code == "max_trades_reached"


def test_paper_execution_supports_partial_fill_and_nudge() -> None:
    engine = PaperExecutionEngine(EXECUTION_CONFIG)
    request = OrderRequest("NVDA", "NVDA-C-100", 3, "buy", 2.0, "paper", "limit")

    result = engine.stage_order(request, trades_today=0, daily_realized_pnl=0.0, confirm=True)

    assert result.status in {"partially_filled", "filled"}
    assert result.filled_contracts > 0
    if result.status == "partially_filled":
        assert result.nudged_limit_price is not None
        assert result.remaining_contracts > 0


def test_pipeline_builds_ranked_candidates_and_plan() -> None:
    pipeline = OptionsSelectionPipeline(EXECUTION_CONFIG["option_selection"])
    plan = pipeline.build_plan(_intent(), _contracts())

    assert plan.profile == "balanced"
    assert plan.ranked_candidates
    assert plan.allocations


def test_option_direction_alias_long_call_matches_calls() -> None:
    selector = OptionSelector(EXECUTION_CONFIG["option_selection"])
    intent = TradeIntent(
        symbol="NVDA",
        direction="long_call",
        style="intraday",
        desired_position_size_usd=1200,
        max_hold_minutes=30,
    )
    ranked = selector.select_candidates(intent, _contracts())

    assert ranked
    assert all(candidate.contract.option_type == "call" for candidate in ranked)


def test_unknown_direction_returns_no_candidates() -> None:
    selector = OptionSelector(EXECUTION_CONFIG["option_selection"])
    intent = TradeIntent(
        symbol="NVDA",
        direction="unknown_direction",
        style="intraday",
        desired_position_size_usd=1200,
        max_hold_minutes=30,
    )

    assert selector.select_candidates(intent, _contracts()) == []
