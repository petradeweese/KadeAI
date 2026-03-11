"""Deterministic option contract filtering and ranking."""

from __future__ import annotations

from kade.market.structure import TickerState
from kade.options.models import OptionCandidate, OptionContract, TradeIntent


class OptionSelector:
    """Deterministic selector with explicit intent-to-option-type mapping."""

    INTENT_OPTION_TYPE_MAP = {
        "long": "call",
        "short": "put",
        "long_call": "call",
        "short_put": "put",
    }

    def __init__(self, config: dict) -> None:
        self.config = config
        self.profile_name = config["default_profile"]
        self.profile = config["profiles"][self.profile_name]

    def select_candidates(
        self,
        intent: TradeIntent,
        contracts: list[OptionContract],
        ticker_state: TickerState | None = None,
        radar_context: dict[str, object] | None = None,
    ) -> list[OptionCandidate]:
        target_option_type = self._target_option_type(intent.direction)
        if target_option_type is None:
            return []

        filtered: list[OptionCandidate] = []
        for contract in contracts:
            if contract.symbol != intent.symbol:
                continue
            if not self._direction_matches(target_option_type, contract.option_type):
                continue
            spread_pct = self._spread_pct(contract)
            if not self._passes_thresholds(contract, spread_pct):
                continue
            filtered.append(
                OptionCandidate(
                    contract=contract,
                    spread_pct=spread_pct,
                    affordability_score=self._affordability_score(contract, intent),
                    liquidity_score=self._liquidity_score(contract),
                    expiration_score=self._expiration_score(contract.days_to_expiration),
                    delta_score=self._delta_score(target_option_type, contract.delta),
                    total_score=0.0,
                    reasons=self._reasons(contract, spread_pct, ticker_state, radar_context),
                )
            )

        scored = [self._with_total_score(candidate) for candidate in filtered]
        return sorted(scored, key=lambda c: (-c.total_score, c.contract.strike, c.contract.option_symbol))

    def _passes_thresholds(self, contract: OptionContract, spread_pct: float) -> bool:
        return (
            self.profile["min_days_to_expiration"] <= contract.days_to_expiration <= self.profile["max_days_to_expiration"]
            and contract.open_interest >= self.profile["min_open_interest"]
            and contract.volume >= self.profile["min_volume"]
            and spread_pct <= self.profile["max_spread_pct"]
        )

    def _target_option_type(self, direction: str) -> str | None:
        return self.INTENT_OPTION_TYPE_MAP.get(direction.lower())

    def _direction_matches(self, target_option_type: str, option_type: str) -> bool:
        return option_type == target_option_type

    def _spread_pct(self, contract: OptionContract) -> float:
        mid = (contract.ask + contract.bid) / 2 if (contract.ask + contract.bid) > 0 else 0.0
        if mid == 0:
            return 1.0
        return (contract.ask - contract.bid) / mid

    def _affordability_score(self, contract: OptionContract, intent: TradeIntent) -> float:
        estimated_contract_cost = contract.ask * 100
        max_contracts = max(1, int(intent.desired_position_size_usd / max(estimated_contract_cost, 1)))
        return min(1.0, max_contracts / 5)

    def _liquidity_score(self, contract: OptionContract) -> float:
        oi_score = min(1.0, contract.open_interest / (self.profile["min_open_interest"] * 3))
        volume_score = min(1.0, contract.volume / (self.profile["min_volume"] * 3))
        return (oi_score + volume_score) / 2

    def _expiration_score(self, dte: int) -> float:
        target = self.profile["target_days_to_expiration"]
        max_distance = max(target - self.profile["min_days_to_expiration"], self.profile["max_days_to_expiration"] - target)
        return max(0.0, 1 - (abs(dte - target) / max(max_distance, 1)))

    def _delta_score(self, target_option_type: str, delta: float | None) -> float:
        if delta is None:
            return 0.4
        band_key = "target_delta_call" if target_option_type == "call" else "target_delta_put"
        band = self.profile[band_key]
        if band["min"] <= delta <= band["max"]:
            return 1.0
        distance = min(abs(delta - band["min"]), abs(delta - band["max"]))
        return max(0.0, 1 - (distance / 0.30))

    def _with_total_score(self, candidate: OptionCandidate) -> OptionCandidate:
        spread_score = max(0.0, 1 - (candidate.spread_pct / self.profile["max_spread_pct"]))
        weighted = (
            candidate.affordability_score * self.profile["affordability_weight"]
            + candidate.liquidity_score * self.profile["liquidity_weight"]
            + spread_score * self.profile["spread_weight"]
            + candidate.expiration_score * self.profile["expiration_weight"]
            + candidate.delta_score * self.profile["delta_weight"]
        )
        max_weight = (
            self.profile["affordability_weight"]
            + self.profile["liquidity_weight"]
            + self.profile["spread_weight"]
            + self.profile["expiration_weight"]
            + self.profile["delta_weight"]
        )
        return OptionCandidate(
            contract=candidate.contract,
            spread_pct=candidate.spread_pct,
            affordability_score=candidate.affordability_score,
            liquidity_score=candidate.liquidity_score,
            expiration_score=candidate.expiration_score,
            delta_score=candidate.delta_score,
            total_score=round(100 * weighted / max_weight, 2),
            reasons=candidate.reasons,
        )

    def _reasons(
        self,
        contract: OptionContract,
        spread_pct: float,
        ticker_state: TickerState | None,
        radar_context: dict[str, object] | None,
    ) -> list[str]:
        reasons = [
            f"dte={contract.days_to_expiration}",
            f"spread_pct={spread_pct:.3f}",
            f"oi={contract.open_interest}",
            f"volume={contract.volume}",
        ]
        if contract.delta is not None:
            reasons.append(f"delta={contract.delta:.2f}")
        if ticker_state and ticker_state.regime:
            reasons.append(f"regime={ticker_state.regime}")
        if radar_context and radar_context.get("state"):
            reasons.append(f"radar_state={radar_context['state']}")
        return reasons
