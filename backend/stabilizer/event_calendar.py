import httpx
from datetime import date
from backend.data.cache import data_cache

TTL = 12 * 3600

# Known release patterns (approximate; override with FRED release calendar)
# FOMC: ~8 times/year; CPI: monthly ~13th; NFP: monthly first Friday
MATERIAL_EVENTS = {
    "FOMC": {"alpha": 0.60, "label": "FOMC 결정 반영"},
    "CPI":  {"alpha": 0.50, "label": "CPI 서프라이즈 반영"},
    "NFP":  {"alpha": 0.45, "label": "고용 데이터 반영"},
}


async def get_today_event() -> dict | None:
    today = date.today().isoformat()
    cache_key = f"event_{today}"
    cached = data_cache.get(cache_key, TTL)
    if cached is not None:
        return cached if cached else None

    event = await _check_fred_releases(today)
    # Cache None as empty dict so we don't re-query
    data_cache.set(cache_key, event or {})
    return event


async def _check_fred_releases(today: str) -> dict | None:
    """Check FRED release calendar for today's material releases."""
    try:
        url = "https://api.stlouisfed.org/fred/releases/dates"
        from backend.config import settings
        params = {
            "api_key": settings.FRED_API_KEY,
            "file_type": "json",
            "realtime_start": today,
            "realtime_end": today,
            "limit": 50,
        }
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            releases = r.json().get("release_dates", [])

        names = [rel.get("release_name", "").upper() for rel in releases]
        if any("FOMC" in n or "FEDERAL OPEN" in n for n in names):
            return MATERIAL_EVENTS["FOMC"]
        if any("CONSUMER PRICE" in n for n in names):
            return MATERIAL_EVENTS["CPI"]
        if any("EMPLOYMENT SITUATION" in n or "NONFARM" in n for n in names):
            return MATERIAL_EVENTS["NFP"]
    except Exception:
        pass
    return None
