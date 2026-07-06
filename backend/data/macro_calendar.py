"""Rate-relevant US macro indicators for the "Today" tab.

Each indicator carries: the latest actual reading (transformed to the number that
actually matters — YoY for price indices, MoM change for payrolls, level for
rates), the prior reading, the direction of surprise, its rate-policy meaning,
and a best-effort *next scheduled release date* pulled from the FRED release
calendar. Consensus/forecast numbers are NOT invented here — where a public
consensus feed is unavailable the panel shows the schedule + prior as the
reference point, and the market's own forward expectation is surfaced via the
breakeven/inflation-expectation series (which ARE expectations).

All network calls degrade gracefully: a failed series or release lookup yields
nulls, never an exception into the request.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date

import httpx

from backend.config import settings
from backend.data.cache import data_cache

logger = logging.getLogger("fed_watcher.macro_calendar")

FRED_BASE = "https://api.stlouisfed.org/fred"
_VALUE_TTL = 4 * 3600
_RELEASE_TTL = 12 * 3600

# transform: how the raw FRED series becomes the number people quote
#   yoy    → year-over-year % (needs ~13 monthly obs)
#   mom_k  → month-over-month change, in thousands (payrolls)
#   level  → the value as-is (rates, unemployment, GDP q/q annualized)
#   level_k→ the value as-is but in thousands with a K suffix (jobless claims)
#   mom_pct→ month-over-month % (retail sales)
INDICATORS = [
    # key, series, ko name, en name, category, unit, transform, impact, meaning_ko
    ("cpi",      "CPIAUCSL", "소비자물가지수 (CPI)",       "CPI (headline)",          "inflation",    "%",   "yoy",    "high",   "높으면 매파적 — 금리 인하 지연"),
    ("core_cpi", "CPILFESL", "근원 CPI",                  "Core CPI",                "inflation",    "%",   "yoy",    "high",   "연준이 더 주시하는 기조적 물가"),
    ("pce",      "PCEPI",    "PCE 물가지수",               "PCE (headline)",          "inflation",    "%",   "yoy",    "high",   "연준 공식 물가 목표(2%)의 기준"),
    ("core_pce", "PCEPILFE", "근원 PCE",                  "Core PCE",                "inflation",    "%",   "yoy",    "high",   "연준의 핵심 인플레 지표"),
    ("nfp",      "PAYEMS",   "비농업 고용 (NFP)",          "Nonfarm Payrolls",        "labor",        "K",   "mom_k",  "high",   "강하면 매파적 — 노동시장 과열"),
    ("unemp",    "UNRATE",   "실업률",                     "Unemployment Rate",       "labor",        "%",   "level",  "high",   "오르면 비둘기적 — 인하 명분"),
    ("claims",   "ICSA",     "주간 신규 실업수당 청구",      "Initial Jobless Claims",  "labor",        "K",   "level_k","medium", "급증 시 경기 둔화 신호"),
    ("retail",   "RSAFS",    "소매판매 (MoM)",             "Retail Sales (MoM)",      "growth",       "%",   "mom_pct","medium", "소비 강도 — 성장·물가 압력"),
    ("gdp",      "A191RL1Q225SBEA", "실질 GDP (연율 QoQ)",  "Real GDP (QoQ, ann.)",    "growth",       "%",   "level",  "medium", "성장 속도 — 정책 여력"),
    ("infexp5",  "T5YIE",    "기대 인플레 (5년 BEI)",       "5Y Breakeven Inflation",  "expectations", "%",   "level",  "high",   "시장이 반영한 5년 기대 물가"),
    ("infexp10", "T10YIE",   "기대 인플레 (10년 BEI)",      "10Y Breakeven Inflation", "expectations", "%",   "level",  "medium", "시장이 반영한 장기 기대 물가"),
    ("mich",     "MICH",     "기대 인플레 (미시간 1년)",     "UMich 1Y Inflation Exp.", "expectations", "%",   "level",  "medium", "가계 설문 1년 기대 물가"),
    ("dff",      "DFF",      "실효 연방기금금리",           "Effective Fed Funds Rate","policy",       "%",   "level",  "high",   "현재 정책금리 수준"),
]

# FRED release_id per indicator — used to look up the next scheduled release date.
# Rates/expectations (daily/continuous) carry no discrete "release event".
_RELEASE_ID = {
    "cpi": 10, "core_cpi": 10,          # Consumer Price Index
    "pce": 21, "core_pce": 21,          # Personal Income & Outlays
    "nfp": 50, "unemp": 50,             # Employment Situation
    "claims": 180,                       # UI Weekly Claims
    "retail": 41,                        # Advance Retail Sales
    "gdp": 53,                           # Gross Domestic Product
}


def _fmt(value: float | None, unit: str, transform: str) -> str | None:
    if value is None:
        return None
    if transform == "mom_k":
        return f"{value:+,.0f}K"          # PAYEMS already in thousands
    if transform == "level_k":
        return f"{value / 1000:,.0f}K"    # ICSA reported in persons → thousands
    if unit == "%":
        sign = "+" if transform in ("yoy", "mom_pct") and value > 0 else ""
        return f"{sign}{value:.1f}%"
    return f"{value:,.1f}"


async def _fetch_points(series_id: str, limit: int = 16) -> list[dict]:
    """Recent observations ascending (date, value). Cached, non-throwing."""
    key = f"cal_points_{series_id}"
    cached = data_cache.get(key, ttl_seconds=_VALUE_TTL)
    if cached is not None:
        return cached
    try:
        params = {
            "series_id": series_id, "api_key": settings.FRED_API_KEY,
            "file_type": "json", "limit": limit, "sort_order": "desc",
        }
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{FRED_BASE}/series/observations", params=params)
            r.raise_for_status()
        obs = [o for o in r.json().get("observations", []) if o["value"] not in (".", "")]
        obs.reverse()
        pts = [{"date": o["date"], "value": float(o["value"])} for o in obs]
    except Exception as e:
        logger.info("macro points %s failed: %s", series_id, e)
        pts = []
    data_cache.set(key, pts)
    return pts


def _transform(pts: list[dict], transform: str) -> tuple[float | None, float | None]:
    """Return (latest_display_value, prior_display_value) per transform rule."""
    if not pts:
        return None, None
    vals = [p["value"] for p in pts]
    if transform == "yoy":
        if len(vals) >= 13:
            latest = (vals[-1] / vals[-13] - 1) * 100
            prior = (vals[-2] / vals[-14] - 1) * 100 if len(vals) >= 14 else None
            return round(latest, 2), (round(prior, 2) if prior is not None else None)
        return None, None
    if transform == "mom_k":
        latest = vals[-1] - vals[-2] if len(vals) >= 2 else None
        prior = vals[-2] - vals[-3] if len(vals) >= 3 else None
        return (round(latest) if latest is not None else None,
                round(prior) if prior is not None else None)
    if transform == "mom_pct":
        latest = (vals[-1] / vals[-2] - 1) * 100 if len(vals) >= 2 else None
        prior = (vals[-2] / vals[-3] - 1) * 100 if len(vals) >= 3 else None
        return (round(latest, 2) if latest is not None else None,
                round(prior, 2) if prior is not None else None)
    # level / level_k
    return vals[-1], (vals[-2] if len(vals) >= 2 else None)


async def _next_release(key: str) -> str | None:
    """Best-effort next scheduled release date (YYYY-MM-DD) from FRED. None if
    unknown or not a discrete release (rates/expectations)."""
    rid = _RELEASE_ID.get(key)
    if rid is None:
        return None
    ck = f"cal_release_{rid}"
    cached = data_cache.get(ck, ttl_seconds=_RELEASE_TTL)
    if cached is not None:
        return cached or None
    today = date.today().isoformat()
    nxt = ""
    try:
        params = {
            "release_id": rid, "api_key": settings.FRED_API_KEY, "file_type": "json",
            "include_release_dates_with_no_data": "true",
            "sort_order": "asc", "realtime_start": today, "realtime_end": "9999-12-31",
            "limit": 60,
        }
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.get(f"{FRED_BASE}/release/dates", params=params)
            r.raise_for_status()
        for d in r.json().get("release_dates", []):
            if d.get("date", "") >= today:
                nxt = d["date"]
                break
    except Exception as e:
        logger.info("release date %s failed: %s", key, e)
    data_cache.set(ck, nxt)
    return nxt or None


async def _one(meta: tuple) -> dict:
    key, series_id, name_ko, name_en, category, unit, transform, impact, meaning = meta
    pts = await _fetch_points(series_id)
    latest_v, prior_v = _transform(pts, transform)
    nxt = await _next_release(key)
    latest_date = pts[-1]["date"] if pts else None
    change = (latest_v - prior_v) if (latest_v is not None and prior_v is not None) else None
    return {
        "key": key,
        "series_id": series_id,
        "name_ko": name_ko,
        "name_en": name_en,
        "category": category,
        "unit": unit,
        "impact": impact,
        "meaning_ko": meaning,
        "latest_value": latest_v,
        "latest_display": _fmt(latest_v, unit, transform),
        "latest_date": latest_date,
        "prior_value": prior_v,
        "prior_display": _fmt(prior_v, unit, transform),
        "change": round(change, 2) if change is not None else None,
        "next_release": nxt,
    }


async def get_macro_indicators() -> dict:
    """Full indicator panel. Cached 1h so the Today tab is snappy."""
    ck = "macro_indicators_panel"
    cached = data_cache.get(ck, ttl_seconds=3600)
    if cached is not None:
        return cached
    rows = await asyncio.gather(*[_one(m) for m in INDICATORS])
    payload = {"as_of": date.today().isoformat(), "indicators": list(rows)}
    data_cache.set(ck, payload)
    return payload
