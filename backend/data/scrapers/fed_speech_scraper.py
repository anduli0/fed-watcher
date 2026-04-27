"""
Fed speeches scraper.
Primary: RSS feed (reliable, always works) → parse XML
Fallback: HTML page if RSS fails
"""
import httpx
from bs4 import BeautifulSoup
from dataclasses import dataclass
from backend.data.cache import data_cache

TTL = 6 * 3600
BASE = "https://www.federalreserve.gov"

# RSS feed for Fed speeches — more stable than HTML pages
RSS_URL = "https://www.federalreserve.gov/feeds/speeches.xml"
# HTML fallback candidates
HTML_CANDIDATES = [
    "/newsevents/speeches.htm",
    "/newsevents/speech/speeches.htm",
    "/newsevents/speech.htm",
]


@dataclass
class Speech:
    title: str
    speaker: str
    date: str
    url: str
    text: str = ""


async def fetch_speeches(limit: int = 10) -> list[Speech]:
    cache_key = "fed_speeches"
    cached = data_cache.get(cache_key, TTL)
    if cached:
        return [Speech(**s) for s in cached]

    speeches = await _fetch_via_rss(limit)
    if not speeches:
        speeches = await _fetch_via_html(limit)

    data_cache.set(cache_key, [s.__dict__ for s in speeches])
    return speeches


async def _fetch_via_rss(limit: int) -> list[Speech]:
    """Parse the Fed's RSS speech feed using stdlib xml.etree (no lxml required)."""
    import xml.etree.ElementTree as ET
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            r = await client.get(RSS_URL)
            if r.status_code != 200:
                return []

        # Strip BOM if present
        text = r.content.decode("utf-8-sig", errors="replace")
        root = ET.fromstring(text)
        ns = {"dc": "http://purl.org/dc/elements/1.1/"}

        speeches = []
        for item in root.iter("item"):
            title_el = item.find("title")
            link_el  = item.find("link")
            desc_el  = item.find("description")
            date_el  = item.find("pubDate")
            creator  = item.find("dc:creator", ns)

            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            link  = link_el.text.strip()  if link_el  is not None and link_el.text  else ""
            if not title or not link:
                continue

            # Extract speaker from dc:creator or description text
            speaker = ""
            if creator is not None and creator.text:
                speaker = creator.text.strip()[:80]
            elif desc_el is not None and desc_el.text:
                desc_text = BeautifulSoup(desc_el.text, "html.parser").get_text(strip=True)
                if "by " in desc_text.lower():
                    speaker = desc_text.split("by ", 1)[1].split(",")[0].split(".")[0][:80]

            # Description as speech text excerpt
            text_excerpt = ""
            if desc_el is not None and desc_el.text:
                text_excerpt = BeautifulSoup(desc_el.text, "html.parser").get_text(
                    separator=" ", strip=True
                )[:3000]

            speeches.append(Speech(
                title=title[:250],
                speaker=speaker or "Federal Reserve Official",
                date=date_el.text.strip()[:30] if date_el is not None and date_el.text else "",
                url=link,
                text=text_excerpt,
            ))
            if len(speeches) >= limit:
                break

        return speeches
    except Exception:
        return []


async def _fetch_via_html(limit: int) -> list[Speech]:
    """HTML fallback — try multiple candidate paths."""
    speeches: list[Speech] = []
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            html = ""
            for path in HTML_CANDIDATES:
                r = await client.get(f"{BASE}{path}")
                if r.status_code == 200:
                    html = r.text
                    break
            if not html:
                return []

            soup = BeautifulSoup(html, "html.parser")
            for row in soup.select(".itemlist li, .list-item, article")[:limit]:
                link = row.select_one("a")
                em = row.select_one("em, .speaker, .author")
                if not link:
                    continue
                href = link.get("href", "")
                url = href if href.startswith("http") else BASE + href
                speech = Speech(
                    title=link.get_text(strip=True)[:250],
                    speaker=em.get_text(strip=True) if em else "Unknown",
                    date=row.get_text(strip=True)[-12:].strip(),
                    url=url,
                )
                try:
                    speech.text = await _fetch_speech_text(client, url)
                except Exception:
                    pass
                speeches.append(speech)
    except Exception:
        pass
    return speeches


async def _fetch_speech_text(client: httpx.AsyncClient, url: str) -> str:
    r = await client.get(url, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    for sel in [".col-xs-12.col-sm-8.col-md-8", "article", ".content", "main"]:
        content = soup.select_one(sel)
        if content:
            return content.get_text(separator="\n", strip=True)[:8000]
    return ""
