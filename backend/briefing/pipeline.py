"""
Daily briefing pipeline orchestrator.
Runs fetch → dedupe → rank → select → generate (EN+KO) → store.
"""
from __future__ import annotations
import asyncio
import json
import logging
from datetime import datetime, date

from sqlalchemy.ext.asyncio import AsyncSession

from backend.briefing.fetcher import fetch_all_sources, ArticleData
from backend.briefing.ranker import deduplicate, score_and_rank, ensure_category_coverage, MIN_ARTICLES_FOR_BRIEFING
from backend.briefing.generator import generate_briefing
from backend.database.init_db import AsyncSessionLocal

logger = logging.getLogger("fed_watcher.briefing.pipeline")

# Locks to prevent concurrent runs for the same date+lang
_running_keys: set[str] = set()


async def run_briefing_pipeline(
    target_date: date | None = None,
    force: bool = False,
) -> dict:
    """
    Full pipeline: fetch → dedupe → rank → generate EN+KO → store.

    Args:
        target_date: date to generate briefing for (defaults to today UTC)
        force: if True, overwrite existing published briefing for this date

    Returns dict with status and briefing IDs.
    """
    from backend.database.models import DailyBriefing, NewsArticle, BriefingArticle, PipelineRun
    from sqlalchemy import select, and_

    td = target_date or date.today()
    date_str = td.isoformat()
    run_key = date_str

    # Idempotency guard
    if run_key in _running_keys:
        logger.info("Pipeline already running for %s — skipping", date_str)
        return {"status": "already_running", "date": date_str}
    _running_keys.add(run_key)

    async with AsyncSessionLocal() as db:
        # Create pipeline run log
        run = PipelineRun(
            run_type="daily_briefing",
            status="running",
            started_at=datetime.utcnow(),
            briefing_date=date_str,
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = run.id

    try:
        result = await _execute_pipeline(date_str, force, run_id)
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            stmt = select(PipelineRun).where(PipelineRun.id == run_id)
            r = (await db.execute(stmt)).scalar_one_or_none()
            if r:
                r.status = "completed"
                r.finished_at = datetime.utcnow()
                r.logs_json = json.dumps(result)
                await db.commit()
        return result
    except Exception as exc:
        logger.error("Pipeline failed for %s: %s", date_str, exc, exc_info=True)
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            stmt = select(PipelineRun).where(PipelineRun.id == run_id)
            r = (await db.execute(stmt)).scalar_one_or_none()
            if r:
                r.status = "failed"
                r.finished_at = datetime.utcnow()
                r.error_message = str(exc)[:1000]
                await db.commit()
        return {"status": "failed", "date": date_str, "error": str(exc)[:200]}
    finally:
        _running_keys.discard(run_key)


async def _execute_pipeline(date_str: str, force: bool, run_id: int) -> dict:
    from backend.database.models import DailyBriefing, NewsArticle, BriefingArticle
    from sqlalchemy import select, and_

    # ── Step 1: Fetch all RSS feeds ────────────────────────────────────────
    logger.info("[%s] Step 1: Fetching RSS feeds", date_str)
    raw_articles = await fetch_all_sources()

    if not raw_articles:
        raise RuntimeError("No articles fetched from any source")

    # ── Step 2: Deduplicate ────────────────────────────────────────────────
    logger.info("[%s] Step 2: Deduplicating %d articles", date_str, len(raw_articles))
    deduped = deduplicate(raw_articles)

    if len(deduped) < MIN_ARTICLES_FOR_BRIEFING:
        raise RuntimeError(
            f"Insufficient articles after dedup: {len(deduped)} (minimum {MIN_ARTICLES_FOR_BRIEFING})"
        )

    # ── Step 3: Score and rank ─────────────────────────────────────────────
    logger.info("[%s] Step 3: Scoring and ranking", date_str)
    scored = score_and_rank(deduped)
    selected = ensure_category_coverage(scored)

    logger.info("[%s] Selected %d articles for briefing", date_str, len(selected))

    # ── Step 4: Store articles in DB ───────────────────────────────────────
    article_db_ids: dict[str, int] = {}
    async with AsyncSessionLocal() as db:
        for art in selected:
            # Upsert by canonical_url
            stmt = select(NewsArticle).where(NewsArticle.canonical_url == art["canonical_url"])
            existing = (await db.execute(stmt)).scalar_one_or_none()
            if existing:
                article_db_ids[art["canonical_url"]] = existing.id
            else:
                na = NewsArticle(
                    source_id=art["source_id"],
                    source_name=art["source_name"],
                    title=art["title"],
                    url=art["url"],
                    canonical_url=art["canonical_url"],
                    author=art["author"],
                    published_at=art["published_at"],
                    snippet=art["snippet"],
                    topic_tags_json=json.dumps(art["topic_tags"]),
                )
                db.add(na)
                await db.flush()
                article_db_ids[art["canonical_url"]] = na.id
        await db.commit()

    # ── Step 5: Generate EN and KO briefings in parallel ──────────────────
    logger.info("[%s] Step 5: Generating EN + KO briefings", date_str)
    try:
        en_data, ko_data = await asyncio.gather(
            generate_briefing(selected, "en"),
            generate_briefing(selected, "ko"),
        )
    except Exception as exc:
        raise RuntimeError(f"LLM generation failed: {exc}")

    # ── Step 6: Store briefings ────────────────────────────────────────────
    source_ids = list({art["source_id"] for art in selected})
    source_names = list({art["source_name"] for art in selected})
    model_used = "claude-sonnet-4-6"

    briefing_db_ids: dict[str, int] = {}
    async with AsyncSessionLocal() as db:
        for lang, data in [("en", en_data), ("ko", ko_data)]:
            # Check for existing briefing
            stmt = select(DailyBriefing).where(
                and_(
                    DailyBriefing.briefing_date == date_str,
                    DailyBriefing.language == lang,
                )
            )
            existing = (await db.execute(stmt)).scalar_one_or_none()

            if existing and not force:
                logger.info("Briefing %s/%s already exists — skipping", date_str, lang)
                briefing_db_ids[lang] = existing.id
                continue

            brief = existing or DailyBriefing(
                briefing_date=date_str,
                language=lang,
                timezone="Asia/Seoul",
            )
            brief.title = data.get("title", "")
            brief.market_impact_headline = data.get("marketImpactHeadline", "")
            brief.executive_summary_json = json.dumps(data.get("executiveSummary", []), ensure_ascii=False)
            brief.body_json = json.dumps(data, ensure_ascii=False)
            brief.source_count = len(source_ids)
            brief.article_count = len(selected)
            brief.model_used = model_used
            brief.status = "published"
            brief.generation_started_at = datetime.utcnow()
            brief.generation_finished_at = datetime.utcnow()
            brief.sources_json = json.dumps([
                {"id": a["source_id"], "name": a["source_name"],
                 "title": a["title"], "url": a["url"],
                 "publisher": a["source_name"],
                 "published_at": a["published_at"].isoformat() if a["published_at"] else ""}
                for a in selected
            ], ensure_ascii=False)

            if not existing:
                db.add(brief)
            await db.flush()
            briefing_db_ids[lang] = brief.id

            # Store briefing-article links
            for art in selected:
                art_id = article_db_ids.get(art["canonical_url"])
                if art_id:
                    ba = BriefingArticle(
                        briefing_id=brief.id,
                        article_id=art_id,
                        role="primary",
                    )
                    db.add(ba)

        await db.commit()

    logger.info("[%s] Pipeline complete. EN=%s KO=%s",
                date_str, briefing_db_ids.get("en"), briefing_db_ids.get("ko"))
    return {
        "status": "completed",
        "date": date_str,
        "article_count": len(selected),
        "source_count": len(source_ids),
        "briefing_ids": briefing_db_ids,
    }
