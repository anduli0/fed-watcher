"""
krw-watcher — 원/달러 환율 와쳐 웹 서비스.

Runs entirely server-side: collects USD/KRW on a schedule, generates Korean
AI briefings through the owner's Claude subscription (`claude -p`), keeps the
free-tier host awake with a self-ping, and serves the dashboard + JSON API.
The phone/browser only ever reads.
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import analyst, collector
from .claude_cli import auth_mode, last_auth_status

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("krw_watcher")

KST = ZoneInfo("Asia/Seoul")
STARTED_AT = datetime.now(timezone.utc)

COLLECT_EVERY_MIN = int(os.getenv("COLLECT_EVERY_MIN", "10"))
# KST hours for scheduled AI briefings (분 단위 고정: 30분)
ANALYSIS_HOURS_KST = os.getenv("ANALYSIS_HOURS_KST", "8,12,18,22")
RUN_ON_STARTUP = os.getenv("RUN_ON_STARTUP", "true").lower() in ("1", "true", "yes", "on")
STARTUP_DELAY_SEC = float(os.getenv("STARTUP_DELAY_SEC", "10"))
STARTUP_MAX_AGE_H = float(os.getenv("STARTUP_MAX_AGE_H", "6"))

_scheduler: AsyncIOScheduler | None = None


async def _keepalive_pinger() -> None:
    """Free-tier anti-sleep: Render idles the container after ~15 min without
    INBOUND traffic, which kills scheduled jobs. Ping our own public URL so the
    router sees a real inbound request. No-op without a public URL."""
    url = os.getenv("KEEPALIVE_URL") or os.getenv("RENDER_EXTERNAL_URL", "")
    interval = int(os.getenv("KEEPALIVE_INTERVAL_SEC", "600"))
    if not url or interval <= 0:
        logger.info("keep-alive pinger disabled (no public URL or interval<=0)")
        return
    ping_url = url.rstrip("/") + "/health"
    logger.info("keep-alive pinger active: %s every %ds", ping_url, interval)
    while True:
        await asyncio.sleep(interval)
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                await client.get(ping_url)
        except Exception as e:
            logger.warning("keep-alive ping failed: %s", e)


async def _startup_warmup() -> None:
    await asyncio.sleep(STARTUP_DELAY_SEC)
    await collector.collect_latest()
    await collector.collect_context()
    age = analyst.hours_since_last()
    if RUN_ON_STARTUP and (age is None or age > STARTUP_MAX_AGE_H):
        collector.emit("system", "부팅 워밍업: 최신 분석이 없어 새로 생성", "info")
        await analyst.run_analysis(trigger="startup", force=True)
    else:
        collector.emit("system",
                       f"부팅 완료 (최근 분석 {age:.1f}시간 전 — 재사용)" if age is not None
                       else "부팅 완료", "info")


async def _scheduled_analysis() -> None:
    await analyst.run_analysis(trigger="scheduled")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler
    analyst.load()
    _scheduler = AsyncIOScheduler(timezone=str(KST))
    _scheduler.add_job(collector.collect_latest,
                       IntervalTrigger(minutes=COLLECT_EVERY_MIN),
                       id="collect", max_instances=1, coalesce=True)
    _scheduler.add_job(collector.collect_context,
                       IntervalTrigger(minutes=max(30, COLLECT_EVERY_MIN * 3)),
                       id="context", max_instances=1, coalesce=True)
    _scheduler.add_job(_scheduled_analysis,
                       CronTrigger(hour=ANALYSIS_HOURS_KST, minute=30, timezone=str(KST)),
                       id="analysis", max_instances=1, coalesce=True)
    _scheduler.start()
    asyncio.create_task(_startup_warmup())
    asyncio.create_task(_keepalive_pinger())
    collector.emit("system", f"krw-watcher 시작 (분석 스케줄 KST {ANALYSIS_HOURS_KST}시 30분)", "info")
    yield
    try:
        _scheduler.shutdown(wait=False)
    except Exception:
        pass


app = FastAPI(title="krw-watcher", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["GET", "POST"], allow_headers=["*"])


@app.get("/health")
async def health():
    ok, detail = last_auth_status()
    return {
        "status": "ok",
        "app": "krw-watcher",
        "started_at": STARTED_AT.isoformat(),
        "rate": collector.latest.get("rate"),
        "data_collected_at": collector.latest.get("collected_at"),
        "analyses_stored": len(analyst.analyses),
        "last_analysis_kst": (analyst.latest_analysis() or {}).get("created_kst"),
        "analysis_running": analyst.is_running(),
        "claude_auth": {"ok": ok, "mode": auth_mode(), "detail": detail},
    }


@app.get("/api/latest")
async def api_latest():
    if not collector.latest:
        await collector.collect_latest()
    return {"latest": collector.latest or None, "context": collector.context}


@app.get("/api/chart")
async def api_chart(range: str = "1d"):
    return await collector.get_chart(range)


@app.get("/api/analysis")
async def api_analysis():
    rec = analyst.latest_analysis()
    if not rec:
        return JSONResponse({"status": "no_analysis",
                             "message": "아직 생성된 분석이 없습니다."}, status_code=200)
    return rec


@app.get("/api/analyses")
async def api_analyses(limit: int = 10):
    return analyst.analyses[:max(1, min(limit, 60))]


@app.get("/api/activity")
async def api_activity(limit: int = 50):
    return list(collector.activity)[:max(1, min(limit, 300))]


@app.post("/api/trigger-analysis")
async def api_trigger_analysis():
    if analyst.is_running():
        return {"status": "already_running"}
    asyncio.create_task(analyst.run_analysis(trigger="manual"))
    return {"status": "started"}


_STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
if os.path.isdir(_STATIC_DIR):
    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
