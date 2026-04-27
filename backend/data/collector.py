"""
Continuous web data collector — runs every 30 minutes WITHOUT Claude API tokens.
Emits real events to activity_log for frontend display.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database.init_db import AsyncSessionLocal
from backend.database.models import DataCollectionSnapshot
from backend.data.fred_client import get_macro_snapshot
from backend.data.scrapers.fed_speech_scraper import fetch_speeches
from backend.data.scrapers.fomc_minutes_scraper import fetch_fomc_minutes
from backend.data.scrapers.beige_book_scraper import fetch_beige_book
from backend.data.scrapers.regional_fed_scraper import fetch_all_regional_stances, stances_to_text
from backend.data.scrapers.cme_fedwatch_scraper import fetch_fedwatch_probabilities
from backend.data import activity_log as AL

logger = logging.getLogger("fed_watcher.collector")

_LATEST: dict = {
    "macro_snapshot": None, "macro_text": "",
    "speeches": [], "speeches_text": "",
    "minutes": [], "beige_book": "",
    "regional": [], "regional_text": "",
    "cme": {}, "collected_at": None,
}


def get_latest_snapshot() -> dict:
    return _LATEST


async def collect_web_data() -> dict:
    AL.system_event("Data sweep started (no AI tokens)")
    logger.info("[Collector] Starting web data sweep…")
    started = datetime.now(timezone.utc)

    # Emit per-source collection events
    AL.collecting("FRED API", "api.stlouisfed.org")
    AL.collecting("Fed Speeches", "federalreserve.gov/newsevents")
    AL.collecting("FOMC Minutes", "federalreserve.gov/monetarypolicy")
    AL.collecting("Beige Book", "federalreserve.gov/monetarypolicy")
    AL.collecting("Regional Feds", "12 district bank websites")
    AL.collecting("CME FedWatch", "cmegroup.com")

    results = await asyncio.gather(
        get_macro_snapshot(),
        fetch_speeches(limit=8),
        fetch_fomc_minutes(limit=3),
        fetch_beige_book(),
        fetch_all_regional_stances(),
        fetch_fedwatch_probabilities(),
        return_exceptions=True,
    )
    macro, speeches, minutes, beige, regional, cme = [
        (None if isinstance(r, Exception) else r) for r in results
    ]

    failures = []
    for label, r in zip(["FRED API", "Fed Speeches", "FOMC Minutes", "Beige Book", "Regional Feds", "CME FedWatch"], results):
        if isinstance(r, Exception):
            failures.append(f"{label}: {str(r)[:80]}")
            AL.collect_failed(label, str(r)[:60])

    speeches = speeches or []
    minutes = minutes or []
    regional = regional or []

    # Emit success events
    if macro:
        dff = macro.get("DFF")
        AL.collected("FRED API", 10, f"series — DFF={dff}%")
    if speeches:
        AL.collected("Fed Speeches", len(speeches), "speeches scraped")
    if minutes:
        AL.collected("FOMC Minutes", len(minutes), "meeting minutes")
    if beige:
        AL.collected("Beige Book", 1, "report")
    if regional:
        ok_count = sum(1 for r in regional if r.scrape_status == "ok")
        AL.collected("Regional Feds", ok_count, f"/{len(regional)} banks")
    if cme and cme.get("status") != "unavailable":
        AL.collected("CME FedWatch", len(cme.get("raw_lines", [])), "probability lines")

    _LATEST.update({
        "macro_snapshot": macro,
        "macro_text": macro.summary_text() if macro else "",
        "speeches": speeches,
        "speeches_text": "\n\n".join(f"[{s.speaker} — {s.date}]\n{s.text}" for s in speeches),
        "minutes": minutes,
        "beige_book": beige or "",
        "regional": regional,
        "regional_text": stances_to_text(regional),
        "cme": cme or {},
        "collected_at": started.isoformat(),
    })

    async with AsyncSessionLocal() as db:
        await _persist_snapshot(db)

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    AL.system_event(f"Data sweep complete in {elapsed:.1f}s · {len(speeches)} speeches, {len(minutes)} minutes, {len(regional)} regional")
    logger.info("[Collector] Sweep done in %.1fs. Failures: %s", elapsed,
                ", ".join(failures) if failures else "none")

    return {
        "collected_at": _LATEST["collected_at"],
        "duration_s": elapsed,
        "counts": {"speeches": len(speeches), "minutes": len(minutes), "regional": len(regional)},
        "failures": failures,
    }


async def _persist_snapshot(db: AsyncSession):
    snap = DataCollectionSnapshot(
        macro_json=_LATEST["macro_text"][:5000],
        speeches_json=json.dumps([{"speaker": s.speaker, "date": s.date, "title": s.title} for s in _LATEST["speeches"]]),
        minutes_json=json.dumps([m[:500] for m in _LATEST["minutes"]]),
        beige_book_text=_LATEST["beige_book"][:5000],
        regional_json=_LATEST["regional_text"][:5000],
        cme_json=json.dumps(_LATEST["cme"])[:2000],
        has_new_data=True,
    )
    db.add(snap)
    await db.commit()
