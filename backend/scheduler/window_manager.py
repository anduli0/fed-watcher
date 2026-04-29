import asyncio
import logging
from datetime import time
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger("fed_watcher.scheduler")

# ── KST window constants ─────────────────────────────────────────────────────
FINAL_CYCLE_KST    = dict(hour=5,  minute=0)
PUBLISH_KST        = dict(hour=8,  minute=0)
SHUTDOWN_KST       = dict(hour=8, minute=30)
INTER_CYCLE_HOURS  = "12,16,20,0"
DATA_COLLECT_MIN   = 30  # Collect every 30 min — no AI tokens
BRIEFING_KST       = dict(hour=7, minute=30)  # 07:30 KST daily (22:30 UTC prev day)

TZ = "Asia/Seoul"

scheduler = AsyncIOScheduler(timezone=TZ)


async def _run_daily_briefing():
    """Daily briefing generation — runs at 07:30 KST. Uses KST date for briefing_date."""
    from backend.briefing.pipeline import run_briefing_pipeline
    from datetime import datetime
    from zoneinfo import ZoneInfo
    # Use KST date so briefing is labelled with the correct calendar date
    today_kst = datetime.now(ZoneInfo("Asia/Seoul")).date()
    logger.info("Daily briefing pipeline triggered for %s (KST)", today_kst)
    try:
        result = await run_briefing_pipeline(target_date=today_kst, force=False)
        logger.info("Daily briefing pipeline result: %s", result.get("status"))
    except Exception as exc:
        logger.error("Daily briefing pipeline error: %s", exc, exc_info=True)


def init_scheduler(
    run_cycle_fn,
    publish_fn,
    shutdown_fn,
    collect_data_fn,
):
    """Register all jobs. Call once at app startup."""

    # ── Continuous data collection (no AI tokens) ──
    scheduler.add_job(
        collect_data_fn,
        IntervalTrigger(minutes=DATA_COLLECT_MIN, timezone=TZ),
        id="data_collect",
        replace_existing=True,
        next_run_time=None,  # first run triggered manually at startup
    )

    # AI Orchestrator cycles
    scheduler.add_job(
        run_cycle_fn,
        CronTrigger(hour=INTER_CYCLE_HOURS, minute=30, timezone=TZ),
        id="inter_cycle",
        args=["scheduled"],
        replace_existing=True,
    )

    scheduler.add_job(
        run_cycle_fn,
        CronTrigger(**FINAL_CYCLE_KST, timezone=TZ),
        id="final_cycle",
        args=["final"],
        replace_existing=True,
    )

    scheduler.add_job(
        publish_fn,
        CronTrigger(**PUBLISH_KST, timezone=TZ),
        id="publish_forecast",
        replace_existing=True,
    )

    # ── Daily Macro News Briefing — 07:30 KST (22:30 UTC prev day) ─────────
    scheduler.add_job(
        _run_daily_briefing,
        CronTrigger(**BRIEFING_KST, timezone=TZ),
        id="daily_briefing",
        replace_existing=True,
    )

    # NOTE: graceful_shutdown cron removed — cloud deployment runs 24/7

    scheduler.start()
    logger.info(
        "Scheduler started. Data collect every %d min · Cycles: %s · "
        "Publish 08:00 KST · Daily Briefing 07:30 KST",
        DATA_COLLECT_MIN, INTER_CYCLE_HOURS,
    )
