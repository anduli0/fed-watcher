"""
USD/KRW market data collection with multi-source fallback.

Primary: Yahoo Finance chart API (intraday + history, no key).
Fallbacks: open.er-api.com (hourly spot, no key), frankfurter.app (ECB daily).
Context indicators (dollar index, US 10Y, USD/JPY, KOSPI) are best-effort.

Everything is cached in memory; chart ranges have their own TTLs so the
dashboard never triggers a remote fetch storm.
"""
import asyncio
import logging
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger("krw_watcher.collector")

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 krw-watcher/1.0"}
YQ = "https://query1.finance.yahoo.com/v8/finance/chart"

# range -> (yahoo range, yahoo interval, cache ttl seconds)
RANGES = {
    "1d": ("1d", "5m", 600),
    "1w": ("5d", "30m", 1800),
    "1mo": ("1mo", "1d", 7200),
    "1y": ("1y", "1d", 21600),
}

CONTEXT_SYMBOLS = {
    "dxy": ("DX-Y.NYB", "달러인덱스"),
    "us10y": ("^TNX", "미국 10년물(%)"),
    "usdjpy": ("JPY=X", "엔/달러"),
    "kospi": ("^KS11", "코스피"),
}

# ── State ────────────────────────────────────────────────────────────────────
latest: dict[str, Any] = {}          # {"rate", "prev_close", "change", "change_pct", "source", "market_time", "collected_at"}
context: dict[str, Any] = {}         # {key: {"label","price","change_pct"}}
_charts: dict[str, dict] = {}        # range -> {"points": [[ts,close],...], "fetched": epoch}
activity: deque = deque(maxlen=300)  # [{"ts","source","message","status"}]


def emit(source: str, message: str, status: str = "info") -> None:
    activity.appendleft({
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "message": message,
        "status": status,
    })
    log = logger.error if status == "error" else logger.info
    log("[%s] %s", source, message)


