import asyncio
import httpx
from bs4 import BeautifulSoup
from dataclasses import dataclass
from backend.data.cache import data_cache

TTL = 12 * 3600

# Per-bank CSS selectors for speech titles — reduces noise vs generic <a> scan
REGIONAL_FEDS: dict[str, dict] = {
    "Boston":       {"url": "https://www.bostonfed.org/news-and-events/speeches.aspx",
                     "selector": "h3 a, .news-item a, .speech-title a"},
    "New York":     {"url": "https://www.newyorkfed.org/newsevents/speeches",
                     "selector": ".ts-list-item a, h3 a, .speech a"},
    "Philadelphia": {"url": "https://www.philadelphiafed.org/our-people/speeches",
                     "selector": "h3 a, .speech-listing a"},
    "Cleveland":    {"url": "https://www.clevelandfed.org/collections/speeches",
                     "selector": ".views-row a, h3 a"},
    "Richmond":     {"url": "https://www.richmondfed.org/press_room/speeches",
                     "selector": ".views-field-title a, h3 a"},
    "Atlanta":      {"url": "https://www.atlantafed.org/news/speeches",
                     "selector": ".speeches-list a, h3 a, .news-item a"},
    "Chicago":      {"url": "https://www.chicagofed.org/publications/speeches",
                     "selector": ".border-bottom a, h3 a"},
    "St. Louis":    {"url": "https://www.stlouisfed.org/about-us/speeches-presentations",
                     "selector": ".speeches a, h3 a, .list-item a"},
    "Minneapolis":  {"url": "https://www.minneapolisfed.org/news-and-events/speeches",
                     "selector": ".news-list a, h3 a"},
    "Kansas City":  {"url": "https://www.kansascityfed.org/research/speeches-and-essays",
                     "selector": ".research-list a, h3 a, .article-title a"},
    "Dallas":       {"url": "https://www.dallasfed.org/news/speeches",
                     "selector": ".article-list a, h3 a"},
    "San Francisco":{"url": "https://www.frbsf.org/our-district/press/presidents-speeches",
                     "selector": ".views-field-title a, h3 a, .speech-list a"},
}

HAWK_WORDS = {"hike", "tighten", "restrictive", "inflation", "overshoot", "hawkish"}
DOVE_WORDS  = {"cut", "ease", "accommodative", "labor", "employment", "dovish", "pause"}


@dataclass
class RegionalStance:
    bank: str
    latest_speech_title: str = ""
    latest_speech_date: str = ""
    snippet: str = ""
    inferred_lean: str = "unknown"  # hawkish|dovish|neutral|unknown
    scrape_status: str = "ok"


async def fetch_all_regional_stances() -> list[RegionalStance]:
    cache_key = "regional_stances"
    cached = data_cache.get(cache_key, TTL)
    if cached:
        return [RegionalStance(**s) for s in cached]

    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        tasks = [
            _fetch_one(client, bank, cfg["url"], cfg["selector"])
            for bank, cfg in REGIONAL_FEDS.items()
        ]
        stances = list(await asyncio.gather(*tasks, return_exceptions=False))

    # replace any exceptions with failed stance
    clean = []
    for bank, r in zip(REGIONAL_FEDS.keys(), stances):
        if isinstance(r, Exception):
            clean.append(RegionalStance(bank=bank, scrape_status=f"error: {str(r)[:50]}"))
        else:
            clean.append(r)

    data_cache.set(cache_key, [s.__dict__ for s in clean])
    return clean


async def _fetch_one(
    client: httpx.AsyncClient, bank: str, url: str, selector: str
) -> RegionalStance:
    try:
        r = await client.get(url, timeout=10)
        if r.status_code != 200:
            return RegionalStance(bank=bank, scrape_status=f"http_{r.status_code}")

        soup = BeautifulSoup(r.text, "html.parser")

        # Try per-bank selectors first, fallback to heading-level links
        title = ""
        for sel in selector.split(", "):
            candidates = [
                a.get_text(strip=True) for a in soup.select(sel)
                if 20 < len(a.get_text(strip=True)) < 300
            ]
            if candidates:
                title = candidates[0]
                break

        if not title:
            return RegionalStance(bank=bank, scrape_status="no_content")

        lean = _infer_lean(title)
        return RegionalStance(
            bank=bank,
            latest_speech_title=title[:250],
            snippet=title[:400],
            inferred_lean=lean,
        )
    except Exception as e:
        return RegionalStance(bank=bank, scrape_status=f"failed: {str(e)[:50]}")


def _infer_lean(text: str) -> str:
    lower = text.lower()
    hawk_score = sum(1 for w in HAWK_WORDS if w in lower)
    dove_score = sum(1 for w in DOVE_WORDS if w in lower)
    if hawk_score > dove_score:
        return "hawkish"
    if dove_score > hawk_score:
        return "dovish"
    return "neutral"


def stances_to_text(stances: list[RegionalStance]) -> str:
    lines = []
    for s in stances:
        if s.scrape_status == "ok":
            lines.append(f"[{s.bank}] [{s.inferred_lean.upper()}] {s.latest_speech_title}")
        else:
            lines.append(f"[{s.bank}] Status: {s.scrape_status}")
    return "\n".join(lines)
