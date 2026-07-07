"""
SEP Dot-Plot scraper.

Pulls the ACTUAL latest Summary of Economic Projections (SEP) federal-funds-rate
median path from federalreserve.gov and the prior meeting's median, so the
committee reasons on real dot-plot numbers instead of an abstract framework.

Authoritative source: the "Federal funds rate" MEDIAN row of SEP Table 1
(fomcprojtabl<YYYYMMDD>.htm). We deliberately parse only the clearly-labelled
median row + the immediately-following prior-projection row — never inferred or
fabricated numbers. If anything is ambiguous we return None and the cycle falls
back to the news-only forward signal.
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass

import httpx

from backend.data.cache import data_cache

logger = logging.getLogger("fed_watcher.dotplot")

_UA = "Mozilla/5.0 (compatible; fed-watcher/1.0; +https://fed-watcher-backend-9rgk.onrender.com)"
_CAL_URLS = (
    "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
    "https://www.federalreserve.gov/monetarypolicy.htm",
)
_PROJ_RE = re.compile(r"fomcprojtabl(\d{8})\.htm", re.I)
_CACHE_KEY = "sep_dot_plot"
_CACHE_TTL = 60 * 60 * 12  # 12h — the SEP only changes quarterly


@dataclass
class DotPlot:
    as_of: str            # projtabl date YYYY-MM-DD
    url: str
    years: list[str]      # e.g. ["2026", "2027", "2028", "longer run"]
    median: list[float]   # fed funds rate median per year
    prior_label: str      # e.g. "March projection"
    prior_median: list[float]
    summary_text: str


def _cells(row_html: str) -> list[str]:
    import html as _html
    cs = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.S | re.I)
    return [re.sub(r"<[^>]+>", " ", _html.unescape(c)).strip() for c in cs]


def _first_nums(cells: list[str], n: int = 4) -> list[float]:
    out: list[float] = []
    for c in cells:
        m = re.fullmatch(r"-?\d\.\d", c.strip())
        if m:
            out.append(float(c))
            if len(out) == n:
                break
    return out


async def _discover_latest_url() -> tuple[str, str] | None:
    """Return (url, YYYYMMDD) of the most recent projection table."""
    async with httpx.AsyncClient(timeout=25, follow_redirects=True, headers={"User-Agent": _UA}) as client:
        found: set[str] = set()
        for u in _CAL_URLS:
            try:
                r = await client.get(u)
                found.update(m.group(0) for m in _PROJ_RE.finditer(r.text))
            except Exception as e:
                logger.warning("dot-plot: calendar fetch failed %s: %s", u, e)
        if not found:
            return None
        latest = sorted(found, key=lambda f: _PROJ_RE.search(f).group(1))[-1]
        date8 = _PROJ_RE.search(latest).group(1)
        return f"https://www.federalreserve.gov/monetarypolicy/{latest}", date8


async def fetch_dot_plot() -> DotPlot | None:
    cached = data_cache.get(_CACHE_KEY, _CACHE_TTL)
    if cached is not None:
        try:
            return DotPlot(**cached)
        except Exception:
            pass
    try:
        disc = await _discover_latest_url()
        if not disc:
            logger.warning("dot-plot: no projection table URL found")
            return None
        url, date8 = disc
        async with httpx.AsyncClient(timeout=25, follow_redirects=True, headers={"User-Agent": _UA}) as client:
            r = await client.get(url)
            r.raise_for_status()
            page = r.text

        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S | re.I)
        median: list[float] = []
        prior_label = ""
        prior_median: list[float] = []
        for i, row in enumerate(rows):
            cells = _cells(row)
            label = (cells[0] if cells else "").lower()
            if label.startswith("federal funds rate"):
                median = _first_nums(cells)
                # The immediately-following row is the prior meeting's projection.
                for j in range(i + 1, min(i + 3, len(rows))):
                    pc = _cells(rows[j])
                    plabel = (pc[0] if pc else "").strip()
                    if "projection" in plabel.lower():
                        prior_label = plabel
                        prior_median = _first_nums(pc)
                        break
                break

        if len(median) < 4:
            logger.warning("dot-plot: fed funds median row not parsed (got %s)", median)
            return None

        base_year = int(date8[:4])
        years = [str(base_year), str(base_year + 1), str(base_year + 2), "longer run"]

        # Build the injected summary. State the levels, the path direction, and
        # the revision vs the prior meeting (up = hawkish, down = dovish).
        parts = [
            f"SEP DOT PLOT (as of {date8[:4]}-{date8[4:6]}-{date8[6:8]}), federal-funds-rate MEDIAN by year-end:",
            "  " + " · ".join(f"{y} {m:.2f}%" for y, m in zip(years, median)),
        ]
        if len(prior_median) >= 4:
            rev = median[0] - prior_median[0]
            direction = "HAWKISH upward revision" if rev > 0.02 else ("DOVISH downward revision" if rev < -0.02 else "little changed")
            parts.append(
                f"  Prior ({prior_label}): " + " · ".join(f"{m:.2f}%" for m in prior_median)
                + f"  →  {direction} ({rev:+.2f}pp on the near-year median)."
            )
        parts.append(
            "  Compare the near-year median to the CURRENT effective funds rate: median ABOVE current ⇒ hikes still projected; "
            "BELOW ⇒ cuts projected. Weigh the level AND the revision direction."
        )
        summary_text = "\n".join(parts)

        dp = DotPlot(
            as_of=f"{date8[:4]}-{date8[4:6]}-{date8[6:8]}",
            url=url, years=years, median=median,
            prior_label=prior_label, prior_median=prior_median,
            summary_text=summary_text,
        )
        data_cache.set(_CACHE_KEY, dp.__dict__)
        logger.info("dot-plot: parsed %s median=%s prior=%s", dp.as_of, median, prior_median)
        return dp
    except Exception as e:
        logger.warning("dot-plot fetch/parse failed: %s", e)
        return None
