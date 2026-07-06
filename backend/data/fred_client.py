import httpx
from dataclasses import dataclass, field
from typing import Optional
from backend.config import settings
from backend.data.cache import data_cache

FRED_BASE = "https://api.stlouisfed.org/fred"
TTL = 4 * 3600  # 4시간 캐시

SERIES = {
    "DFF":      "Fed Funds Rate (Effective)",
    "T10Y2Y":   "10Y-2Y Yield Spread",
    "GS2":      "2Y Treasury Yield",
    "GS5":      "5Y Treasury Yield",
    "GS10":     "10Y Treasury Yield",
    "GS30":     "30Y Treasury Yield",
    "CPIAUCSL": "CPI All Urban Consumers",
    "CPILFESL": "Core CPI (ex Food & Energy)",
    "PCEPI":    "PCE Price Index",
    "PCEPILFE": "Core PCE Price Index",
    "PAYEMS":   "Nonfarm Payrolls",
    "UNRATE":   "Unemployment Rate",
    "ICSA":     "Initial Jobless Claims",
    "RSAFS":    "Advance Retail Sales",
    "T5YIE":    "5Y Breakeven Inflation",
    "T10YIE":   "10Y Breakeven Inflation",
    "MICH":     "UMich 1Y Inflation Expectations",
    "A191RL1Q225SBEA": "Real GDP (QoQ, annualized)",
    "SOFR":     "Secured Overnight Financing Rate",
}


@dataclass
class SeriesData:
    series_id: str
    label: str
    latest_value: Optional[float]
    latest_date: Optional[str]
    prior_value: Optional[float]
    mom_change: Optional[float]


@dataclass
class MacroSnapshot:
    series: dict[str, SeriesData] = field(default_factory=dict)

    def get(self, series_id: str) -> Optional[float]:
        s = self.series.get(series_id)
        return s.latest_value if s else None

    def summary_text(self) -> str:
        lines = []
        for sid, s in self.series.items():
            change = f" (chg: {s.mom_change:+.2f})" if s.mom_change is not None else ""
            lines.append(f"{s.label}: {s.latest_value} [{s.latest_date}]{change}")
        return "\n".join(lines)


async def fetch_series(series_id: str) -> SeriesData:
    cache_key = f"fred_{series_id}"
    cached = data_cache.get(cache_key, TTL)
    if cached:
        return SeriesData(**cached)

    params = {
        "series_id": series_id,
        "api_key": settings.FRED_API_KEY,
        "file_type": "json",
        "limit": 5,
        "sort_order": "desc",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{FRED_BASE}/series/observations", params=params)
        r.raise_for_status()
        obs = [o for o in r.json()["observations"] if o["value"] != "."]

    latest_val = float(obs[0]["value"]) if obs else None
    latest_date = obs[0]["date"] if obs else None
    prior_val = float(obs[1]["value"]) if len(obs) > 1 else None
    mom = round(latest_val - prior_val, 4) if (latest_val is not None and prior_val is not None) else None

    result = SeriesData(
        series_id=series_id,
        label=SERIES[series_id],
        latest_value=latest_val,
        latest_date=latest_date,
        prior_value=prior_val,
        mom_change=mom,
    )
    data_cache.set(cache_key, result.__dict__)
    return result


async def get_macro_snapshot() -> MacroSnapshot:
    import asyncio
    tasks = [fetch_series(sid) for sid in SERIES]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    snapshot = MacroSnapshot()
    for r in results:
        if isinstance(r, SeriesData):
            snapshot.series[r.series_id] = r
    return snapshot
