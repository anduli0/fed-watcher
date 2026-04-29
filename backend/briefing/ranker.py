"""
Deduplication, relevance scoring, and article selection for the briefing pipeline.
"""
from __future__ import annotations
import re
import logging
from datetime import datetime

from backend.briefing.fetcher import ArticleData
from backend.briefing.sources import MACRO_KEYWORDS

logger = logging.getLogger("fed_watcher.briefing.ranker")

MIN_ARTICLES_FOR_BRIEFING = 3   # lowered: Google News alone gives 10+
TARGET_ARTICLE_COUNT = 30


def _token_set(text: str) -> set[str]:
    """Lowercase words, strip punctuation — for title similarity."""
    return set(re.findall(r"[a-z0-9]{3,}", text.lower()))


def _title_similarity(a: str, b: str) -> float:
    """Jaccard similarity of token sets. 1.0 = identical."""
    ta, tb = _token_set(a), _token_set(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def deduplicate(articles: list[ArticleData]) -> list[ArticleData]:
    """
    Dedup by:
    1. Canonical URL — exact match → keep first seen
    2. Title similarity ≥ 0.70 → keep higher-scored (or first if not yet scored)
    """
    seen_urls: set[str] = set()
    deduped: list[ArticleData] = []

    for art in articles:
        url = art["canonical_url"]
        if url in seen_urls:
            continue

        # Check title similarity against already-kept articles
        is_dup = False
        for kept in deduped:
            if _title_similarity(art["title"], kept["title"]) >= 0.70:
                is_dup = True
                break

        if not is_dup:
            seen_urls.add(url)
            deduped.append(art)

    logger.info("Dedup: %d → %d articles", len(articles), len(deduped))
    return deduped


def _keyword_score(text: str) -> float:
    """Score based on macro keyword presence. Returns 0.0–1.0 normalized."""
    text_lower = text.lower()
    score = 0.0
    for kw, weight in MACRO_KEYWORDS.items():
        if kw in text_lower:
            score += weight
    return min(score / 10.0, 1.0)  # normalize; max ~10 weighted hits = 1.0


def _recency_score(pub_dt: datetime | None) -> float:
    """Newer = higher score. Returns 0.0–1.0."""
    if pub_dt is None:
        return 0.5
    age_hours = max(0.0, (datetime.utcnow() - pub_dt).total_seconds() / 3600)
    return max(0.0, 1.0 - age_hours / 36.0)  # decays to 0 after 36h


def _source_weight(source_id: str) -> float:
    from backend.briefing.sources import ENABLED_SOURCES
    for src in ENABLED_SOURCES:
        if src.id == source_id:
            return src.reliability_weight
    return 0.5


def score_and_rank(articles: list[ArticleData]) -> list[tuple[float, ArticleData]]:
    """
    Score each article and return sorted (score DESC) list.
    Score = 0.5 * keyword_relevance + 0.25 * recency + 0.25 * source_reliability
    """
    scored = []
    for art in articles:
        combined_text = f"{art['title']} {art['snippet']}"
        kw  = _keyword_score(combined_text)
        rec = _recency_score(art["published_at"])
        src = _source_weight(art["source_id"])
        score = 0.50 * kw + 0.25 * rec + 0.25 * src
        scored.append((score, art))

    scored.sort(key=lambda x: -x[0])
    return scored


def ensure_category_coverage(
    scored: list[tuple[float, ArticleData]],
    n: int = TARGET_ARTICLE_COUNT,
) -> list[ArticleData]:
    """
    Select top N articles while ensuring each category has at least 1 representative.
    Avoids pure equity-only domination.
    """
    # Category priority map: prefer fed/macro over equity noise
    priority_tags = [
        "fed", "monetary_policy", "bonds", "treasury", "fiscal_policy",
        "inflation", "labor_market", "growth", "financial_markets",
        "banks_credit", "risk_sentiment", "equities", "industry",
    ]

    # First: take top-scoring item from each priority tag (ensure coverage)
    included_urls: set[str] = set()
    selected: list[ArticleData] = []

    for tag in priority_tags:
        for score, art in scored:
            if art["canonical_url"] in included_urls:
                continue
            if tag in art["topic_tags"]:
                selected.append(art)
                included_urls.add(art["canonical_url"])
                break

    # Then: fill remaining slots with top-scored articles
    for _, art in scored:
        if len(selected) >= n:
            break
        if art["canonical_url"] not in included_urls:
            selected.append(art)
            included_urls.add(art["canonical_url"])

    logger.info("Selected %d articles for briefing", len(selected))
    return selected[:n]
