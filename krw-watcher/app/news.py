"""
뉴스 스크랩: Google News RSS에서 원/달러 관련 기사를 수집해 키워드 점수로
선별한다 (키 불필요). PC krw-watcher의 '뉴스 스크랩 (핵심 기사 선별)' 포팅.
"""
import html
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from . import collector

logger = logging.getLogger("krw_watcher.news")
KST = ZoneInfo("Asia/Seoul")

FEEDS = [
    ("원/달러 환율", "https://news.google.com/rss/search?q=%EC%9B%90%EB%8B%AC%EB%9F%AC%20%ED%99%98%EC%9C%A8&hl=ko&gl=KR&ceid=KR:ko"),
    ("USD/KRW exchange rate", "https://news.google.com/rss/search?q=USD%2FKRW%20exchange%20rate&hl=en-US&gl=US&ceid=US:en"),
    ("외환당국·한국은행", "https://news.google.com/rss/search?q=%EC%99%B8%ED%99%98%EB%8B%B9%EA%B5%AD%20OR%20%ED%95%9C%EA%B5%AD%EC%9D%80%ED%96%89%20%ED%99%98%EC%9C%A8&hl=ko&gl=KR&ceid=KR:ko"),
]

_SCORE_WORDS = {
    "환율": 2.0, "원달러": 2.5, "원/달러": 2.5, "원화": 1.5, "달러": 1.0,
    "개입": 2.0, "한국은행": 1.5, "연준": 1.5, "fed": 1.2, "금리": 1.2,
    "intervention": 2.0, "usd/krw": 3.0, "krw": 2.0, "won": 1.5,
    "forecast": 1.5, "전망": 1.5, "급등": 1.2, "급락": 1.2, "1500": 1.0, "1600": 1.0,
}

_cache: dict[str, Any] = {"items": [], "fetched": 0.0}
TTL = 1800  # 30 min


def _score(title: str) -> float:
    low = title.lower()
    s = 1.0
    for w, v in _SCORE_WORDS.items():
        if w in low:
            s += v
    return round(s, 1)


def _parse_rss(source: str, xml: str) -> list[dict]:
    items = []
    for m in re.finditer(r"<item>(.*?)</item>", xml, flags=re.S):
        block = m.group(1)
        def tag(name: str) -> str:
            t = re.search(rf"<{name}>(.*?)</{name}>", block, flags=re.S)
            v = t.group(1).strip() if t else ""
            v = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", v, flags=re.S)
            return html.unescape(re.sub(r"<[^>]+>", "", v)).strip()
        title = tag("title")
        if not title:
            continue
        items.append({
            "source": source,
            "title": title[:200],
            "link": tag("link")[:400],
            "published": tag("pubDate")[:40],
            "score": _score(title),
        })
    return items


async def refresh(force: bool = False) -> list[dict]:
    if not force and _cache["items"] and time.time() - _cache["fetched"] < TTL:
        return _cache["items"]
    all_items: list[dict] = []
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for source, url in FEEDS:
            try:
                r = await client.get(url, timeout=20,
                                     headers={"User-Agent": "Mozilla/5.0 krw-watcher/1.0"})
                r.raise_for_status()
                all_items.extend(_parse_rss(source, r.text)[:20])
            except Exception as e:
                logger.info("news feed %s failed: %s", source, str(e)[:80])
    if all_items:
        seen, dedup = set(), []
        for it in sorted(all_items, key=lambda x: -x["score"]):
            key = it["title"][:60]
            if key in seen:
                continue
            seen.add(key)
            dedup.append(it)
        _cache["items"] = dedup[:40]
        _cache["fetched"] = time.time()
        collector.emit("news", f"뉴스 스크랩: {len(dedup)}건 선별", "ok")
    return _cache["items"]


async def headline_lines(limit: int = 8) -> list[str]:
    items = await refresh()
    return [f"- [{i['score']}] {i['title']}" for i in items[:limit]]


async def api_payload() -> dict:
    items = await refresh()
    today = datetime.now(KST).date().isoformat()
    return {"days": [{"date": today, "count": len(items), "articles": items}]}
