"""News normalization and deterministic catalyst tagging."""

from __future__ import annotations

from kade.market.intelligence.models import NewsItem, NewsSummary
from kade.market.intelligence.utilities import breakdown, dedupe_news_items, normalize_symbol_list, short_summary


class NewsNormalizer:
    def __init__(self, config: dict[str, object]) -> None:
        self.max_items = int(config.get("max_items", 12))
        self.keywords = dict(config.get("classification_keywords", {}))

    def normalize(self, raw_items: list[dict[str, object]], source: str, generated_at: str) -> tuple[list[NewsItem], NewsSummary]:
        normalized_raw = dedupe_news_items(raw_items)
        result: list[NewsItem] = []
        for item in normalized_raw[: self.max_items]:
            headline = str(item.get("headline") or item.get("title") or "").strip()
            text = str(item.get("summary") or item.get("description") or headline)
            symbols = normalize_symbol_list(item.get("symbols") if isinstance(item.get("symbols"), list) else [])
            catalyst = self.classify_catalyst(headline=headline, summary=text)
            relevance = "symbol_linked" if symbols else "market_wide"
            result.append(
                NewsItem(
                    timestamp=str(item.get("timestamp") or generated_at),
                    source=source,
                    headline=headline,
                    summary=short_summary(text),
                    symbols=symbols,
                    url=str(item.get("url") or "") or None,
                    catalyst_type=catalyst,
                    relevance_label=relevance,
                    debug={"raw_id": item.get("id")},
                )
            )

        summary = NewsSummary(
            timestamp=generated_at,
            source=source,
            headline_count=len(result),
            catalyst_breakdown=breakdown([item.catalyst_type for item in result]),
            key_items=result[:5],
        )
        return result, summary

    def classify_catalyst(self, headline: str, summary: str) -> str:
        haystack = f"{headline} {summary}".lower()
        for tag in ["earnings", "analyst", "macro", "sector", "product_company", "guidance", "regulatory"]:
            words = [str(word).lower() for word in list(self.keywords.get(tag, []))]
            if any(word and word in haystack for word in words):
                return tag
        return "unknown"
