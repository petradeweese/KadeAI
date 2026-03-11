"""Deterministic option chain generator for dev-facing Phase 4 flows."""

from __future__ import annotations

from kade.options.models import OptionContract


def build_mock_chain(symbol: str, last_price: float | None) -> list[OptionContract]:
    base_price = last_price or 100.0
    strikes = [round(base_price - 2, 2), round(base_price, 2), round(base_price + 2, 2)]
    chain: list[OptionContract] = []
    for days, spread_scale in ((5, 1.0), (12, 1.15)):
        for strike in strikes:
            moneyness = abs(strike - base_price)
            ask = round(max(0.8, 2.2 - (moneyness * 0.3)) * spread_scale, 2)
            bid = round(max(0.5, ask - 0.12), 2)
            common = {
                "symbol": symbol,
                "strike": strike,
                "days_to_expiration": days,
                "bid": bid,
                "ask": ask,
                "volume": int(max(120, 500 - moneyness * 80)),
                "open_interest": int(max(350, 1500 - moneyness * 180)),
            }
            chain.append(
                OptionContract(
                    option_symbol=f"{symbol}-{days}D-C-{strike}",
                    option_type="call",
                    delta=round(0.5 - (strike - base_price) * 0.08, 2),
                    **common,
                )
            )
            chain.append(
                OptionContract(
                    option_symbol=f"{symbol}-{days}D-P-{strike}",
                    option_type="put",
                    delta=round(-0.5 - (strike - base_price) * 0.08, 2),
                    **common,
                )
            )
    return chain