async def _yahoo_chart(client: httpx.AsyncClient, symbol: str, rng: str, interval: str) -> dict:
    r = await client.get(
        f"{YQ}/{symbol}",
        params={"range": rng, "interval": interval, "includePrePost": "false"},
        headers=UA, timeout=20,
    )
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    meta = res.get("meta", {})
    ts = res.get("timestamp") or []
    closes = (res.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
    points = [[t, c] for t, c in zip(ts, closes) if c is not None]
    return {"meta": meta, "points": points}


async def collect_latest() -> Optional[dict]:
    """Refresh the live USD/KRW quote. Returns the new snapshot or None."""
    global latest
    now = datetime.now(timezone.utc).isoformat()

    async with httpx.AsyncClient() as client:
        # 1) Yahoo — live-ish price plus previous close for the daily change
        try:
            data = await _yahoo_chart(client, "KRW=X", "1d", "5m")
            meta = data["meta"]
            rate = meta.get("regularMarketPrice")
            prev = meta.get("chartPreviousClose") or meta.get("previousClose")
            if rate:
                mkt_ts = meta.get("regularMarketTime")
                latest = {
                    "rate": round(float(rate), 2),
                    "prev_close": round(float(prev), 2) if prev else None,
                    "change": round(float(rate) - float(prev), 2) if prev else None,
                    "change_pct": round((float(rate) / float(prev) - 1) * 100, 3) if prev else None,
                    "source": "yahoo",
                    "market_time": datetime.fromtimestamp(mkt_ts, tz=timezone.utc).isoformat() if mkt_ts else None,
                    "collected_at": now,
                }
                _charts["1d"] = {"points": data["points"], "fetched": time.time()}
                emit("collector", f"환율 수집 성공(yahoo): {latest['rate']}원", "ok")
                return latest
        except Exception as e:
            emit("collector", f"yahoo 수집 실패: {str(e)[:120]}", "error")

        # 2) open.er-api.com — hourly spot, rate only
        try:
            r = await client.get("https://open.er-api.com/v6/latest/USD", timeout=20)
            r.raise_for_status()
            j = r.json()
            rate = j.get("rates", {}).get("KRW")
            if rate:
                prev = latest.get("prev_close")
                latest = {
                    "rate": round(float(rate), 2),
                    "prev_close": prev,
                    "change": round(float(rate) - prev, 2) if prev else None,
                    "change_pct": round((float(rate) / prev - 1) * 100, 3) if prev else None,
                    "source": "er-api",
                    "market_time": j.get("time_last_update_utc"),
                    "collected_at": now,
                }
                emit("collector", f"환율 수집 성공(er-api): {latest['rate']}원", "ok")
                return latest
        except Exception as e:
            emit("collector", f"er-api 수집 실패: {str(e)[:120]}", "error")

        # 3) frankfurter — ECB reference (daily)
        try:
            r = await client.get(
                "https://api.frankfurter.app/latest",
                params={"from": "USD", "to": "KRW"}, timeout=20,
            )
            r.raise_for_status()
            j = r.json()
            rate = j.get("rates", {}).get("KRW")
            if rate:
                latest = {
                    "rate": round(float(rate), 2),
                    "prev_close": None, "change": None, "change_pct": None,
                    "source": "frankfurter(ECB)",
                    "market_time": j.get("date"),
                    "collected_at": now,
                }
                emit("collector", f"환율 수집 성공(ECB): {latest['rate']}원", "ok")
                return latest
        except Exception as e:
            emit("collector", f"frankfurter 수집 실패: {str(e)[:120]}", "error")

    emit("collector", "모든 환율 소스 수집 실패", "error")
    return None


async def collect_context() -> dict:
    """Best-effort refresh of surrounding indicators (never raises)."""
    global context
    out: dict[str, Any] = {}
    async with httpx.AsyncClient() as client:
        for key, (symbol, label) in CONTEXT_SYMBOLS.items():
            try:
                data = await _yahoo_chart(client, symbol, "1d", "15m")
                meta = data["meta"]
                price = meta.get("regularMarketPrice")
                prev = meta.get("chartPreviousClose") or meta.get("previousClose")
                if price:
                    out[key] = {
                        "label": label,
                        "price": round(float(price), 2),
                        "change_pct": round((float(price) / float(prev) - 1) * 100, 2) if prev else None,
                    }
            except Exception as e:
                logger.info("context %s failed: %s", symbol, str(e)[:80])
    if out:
        context = out
        emit("collector", f"보조지표 수집: {', '.join(out)}", "ok")
    return context


async def _stooq_daily(client: httpx.AsyncClient, days: int) -> list:
    """Daily USD/KRW history from stooq (CSV, no key) — fallback when Yahoo
    refuses datacenter IPs. Returns [[epoch, close], ...] for the last N days."""
    r = await client.get("https://stooq.com/q/d/l/", params={"s": "usdkrw", "i": "d"},
                         headers=UA, timeout=20)
    r.raise_for_status()
    lines = r.text.strip().splitlines()[1:]  # Date,Open,High,Low,Close,(Volume)
    pts = []
    for ln in lines[-days:]:
        cols = ln.split(",")
        if len(cols) >= 5:
            try:
                ts = int(datetime.strptime(cols[0], "%Y-%m-%d")
                         .replace(tzinfo=timezone.utc).timestamp())
                pts.append([ts, float(cols[4])])
            except ValueError:
                continue
    return pts


_STOOQ_DAYS = {"1w": 7, "1mo": 31, "1y": 366}


async def get_chart(rng: str) -> dict:
    """Return cached chart points for a range, refreshing when the TTL lapsed."""
    if rng not in RANGES:
        rng = "1d"
    yrange, yint, ttl = RANGES[rng]
    cached = _charts.get(rng)
    if cached and time.time() - cached["fetched"] < ttl and cached["points"]:
        return {"range": rng, "points": cached["points"], "cached": True}
    try:
        async with httpx.AsyncClient() as client:
            data = await _yahoo_chart(client, "KRW=X", yrange, yint)
        _charts[rng] = {"points": data["points"], "fetched": time.time()}
        return {"range": rng, "points": data["points"], "cached": False}
    except Exception as e:
        emit("collector", f"차트({rng}) yahoo 실패: {str(e)[:100]}", "error")
        if rng in _STOOQ_DAYS:
            try:
                async with httpx.AsyncClient() as client:
                    pts = await _stooq_daily(client, _STOOQ_DAYS[rng])
                if pts:
                    _charts[rng] = {"points": pts, "fetched": time.time()}
                    emit("collector", f"차트({rng}) stooq 폴백 성공", "ok")
                    return {"range": rng, "points": pts, "cached": False, "source": "stooq"}
            except Exception as e2:
                emit("collector", f"차트({rng}) stooq 폴백 실패: {str(e2)[:100]}", "error")
        if cached:
            return {"range": rng, "points": cached["points"], "cached": True, "stale": True}
        return {"range": rng, "points": [], "error": str(e)[:200]}


def pct_change_over(rng: str) -> Optional[float]:
    """% change of the cached range series (first vs last point)."""
    pts = (_charts.get(rng) or {}).get("points") or []
    if len(pts) < 2 or not pts[0][1]:
        return None
    return round((pts[-1][1] / pts[0][1] - 1) * 100, 2)
