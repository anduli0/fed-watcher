import httpx
import pdfplumber
import io
from bs4 import BeautifulSoup
from backend.data.cache import data_cache

TTL = 24 * 3600
BASE = "https://www.federalreserve.gov"


async def fetch_beige_book() -> str:
    cache_key = "beige_book"
    cached = data_cache.get(cache_key, TTL)
    if cached is not None:
        return cached

    candidate_paths = [
        "/monetarypolicy/beige-book-default.htm",
        "/monetarypolicy/beigebook202504.htm",
        "/monetarypolicy/publications/beige-book-default.htm",
    ]

    text = ""
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
                data_cache.set(cache_key, "")
                return ""

            soup = BeautifulSoup(html, "html.parser")
            pdf_link = soup.select_one("a[href$='.pdf']")
            if not pdf_link:
                data_cache.set(cache_key, "")
                return ""

            href = pdf_link.get("href", "")
            url = href if href.startswith("http") else BASE + href
            pdf_r = await client.get(url, timeout=30)
            if pdf_r.status_code != 200:
                data_cache.set(cache_key, "")
                return ""

            with pdfplumber.open(io.BytesIO(pdf_r.content)) as pdf:
                text = "\n".join(page.extract_text() or "" for page in pdf.pages[:30])
    except Exception:
        text = ""

    result = text[:15000]
    data_cache.set(cache_key, result)
    return result
