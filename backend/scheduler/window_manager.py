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

TZ = "Asia/Seoul"

scheduler = AsyncIOScheduler(timezone=TZ)


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

    # NOTE: graceful_shutdown cron removed — cloud deployment runs 24/7

    scheduler.start()
    logger.info(
        "Scheduler started. Data collect every %d min · Cycles: %s · Publish 08:00 KST",
        DATA_COLLECT_MIN, INTER_CYCLE_HOURS,
    )
