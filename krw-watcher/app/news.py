"""뉴스 스크랩 — 원본 계약 {days:[{date,count,articles}], total, count, articles}
그대로. Google News RSS(키 불필요) + 키워드 점수 선별, 발행일(KST) 기준 최근
7일 그룹핑."""
import html
import logging
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from . import collector

logger = logging.getLogger("krw_watcher.news")
KST = ZoneInfo("Asia/Seoul")

from urllib.parse import quote

def _gn(q: str, ko: bool = True) -> str:
    return ("https://news.google.com/rss/search?q=" + quote(q + " when:7d") +
            ("&hl=ko&gl=KR&ceid=KR:ko" if ko else "&hl=en-US&gl=US&ceid=US:en"))

FEEDS = [
    ("원/달러 환율", _gn("원달러 환율")),
    ("USD/KRW exchange rate", _gn("USD/KRW exchange rate", ko=False)),
    ("외환당국·개입", _gn("(외환당국 OR 구두개입 OR 스무딩오퍼레이션) 환율")),
    ("한국은행 리포트", _gn("한국은행 (보고서 OR 이슈노트 OR 금통위 OR 기준금리)")),
    ("경상수지·환류", _gn("경상수지 OR 무역수지 OR 본원소득수지 OR 배당 환류")),
    ("통화량·유동성", _gn("(M2 OR 통화량 OR 유동성) 원화")),
    ("정부 정책·기재부", _gn("기획재정부 (환율 OR 외환 OR 밸류업)")),
    ("리스크·지정학", _gn("(지정학 OR 신용등급 OR 자본유출) 원화 환율")),
]
_SCORE = {"환율": 2.0, "원달러": 2.5, "원/달러": 2.5, "원화": 1.5, "달러": 1.0, "개입": 2.5,
          "한국은행": 1.8, "금통위": 2.0, "연준": 1.5, "fed": 1.2, "금리": 1.2, "intervention": 2.0,
          "usd/krw": 3.0, "krw": 2.0, "won": 1.5, "forecast": 1.5, "전망": 1.5,
          "경상수지": 2.2, "무역수지": 1.8, "본원소득": 2.2, "환류": 2.5, "배당": 1.3,
          "통화량": 2.0, "m2": 2.0, "유동성": 1.3, "기재부": 1.8, "기획재정부": 1.8,
          "구두개입": 2.8, "스무딩": 2.8, "외환보유액": 2.0, "국민연금": 1.8, "환헤지": 2.0,
          "지정학": 1.5, "신용등급": 1.8, "자본유출": 2.0,
          "급등": 1.2, "급락": 1.2, "1500": 1.0, "1600": 1.0}

_cache: dict[str, Any] = {"items": [], "fetched": 0.0}
TTL = 1800


def _score(title: str) -> float:
    low = title.lower()
    return round(1.0 + sum(v for w, v in _SCORE.items() if w in low), 1)


def _parse(source: str, xml: str) -> list[dict]:
    out = []
    for m in re.finditer(r"<item>(.*?)</item>", xml, flags=re.S):
        blk = m.group(1)
        def tag(n: str) -> str:
            t = re.search(rf"<{n}>(.*?)</{n}>", blk, flags=re.S)
            v = t.group(1).strip() if t else ""
            v = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", v, flags=re.S)
            return html.unescape(re.sub(r"<[^>]+>", "", v)).strip()
        title = tag("title")
        if not title:
            continue
        pub = tag("pubDate")
        try:
            date = parsedate_to_datetime(pub).astimezone(KST).date().isoformat()
        except Exception:
            date = datetime.now(KST).date().isoformat()
        out.append({"source": source, "title": title[:200], "link": tag("link")[:400],
                    "published": pub[:40], "score": _score(title), "date": date})
    return out


async def refresh(force: bool = False) -> list[dict]:
    if not force and _cache["items"] and time.time() - _cache["fetched"] < TTL:
        return _cache["items"]
    items: list[dict] = []
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for source, url in FEEDS:
            try:
                r = await client.get(url, timeout=20,
                                     headers={"User-Agent": "Mozilla/5.0 krw-watcher"})
                r.raise_for_status()
                items.extend(_parse(source, r.text)[:35])
            except Exception as e:
                logger.info("feed %s failed: %s", source, str(e)[:80])
    if items:
        seen, dedup = set(), []
        for it in sorted(items, key=lambda x: (-x["score"])):
            key = it["title"][:60]
            if key not in seen:
                seen.add(key)
                dedup.append(it)
        _cache["items"] = dedup
        _cache["fetched"] = time.time()
        collector.emit("collector", f"뉴스 스크랩: {len(dedup)}건 선별", "ok")
    return _cache["items"]


async def headline_lines(limit: int = 8) -> list[str]:
    items = await refresh()
    return [f"- [{i['score']}] {i['title']}" for i in items[:limit]]


async def api_payload() -> dict:
    items = await refresh()
    by_day: dict[str, list] = {}
    for it in items:
        by_day.setdefault(it["date"], []).append(
            {k: it[k] for k in ("source", "title", "link", "published", "score")})
    days = [{"date": d, "count": len(v),
             "articles": sorted(v, key=lambda a: -a["score"])[:30]}
            for d, v in sorted(by_day.items(), reverse=True)][:7]
    today = days[0]["articles"] if days else []
    return {"days": days, "total": len(items), "count": len(today), "articles": today}
