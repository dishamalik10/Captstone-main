from __future__ import annotations

import json
from typing import Any

from settings import settings


_cache: dict[str, dict[str, Any]] = {}


def _read_disk_cache() -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(settings.trend_cache_path.read_text("utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _fallback(region: str) -> dict[str, Any]:
    return {
        "region": region,
        "generatedAt": None,
        "fresh": False,
        "stale": True,
        "source": "none",
        "trends": [],
        "sources": [],
        "note": "No local trend cache is available. Current trends were not used; wardrobe, occasion, and weather context remain active.",
    }


def current_fashion_trends(region: str = "India", force: bool = False) -> dict[str, Any]:
    if not _cache:
        _cache.update(_read_disk_cache())
    region = region.strip()[:80] or "India"
    cached = _cache.get(region.lower())
    if not cached:
        return _fallback(region)
    # Never label an old generated cache as current. There is deliberately no
    # refresh mechanism here because refresh used hosted search/generation.
    result = dict(cached)
    result.update({
        "region": region,
        "fresh": False,
        "stale": True,
        "source": "local_cache",
        "note": "Showing historical cached trend context. It may be outdated and is only a weak ranking signal.",
    })
    return result


def trend_relevance(items: list[dict[str, Any]], trends: dict[str, Any]) -> float:
    entries = trends.get("trends") or []
    if not entries:
        return 50.0
    item_tokens = set()
    for item in items:
        item_tokens.update(
            {
                item.get("category", "").lower(),
                item.get("color_name", "").lower(),
                item.get("subcategory", "").lower(),
                *(tag.lower() for tag in item.get("style_tags", [])),
            }
        )
    matches = 0
    for trend in entries:
        tokens = {
            *(str(value).lower() for value in trend.get("categories", [])),
            *(str(value).lower() for value in trend.get("colors", [])),
            *(str(value).lower() for value in trend.get("keywords", [])),
        }
        if item_tokens.intersection(tokens):
            matches += 1
    return min(100.0, 45.0 + matches * 11.0)
