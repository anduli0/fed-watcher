import httpx
import pdfplumber
import io
from bs4 import BeautifulSoup
from backend.data.cache import data_cache

TTL = 24 * 3600
BASE = "https://www.federalreserve.gov"


async def fetch_fomc_minutes(limit: int = 3) -> list[str]:
    cache_key = "fomc_minutes"
    cached = data_cache.get(cache_key, TTL)
    if cached:
        return cached

    # FOMC pages have moved over time — try several known paths
    candidate_paths = [
        "/monetarypolicy/fomccalendars.htm",
        "/monetarypolicy/fomcminutes.htm",
        "/monetarypolicy/fomc_historical.htm",
    ]

    texts: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            html = ""
            for path in candidate_paths:
                try:
                    r = await client.get(f"{BASE}{path}")
                    if r.status_code == 200:
                        html = r.text
                        break
                except Exception:
                    continue

            if not html:
                data_cache.set(cache_key, [])
                return []

            soup = BeautifulSoup(html, "html.parser")
            links = [a.get("href", "") for a in soup.select("a[href$='.pdf']") if "minutes" in a.get("href", "").lower()][:limit]
            for href in links:
                url = href if href.startswith("http") else BASE + href
                try:
                    pdf_r = await client.get(url, timeout=30)
                    if pdf_r.status_code == 200:
                        text = _extract_pdf_text(pdf_r.content)
                        texts.append(text[:12000])
                except Exception:
                    pass
    except Exception:
        pass

    data_cache.set(cache_key, texts)
    return texts


def _extract_pdf_text(content: bytes) -> str:
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages[:20])
