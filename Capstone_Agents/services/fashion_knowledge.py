"""Small, local retrieval over original, explicitly heuristic styling notes."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

KNOWLEDGE_PATH = Path(__file__).resolve().parents[1] / "knowledge" / "fashion_heuristics.json"


def _load() -> dict[str, Any]:
    return json.loads(KNOWLEDGE_PATH.read_text(encoding="utf-8"))


def retrieve_guidance(query: str, limit: int = 4) -> list[dict[str, Any]]:
    """Retrieve local sourced paraphrases and authored heuristics with provenance."""
    payload = _load()
    normalized = re.sub(r"[^a-z0-9]+", " ", query.lower()).strip()
    words = set(normalized.split())
    ranked: list[tuple[int, int, dict[str, Any]]] = []
    for index, entry in enumerate(payload["entries"]):
        topics = [re.sub(r"[^a-z0-9]+", " ", topic.lower()).strip() for topic in entry["topics"]]
        topic_words = {word for topic in topics for word in topic.split()}
        score = len(words & topic_words)
        score += 2 * sum(1 for topic in topics if topic and topic in normalized)
        if score:
            result = {key: value for key, value in entry.items() if key != "source_id"}
            source_id = entry.get("source_id")
            if source_id:
                result["source"] = next(
                    (source for source in payload["sources"] if source["id"] == source_id),
                    None,
                )
            ranked.append((-score, index, result))
    ranked.sort(key=lambda value: (value[0], value[1]))
    return [entry for _, _, entry in ranked[:max(0, limit)]]


def knowledge_metadata() -> dict[str, str]:
    payload = _load()
    return {
        "provenance": payload["purpose"],
        "license": "Mixed: per-entry source licenses are listed in the source registry; original notes are CC BY 4.0.",
    }


def source_registry() -> list[dict[str, str]]:
    """Return bibliography and exact reuse terms for sourced prompt notes."""
    return _load()["sources"]
