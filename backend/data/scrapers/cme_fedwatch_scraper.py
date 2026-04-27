"""
Market-implied Fed rate expectations.
CME FedWatch site is inaccessible (HTTP2 error), so we derive expectations
from FRED yield curve data — which encodes the same information.

Key insight:
  2Y Treasury yield ≈ market's expectation of average Fed Funds Rate over next 2 years
  SOFR ≈ overnight market rate (very close to DFF)
  Spread = GS2 - DFF:
    < -0.25%: market pricing 2-4 cuts over 2 years
    -0.25% to 0%: 0-2 cuts expected
    ≈ 0%: flat / hold
    > 0%: rate hike possible
"""
import httpx
from backend.data.cache import data_cache
from backend.config import settings

TTL = 2 * 3600   # 2-hour cache (shorter — market rates update frequently)


async def fetch_fedwatch_probabilities() -> dict:
    cache_key = "cme_fedwatch"
    cached = data_cache.get(cache_key, TTL)
    if cached:
        return cached

    result = await _derive_from_yield_curve()
    data_cache.set(cache_key, result)
    return result


async def _derive_from_yield_curve() -> dict:
    """
    Derive market-implied rate expectations from FRED yield curve.
    Returns structured data similar to what CME FedWatch provides.
    """
    params_base = {
        "api_key": settings.FRED_API_KEY,
        "file_type": "json",
        "limit": 1,
        "sort_order": "desc",
    }
    series_needed = ["DFF", "GS2", "GS10", "T10Y2Y", "SOFR", "T5YIE"]

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            values: dict[str, float] = {}
            for s in series_needed:
                r = await client.get(
                    "https://api.stlouisfed.org/fred/series/observations",
                    params={**params_base, "series_id": s},
                )
                if r.status_code == 200:
                    obs = [o for o in r.json().get("observations", []) if o["value"] != "."]
                    if obs:
                        values[s] = float(obs[0]["value"])

        if "DFF" not in values or "GS2" not in values:
            return {"status": "unavailable", "raw_lines": []}

        dff = values["DFF"]
        gs2 = values["GS2"]
        gs10 = values.get("GS10", dff)
        sofr = values.get("SOFR", dff)
        spread_2y = gs2 - dff       # Positive = market expects rate to RISE
        spread_10y = gs10 - dff
        breakeven = values.get("T5YIE", 2.3)

        # Estimate implied rate path in bps from current DFF
        # 2Y spread × 2 gives rough cumulative cut/hike over 2 years
        implied_12m_bps = round(spread_2y * 100 * 0.7, 0)   # 0.7× = 12m ≈ 70% of 2Y path
        implied_24m_bps = round(spread_2y * 100, 0)

        # Classify market stance
        if spread_2y < -0.25:
            stance = "dovish"
            cuts = int(abs(implied_12m_bps) // 25)
            desc = f"Yield curve implies {cuts}+ cuts over next year (GS2 {gs2:.2f}% vs DFF {dff:.2f}%)"
        elif spread_2y < 0:
            stance = "mildly dovish"
            desc = f"Yield curve implies 1-2 cuts (GS2 {gs2:.2f}% slightly below DFF {dff:.2f}%)"
        elif spread_2y < 0.15:
            stance = "neutral"
            desc = f"Yield curve implies hold/flat (GS2 {gs2:.2f}% ≈ DFF {dff:.2f}%)"
        else:
            stance = "hawkish"
            desc = f"Yield curve implies potential hike (GS2 {gs2:.2f}% > DFF {dff:.2f}%)"

        raw_lines = [
            f"DFF (current rate): {dff:.2f}%",
            f"2Y Treasury: {gs2:.2f}% → 2Y-DFF spread: {spread_2y:+.2f}%",
            f"10Y Treasury: {gs10:.2f}% → 10Y-DFF spread: {spread_10y:+.2f}%",
            f"SOFR: {sofr:.2f}% (overnight rate)",
            f"5Y Breakeven inflation: {breakeven:.2f}%",
            f"Market stance: {stance.upper()}",
            f"Implied 12m rate change: {implied_12m_bps:+.0f} bps",
            f"Implied 24m rate change: {implied_24m_bps:+.0f} bps",
            desc,
        ]

        return {
            "status": "yield_curve_derived",
            "raw_lines": raw_lines,
            "dff": dff,
            "gs2": gs2,
            "gs10": gs10,
            "spread_2y": spread_2y,
            "implied_12m_bps": implied_12m_bps,
            "implied_24m_bps": implied_24m_bps,
            "market_stance": stance,
        }

    except Exception as e:
        return {"status": "error", "raw_lines": [], "error": str(e)[:100]}
