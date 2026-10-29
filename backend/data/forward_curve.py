"""Market-implied policy path per FOMC meeting, bootstrapped from the Treasury
bill / note curve (FRED, no CME dependency).

Zero rates y(t) at tenors 1m, 3m, 6m, 1y, 2y → piecewise-constant forward
rates f(t1,t2) = (y2·t2 − y1·t1)/(t2 − t1). The expected policy rate after a
meeting at horizon m is the forward for the segment containing m. Bills trade
at a roughly constant basis to fed funds, so the implied *change* at each
meeting is f(m) − y(1m), which cancels the level basis. Within 2 years this is
the standard "what the curve is pricing" anchor (term premium ≈ 0 at the
front end); beyond 2 years we return nothing and agents fall back to their
neutral-rate view.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import httpx

from backend.config import settings
from backend.data.cache import data_cache
from backend.fomc_calendar import HorizonSpec

TENORS = [("DGS1MO", 1 / 12), ("DGS3MO", 0.25), ("DGS6MO", 0.5), ("DGS1", 1.0), ("DGS2", 2.0)]
TTL = 4 * 3600
MAX_YEARS = 2.0


@dataclass
class ForwardPath:
    as_of: str
    dff: float | None
    zeros: dict[str, float]                 # tenor id → yield %
    implied_bps: dict[str, float]           # horizon key → implied cumulative change vs today (bps)

    def text_block(self, specs: list[HorizonSpec]) -> str:
        if not self.implied_bps:
            return ""
        lines = [f"Treasury curve {self.as_of}: " + " · ".join(f"{k} {v:.2f}%" for k, v in self.zeros.items())]
        lines.append("Market-implied cumulative change priced for each meeting (bill/note forwards, "
                     "basis-adjusted; ±10 bps is noise):")
        for s in specs:
            v = self.implied_bps.get(s.key)
            if v is None:
                continue
            lines.append(f'  "{s.key}"  {v:+.0f} bps  (≈ {round(v / 25) * 25:+.0f} in 25 bp steps)')
        lines.append("Beyond 2 years the curve carries term premium — anchor on your neutral-rate view instead.")
        return "\n".join(lines)


async def _latest(series_id: str) -> tuple[float | None, str | None]:
    cache_key = f"fwd_{series_id}"
    cached = data_cache.get(cache_key, TTL)
    if cached:
        return cached["v"], cached["d"]
    params = {"series_id": series_id, "api_key": settings.FRED_API_KEY,
              "file_type": "json", "limit": 5, "sort_order": "desc"}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://api.stlouisfed.org/fred/series/observations", params=params)
        r.raise_for_status()
    obs = [o for o in r.json().get("observations", []) if o["value"] != "."]
    if not obs:
        return None, None
    v, d = float(obs[0]["value"]), obs[0]["date"]
    data_cache.set(cache_key, {"v": v, "d": d})
    return v, d


def implied_changes(zeros: list[tuple[float, float]], months_ahead: list[float]) -> list[float | None]:
    """zeros = [(tenor_years, yield_pct)] ascending; returns implied change (bps)
    for each horizon in months, None beyond the last tenor."""
    if len(zeros) < 2:
        return [None] * len(months_ahead)
    fwd = []   # (t_start, t_end, forward)
    for (t1, y1), (t2, y2) in zip(zeros, zeros[1:]):
        fwd.append((t1, t2, (y2 * t2 - y1 * t1) / (t2 - t1)))
    y_short = zeros[0][1]
    out: list[float | None] = []
    for m in months_ahead:
        t = max(0.0, m) / 12.0
        if t > zeros[-1][0]:
            out.append(None)
            continue
        if t <= zeros[0][0]:
            out.append(0.0)
            continue
        f = next(fw for a, b, fw in fwd if a <= t <= b)
        out.append(round((f - y_short) * 100.0, 1))
    return out


async def market_forward_path(specs: list[HorizonSpec], dff: float | None = None) -> ForwardPath | None:
    zeros: dict[str, float] = {}
    as_of = None
    for sid, _ in TENORS:
        try:
            v, d = await _latest(sid)
        except Exception:
            v, d = None, None
        if v is not None:
            zeros[sid] = v
            as_of = max(as_of or d, d)
    pts = [(t, zeros[sid]) for sid, t in TENORS if sid in zeros]
    if len(pts) < 3:
        return None
    within = [s for s in specs if s.months_ahead / 12.0 <= MAX_YEARS]
    vals = implied_changes(pts, [s.months_ahead for s in within])
    implied = {s.key: v for s, v in zip(within, vals) if v is not None}
    return ForwardPath(as_of=as_of or date.today().isoformat(), dff=dff, zeros=zeros, implied_bps=implied)
