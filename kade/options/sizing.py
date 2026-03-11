"""Split sizing plan generation for selected option candidates."""

from __future__ import annotations

from kade.options.models import OptionAllocation, OptionCandidate, SelectedOptionPlan, TradeIntent


class SplitSizer:
    def __init__(self, config: dict) -> None:
        self.config = config

    def build_plan(self, intent: TradeIntent, candidates: list[OptionCandidate], profile: str) -> SelectedOptionPlan:
        if not candidates:
            return SelectedOptionPlan(
                symbol=intent.symbol,
                profile=profile,
                direction=intent.direction,
                target_contracts=0,
                allocations=[],
                total_estimated_cost=0.0,
                ranked_candidates=[],
            )

        top = candidates[: self.config["max_legs"]]
        top_premium = top[0].contract.ask * 100
        target_contracts = max(1, int(intent.desired_position_size_usd / max(top_premium, 1)))

        allocations: list[OptionAllocation] = []
        remaining = target_contracts
        for candidate in top:
            if remaining <= 0:
                break
            per_leg = min(self.config["max_contracts_per_leg"], remaining)
            if per_leg < self.config["min_contracts_per_leg"]:
                continue
            allocations.append(
                OptionAllocation(
                    option_symbol=candidate.contract.option_symbol,
                    contracts=per_leg,
                    strike=candidate.contract.strike,
                    premium=candidate.contract.ask,
                )
            )
            remaining -= per_leg

        if remaining > 0 and allocations:
            first = allocations[0]
            allocations[0] = OptionAllocation(
                option_symbol=first.option_symbol,
                contracts=first.contracts + remaining,
                strike=first.strike,
                premium=first.premium,
            )

        total_estimated_cost = round(sum(allocation.contracts * allocation.premium * 100 for allocation in allocations), 2)
        return SelectedOptionPlan(
            symbol=intent.symbol,
            profile=profile,
            direction=intent.direction,
            target_contracts=target_contracts,
            allocations=allocations,
            total_estimated_cost=total_estimated_cost,
            ranked_candidates=candidates,
        )
