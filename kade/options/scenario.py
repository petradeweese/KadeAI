"""Deterministic target-move scenario board generation for options contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math

from kade.options.models import OptionContract


@dataclass(frozen=True)
class TargetMoveScenarioRequest:
    symbol: str
    direction: str
    current_price: float
    target_price: float
    time_horizon_minutes: int
    budget: float
    allowed_dtes: tuple[int, ...] = (0, 1, 2)
    profile: str | None = None


class TargetMoveScenarioBoard:
    """Generates a rankable board of options outcomes for a target-price scenario."""

    DIRECTION_OPTION_TYPE_MAP = {
        "bullish": "call",
        "bearish": "put",
        "call": "call",
        "put": "put",
        "long": "call",
        "short": "put",
        "long_call": "call",
        "short_put": "put",
    }

    def __init__(self, config: dict) -> None:
        self.config = config
        self.default_profile = str(config.get("default_profile", "fast_intraday"))

    def generate(self, request: TargetMoveScenarioRequest, contracts: list[OptionContract]) -> dict[str, object]:
        profile_name = request.profile or self.default_profile
        profile_cfg = dict(self.config["profiles"][profile_name])
        direction = self.DIRECTION_OPTION_TYPE_MAP.get(request.direction.lower(), request.direction.lower())

        candidates: list[dict[str, object]] = []
        for contract in contracts:
            candidate = self._build_candidate(request, contract, direction, profile_name, profile_cfg)
            if candidate is not None:
                candidates.append(candidate)

        ranked = sorted(candidates, key=lambda c: (-float(c["ranking_score"]), -float(c["estimated_percent_return"]), c["strike"], str(c["option_symbol"])))
        buckets = self._build_buckets(ranked)

        return {
            "request": {
                "symbol": request.symbol,
                "direction": direction,
                "current_price": request.current_price,
                "target_price": request.target_price,
                "time_horizon_minutes": request.time_horizon_minutes,
                "budget": request.budget,
                "allowed_dtes": list(request.allowed_dtes),
                "profile": profile_name,
            },
            "assumptions": {
                "notes": "Scenario estimates are deterministic approximations; not exact pricing or trade advice.",
                "slippage_haircut_pct": profile_cfg["slippage_haircut_pct"],
                "spread_haircut_multiplier": profile_cfg["spread_haircut_multiplier"],
            },
            "candidates": ranked,
            "buckets": buckets,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _build_candidate(
        self,
        request: TargetMoveScenarioRequest,
        contract: OptionContract,
        direction: str,
        profile_name: str,
        profile_cfg: dict[str, object],
    ) -> dict[str, object] | None:
        if contract.symbol != request.symbol:
            return None
        if contract.option_type != direction:
            return None
        if contract.days_to_expiration not in request.allowed_dtes:
            return None

        spread_pct = self._spread_pct(contract.bid, contract.ask)
        if spread_pct > float(profile_cfg["max_spread_pct"]):
            return None
        if contract.open_interest < int(profile_cfg["min_open_interest"]):
            return None
        if contract.volume < int(profile_cfg["min_volume"]):
            return None

        entry_price = self._estimate_entry_price(contract.bid, contract.ask, spread_pct, profile_cfg)
        if entry_price <= 0:
            return None

        contracts_affordable = math.floor(request.budget / (entry_price * 100))
        if contracts_affordable <= 0:
            return None

        target_option_price = self._estimate_target_price(request, contract, entry_price, spread_pct, profile_cfg)
        gain_per_contract = round((target_option_price - entry_price) * 100, 2)
        total_gain = round(gain_per_contract * contracts_affordable, 2)
        percent_return = round(((target_option_price - entry_price) / entry_price) * 100, 2) if entry_price > 0 else 0.0

        liquidity = self._liquidity_summary(contract, profile_cfg)
        delta_suitability = self._delta_suitability(request, contract, profile_cfg)
        dte_fit = self._dte_fit(contract.days_to_expiration, profile_cfg)
        spread_quality = max(0.0, 1 - (spread_pct / max(float(profile_cfg["max_spread_pct"]), 0.0001)))

        ranking_score = self._ranking_score(
            percent_return=percent_return,
            total_gain=total_gain,
            liquidity_score=liquidity["liquidity_score"],
            spread_quality=spread_quality,
            delta_suitability=delta_suitability,
            dte_fit=dte_fit,
            budget=request.budget,
            profile_cfg=profile_cfg,
        )
        risk_label = self._risk_label(contract, spread_pct, liquidity["liquidity_score"], delta_suitability)

        return {
            "option_symbol": contract.option_symbol,
            "option_type": contract.option_type,
            "strike": contract.strike,
            "dte": contract.days_to_expiration,
            "bid": contract.bid,
            "ask": contract.ask,
            "estimated_entry_price": entry_price,
            "contracts_affordable": contracts_affordable,
            "estimated_target_option_price": target_option_price,
            "estimated_gain_per_contract": gain_per_contract,
            "estimated_total_gain": total_gain,
            "estimated_percent_return": percent_return,
            "delta": contract.delta,
            "spread_pct": round(spread_pct, 4),
            "liquidity": liquidity,
            "risk_label": risk_label,
            "aggressiveness_label": profile_name,
            "tags": self._tags(risk_label, spread_pct, contract.days_to_expiration, contracts_affordable),
            "ranking_score": ranking_score,
            "notes": [
                "estimated_target_option_price uses delta-driven scenario approximation",
                "includes spread/slippage haircuts and short-DTE gamma-style uplift",
                "scenario output is deterministic and inspectable",
            ],
        }

    def _estimate_entry_price(self, bid: float, ask: float, spread_pct: float, profile_cfg: dict[str, object]) -> float:
        midpoint = (bid + ask) / 2
        entry = midpoint + ((ask - bid) * float(profile_cfg["entry_aggressiveness"]))
        entry += midpoint * spread_pct * float(profile_cfg["entry_spread_penalty_multiplier"])
        return round(max(entry, 0.01), 2)

    def _estimate_target_price(
        self,
        request: TargetMoveScenarioRequest,
        contract: OptionContract,
        entry_price: float,
        spread_pct: float,
        profile_cfg: dict[str, object],
    ) -> float:
        move = request.target_price - request.current_price
        directional_move = move if contract.option_type == "call" else -move
        delta = contract.delta if contract.delta is not None else float(profile_cfg["fallback_delta"])
        delta_abs = abs(delta)

        base_change = directional_move * delta_abs
        gamma_uplift = self._gamma_uplift(contract.days_to_expiration, request.time_horizon_minutes, profile_cfg)
        adjusted_change = max(0.0, base_change * (1 + gamma_uplift))

        raw_target_price = entry_price + adjusted_change
        slippage_haircut = raw_target_price * float(profile_cfg["slippage_haircut_pct"])
        spread_haircut = entry_price * spread_pct * float(profile_cfg["spread_haircut_multiplier"])

        conservative_floor = float(profile_cfg["target_price_floor_multiplier"]) * entry_price
        return round(max(conservative_floor, raw_target_price - slippage_haircut - spread_haircut), 2)

    def _gamma_uplift(self, dte: int, minutes: int, profile_cfg: dict[str, object]) -> float:
        dte_uplift = dict(profile_cfg["gamma_uplift_by_dte"]).get(dte, 0.0)
        short_window_boost = float(profile_cfg["short_window_uplift"] if minutes <= int(profile_cfg["short_window_minutes"]) else 0.0)
        return float(dte_uplift) + short_window_boost

    def _spread_pct(self, bid: float, ask: float) -> float:
        mid = (bid + ask) / 2
        if mid <= 0:
            return 1.0
        return max(0.0, (ask - bid) / mid)

    def _liquidity_summary(self, contract: OptionContract, profile_cfg: dict[str, object]) -> dict[str, object]:
        min_oi = max(int(profile_cfg["min_open_interest"]), 1)
        min_volume = max(int(profile_cfg["min_volume"]), 1)
        oi_ratio = min(contract.open_interest / (min_oi * 2), 1.5)
        volume_ratio = min(contract.volume / (min_volume * 2), 1.5)
        liquidity_score = round(min((oi_ratio + volume_ratio) / 2, 1.0), 3)
        if liquidity_score >= 0.8:
            label = "high"
        elif liquidity_score >= 0.55:
            label = "medium"
        else:
            label = "thin"
        return {
            "open_interest": contract.open_interest,
            "volume": contract.volume,
            "liquidity_score": liquidity_score,
            "label": label,
        }

    def _delta_suitability(self, request: TargetMoveScenarioRequest, contract: OptionContract, profile_cfg: dict[str, object]) -> float:
        abs_delta = abs(contract.delta) if contract.delta is not None else float(profile_cfg["fallback_delta"])
        target_range = profile_cfg["target_delta_range"]
        low, high = float(target_range[0]), float(target_range[1])
        if low <= abs_delta <= high:
            return 1.0
        if abs_delta < low:
            return max(0.0, 1 - ((low - abs_delta) / 0.40))
        return max(0.0, 1 - ((abs_delta - high) / 0.35))

    def _dte_fit(self, dte: int, profile_cfg: dict[str, object]) -> float:
        dte_preferences: dict[int, float] = {int(key): float(value) for key, value in dict(profile_cfg["dte_preferences"]).items()}
        return dte_preferences.get(dte, 0.3)

    def _ranking_score(
        self,
        *,
        percent_return: float,
        total_gain: float,
        liquidity_score: float,
        spread_quality: float,
        delta_suitability: float,
        dte_fit: float,
        budget: float,
        profile_cfg: dict[str, object],
    ) -> float:
        weights = profile_cfg["ranking_weights"]
        normalized_return = max(min(percent_return / 150.0, 1.0), -1.0)
        normalized_total_gain = max(min(total_gain / max(budget, 1.0), 2.0), -1.0)
        weighted_sum = (
            normalized_return * float(weights["estimated_percent_return"])
            + normalized_total_gain * float(weights["estimated_total_gain"])
            + liquidity_score * float(weights["liquidity"])
            + spread_quality * float(weights["spread_quality"])
            + delta_suitability * float(weights["delta_suitability"])
            + dte_fit * float(weights["dte_fit"])
        )
        return round(weighted_sum * 100, 2)

    def _risk_label(self, contract: OptionContract, spread_pct: float, liquidity_score: float, delta_suitability: float) -> str:
        if contract.days_to_expiration == 0 and (spread_pct > 0.08 or liquidity_score < 0.6):
            return "high_risk_fill"
        if delta_suitability < 0.45:
            return "low_responsiveness"
        if spread_pct < 0.05 and liquidity_score >= 0.8:
            return "safer_fill"
        return "balanced_risk"

    def _tags(self, risk_label: str, spread_pct: float, dte: int, contracts_affordable: int) -> list[str]:
        tags = [risk_label, f"dte_{dte}"]
        if spread_pct <= 0.05:
            tags.append("tight_spread")
        if dte == 0:
            tags.append("zero_dte")
        if contracts_affordable >= 5:
            tags.append("budget_flexible")
        elif contracts_affordable == 1:
            tags.append("single_contract_budget")
        return tags

    def _build_buckets(self, ranked: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
        top_n = int(self.config.get("bucket_top_n", 3))
        highest_estimated_return = sorted(ranked, key=lambda c: (-float(c["estimated_percent_return"]), -float(c["ranking_score"]), c["option_symbol"]))[:top_n]
        best_balance = sorted(ranked, key=lambda c: (-float(c["ranking_score"]), -float(c["liquidity"]["liquidity_score"]), c["option_symbol"]))[:top_n]
        safer_fill = sorted(ranked, key=lambda c: (str(c["risk_label"]) != "safer_fill", float(c["spread_pct"]), -float(c["liquidity"]["liquidity_score"]), c["option_symbol"]))[:top_n]
        aggressive_cheap = sorted(ranked, key=lambda c: (float(c["estimated_entry_price"]), -float(c["estimated_percent_return"]), c["option_symbol"]))[:top_n]

        def slim(items: list[dict[str, object]]) -> list[dict[str, object]]:
            return [
                {
                    "option_symbol": item["option_symbol"],
                    "dte": item["dte"],
                    "estimated_percent_return": item["estimated_percent_return"],
                    "estimated_total_gain": item["estimated_total_gain"],
                    "risk_label": item["risk_label"],
                }
                for item in items
            ]

        return {
            "highest_estimated_return": slim(highest_estimated_return),
            "best_balance": slim(best_balance),
            "safer_fill": slim(safer_fill),
            "aggressive_cheap": slim(aggressive_cheap),
        }
