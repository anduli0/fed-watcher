"""
RSS feed fetcher for the daily briefing pipeline.
Uses httpx for async HTTP and feedparser for RSS parsing.
Stores only: title, URL, snippet, author, published_at — no full article bodies.
"""
from __future__ import annotations
import asyncio
import hashlib
import logging
import re
import urllib.parse
from datetime import datetime, timedelta
from typing import TypedDict

import feedparser
import httpx

from backend.briefing.sources import NewsSource, ENABLED_SOURCES

logger = logging.getLogger("fed_watcher.briefing.fetcher")

FETCH_TIMEOUT = 20.0   # seconds per feed
MAX_SNIPPET_CHARS = 500
LOOKBACK_HOURS_NEWS = 48     # news feeds: last 48h
LOOKBACK_HOURS_OFFICIAL = 168  # official govt sources: last 7 days (they publish infrequently)


class ArticleData(TypedDict):
    source_id: str
    source_name: str
    title: str
    url: str
    canonical_url: str
    author: str
    published_at: datetime | None
    snippet: str
    topic_tags: list[str]


def _normalize_url(url: str) -> str:
    """Strip UTM params and normalize URL for deduplication."""
    try:
        parsed = urllib.parse.urlparse(url)
        # Remove tracking params
        qs = urllib.parse.parse_qs(parsed.query)
        clean_qs = {k: v for k, v in qs.items()
                    if not k.lower().startswith(("utm_", "source", "ref", "fbclid", "gclid"))}
        clean_query = urllib.parse.urlencode(clean_qs, doseq=True)
        normalized = urllib.parse.urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower().lstrip("www."),
            parsed.path.rstrip("/"),
            parsed.params,
            clean_query,
            "",
        ))
        return normalized
    except Exception:
        return url.strip().lower()


def _extract_snippet(entry: feedparser.FeedParserDict) -> str:
    """Extract best available short text from RSS entry."""
    # Try summary first (RSS), then content
    text = ""
    if entry.get("summary"):
        text = entry.summary
    elif entry.get("content"):
        text = entry.content[0].get("value", "")
    # Strip HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:MAX_SNIPPET_CHARS]


def _parse_date(entry: feedparser.FeedParserDict) -> datetime | None:
    """Extract published date from RSS entry."""
    for field in ("published_parsed", "updated_parsed", "created_parsed"):
        val = entry.get(field)
        if val:
            try:
                return datetime(*val[:6])
            except Exception:
                pass
    return None


def _is_recent(dt: datetime | None, official: bool = False) -> bool:
    if dt is None:
        return True  # include if date unknown
    hours = LOOKBACK_HOURS_OFFICIAL if official else LOOKBACK_HOURS_NEWS
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    return dt >= cutoff


async def _fetch_feed(
    source: NewsSource,
    client: httpx.AsyncClient,
) -> list[ArticleData]:
    """Fetch and parse one RSS feed. Returns list of article metadata."""
    try:
        resp = await client.get(source.feed_url, timeout=FETCH_TIMEOUT)
        resp.raise_for_status()
        feed = await asyncio.get_event_loop().run_in_executor(
            None, feedparser.parse, resp.text
        )
    except Exception as exc:
        logger.warning("Feed fetch failed [%s]: %s", source.id, exc)
        return []

    is_official = source.category == "official"
    articles: list[ArticleData] = []
    for entry in feed.entries[: source.max_items]:
        url = entry.get("link", "")
        if not url:
            continue

        pub_date = _parse_date(entry)
        if not _is_recent(pub_date, official=is_official):
            continue

        title = entry.get("title", "").strip()
        if not title:
            continue

        canonical = _normalize_url(url)
        snippet = _extract_snippet(entry)
        author = entry.get("author", entry.get("author_detail", {}).get("name", ""))

        articles.append(ArticleData(
            source_id=source.id,
            source_name=source.name,
            title=title,
            url=url,
            canonical_url=canonical,
            author=str(author)[:200],
            published_at=pub_date,
            snippet=snippet,
            topic_tags=list(source.topic_tags),
        ))

    logger.info("Fetched %d articles from [%s]", len(articles), source.name)
    return articles


async def fetch_all_sources() -> list[ArticleData]:
    """Fetch all enabled sources concurrently and return merged article list."""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; FedWatcher/1.0; +https://fed-watcher.vercel.app)",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, verify=False) as client:
        tasks = [_fetch_feed(src, client) for src in ENABLED_SOURCES]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    all_articles: list[ArticleData] = []
    for r in results:
        if isinstance(r, list):
            all_articles.extend(r)
        elif isinstance(r, Exception):
            logger.error("Fetch task error: %s", r)

    logger.info("Total fetched: %d articles from %d sources", len(all_articles), len(ENABLED_SOURCES))
    return all_articles
