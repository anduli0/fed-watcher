"""
API routes for the Daily Macro News Briefing feature.
All routes under /api/briefings.
"""
from __future__ import annotations
import json
import asyncio
import logging
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_

from backend.database.init_db import get_db
from backend.database.models import DailyBriefing, PipelineRun
from backend.config import settings

logger = logging.getLogger("fed_watcher.briefing.routes")

router = APIRouter(prefix="/api/briefings")

CRON_SECRET = getattr(settings, "CRON_SECRET", "")


def _serialize_briefing(b: DailyBriefing, full: bool = True) -> dict:
    """Serialize a DailyBriefing model to API response dict."""
    base = {
        "id": b.id,
        "briefing_date": b.briefing_date,
        "language": b.language,
        "timezone": b.timezone,
        "title": b.title,
        "market_impact_headline": b.market_impact_headline,
        "source_count": b.source_count,
        "article_count": b.article_count,
        "model_used": b.model_used,
        "status": b.status,
        "generation_finished_at": b.generation_finished_at.isoformat() if b.generation_finished_at else None,
        "created_at": b.created_at.isoformat() if b.created_at else None,
    }

    if full:
        # Parse stored JSON blobs
        exec_summary = []
        if b.executive_summary_json:
            try:
                exec_summary = json.loads(b.executive_summary_json)
            except Exception:
                pass

        body_data = {}
        if b.body_json:
            try:
                body_data = json.loads(b.body_json)
            except Exception:
                pass

        sources = []
        if b.sources_json:
            try:
                sources = json.loads(b.sources_json)
            except Exception:
                pass

        base.update({
            "executive_summary": exec_summary,
            "sections": body_data.get("sections", []),
            "what_changed_since_yesterday": body_data.get("whatChangedSinceYesterday", []),
            "fed_watcher_rate_path_signal": body_data.get("fedWatcherRatePathSignal", ""),
            "watch_next": body_data.get("watchNext", []),
            "disclaimer": body_data.get("disclaimer", ""),
            "sources": sources,
        })

    return base


@router.get("/latest")
async def get_latest_briefing(
    lang: str = Query("en", pattern="^(en|ko)$"),
    db: AsyncSession = Depends(get_db),
):
    """Return the latest published briefing for the given language."""
    stmt = (
        select(DailyBriefing)
        .where(and_(DailyBriefing.language == lang, DailyBriefing.status == "published"))
        .order_by(desc(DailyBriefing.briefing_date), desc(DailyBriefing.id))
        .limit(1)
    )
    result = (await db.execute(stmt)).scalar_one_or_none()

    if not result:
        # Try fallback to other language
        other_lang = "ko" if lang == "en" else "en"
        stmt2 = (
            select(DailyBriefing)
            .where(and_(DailyBriefing.language == other_lang, DailyBriefing.status == "published"))
            .order_by(desc(DailyBriefing.briefing_date), desc(DailyBriefing.id))
            .limit(1)
        )
        fallback = (await db.execute(stmt2)).scalar_one_or_none()
        if fallback:
            data = _serialize_briefing(fallback)
            data["fallback"] = True
            data["requested_lang"] = lang
            return data
        return None

    return _serialize_briefing(result)


@router.get("")
async def list_briefings(
    lang: str = Query("en", pattern="^(en|ko)$"),
    limit: int = Query(10, ge=1, le=60),
    db: AsyncSession = Depends(get_db),
):
    """Return list of published briefings for the archive view (light payload)."""
    stmt = (
        select(DailyBriefing)
        .where(and_(DailyBriefing.language == lang, DailyBriefing.status == "published"))
        .order_by(desc(DailyBriefing.briefing_date))
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_serialize_briefing(b, full=False) for b in rows]


@router.get("/{briefing_date}")
async def get_briefing_by_date(
    briefing_date: str,
    lang: str = Query("en", pattern="^(en|ko)$"),
    db: AsyncSession = Depends(get_db),
):
    """Return briefing for a specific date and language."""
    stmt = select(DailyBriefing).where(
        and_(
            DailyBriefing.briefing_date == briefing_date,
            DailyBriefing.language == lang,
            DailyBriefing.status == "published",
        )
    )
    result = (await db.execute(stmt)).scalar_one_or_none()
    if not result:
        raise HTTPException(status_code=404, detail=f"No briefing for {briefing_date}/{lang}")
    return _serialize_briefing(result)


@router.post("/generate")
async def trigger_briefing_generation(
    target_date: str | None = None,
    force: bool = False,
    x_cron_secret: str | None = None,
):
    """
    Manual trigger for briefing generation.
    Protected by CRON_SECRET header or admin usage.
    """
    if CRON_SECRET and x_cron_secret != CRON_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    from backend.briefing.pipeline import run_briefing_pipeline, _running_keys
    from zoneinfo import ZoneInfo

    td = None
    if target_date:
        try:
            td = date.fromisoformat(target_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    # Default to KST date
    if td is None:
        td = datetime.now(ZoneInfo("Asia/Seoul")).date()

    date_key = td.isoformat()
    if date_key in _running_keys:
        return {"status": "already_running", "date": date_key}

    asyncio.create_task(run_briefing_pipeline(td, force=force))
    return {"status": "triggered", "date": date_key}


@router.get("/admin/pipeline-runs")
async def get_pipeline_runs(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Return recent pipeline run logs for admin visibility."""
    stmt = (
        select(PipelineRun)
        .order_by(desc(PipelineRun.started_at))
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": r.id,
            "run_type": r.run_type,
            "status": r.status,
            "briefing_date": r.briefing_date,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "error_message": r.error_message,
        }
        for r in rows
    ]
