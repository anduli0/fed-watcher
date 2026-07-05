"""
krw-watcher — 원/달러 환율 와쳐 웹 서비스 (PC 버전의 웹 포팅).

서버에서 24시간 스스로 동작: 환율/보조지표/뉴스 수집, 23-에이전트 계층형
위원회의 호라이즌 예측(1w/1m/3m/12m)과 도출 리포트(KO/EN), 데일리 브리프
(옵션: 텔레그램 전송)를 소유자의 클로드 구독(`claude -p`)으로 생성한다.
무료 호스트 유휴 슬립은 자가 핑으로 방지. 휴대폰은 브라우저로 읽기만 한다.
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

from . import agents, analyst, collector, news
from .claude_cli import auth_mode, last_auth_status

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("krw_watcher")

KST = ZoneInfo("Asia/Seoul")
STARTED_AT = datetime.now(timezone.utc)
MODEL_ID = os.getenv("MODEL_ID", "claude (owner subscription)")

COLLECT_EVERY_MIN = int(os.getenv("COLLECT_EVERY_MIN", "10"))
CYCLE_HOURS_KST = os.getenv("CYCLE_HOURS_KST", "8,13,20")     # 위원회 사이클(분=20)
BRIEF_HOURS_KST = os.getenv("BRIEF_HOURS_KST", "7")            # 데일리 브리프(분=30)
RUN_ON_STARTUP = os.getenv("RUN_ON_STARTUP", "true").lower() in ("1", "true", "yes", "on")
STARTUP_DELAY_SEC = float(os.getenv("STARTUP_DELAY_SEC", "10"))
STARTUP_MAX_AGE_H = float(os.getenv("STARTUP_MAX_AGE_H", "8"))

_scheduler: AsyncIOScheduler | None = None


async def _keepalive_pinger() -> None:
    """무료 티어 슬립 방지: 15분 유휴 전에 자기 자신을 핑해 인바운드를 만든다."""
    url = os.getenv("KEEPALIVE_URL") or os.getenv("RENDER_EXTERNAL_URL", "")
    interval = int(os.getenv("KEEPALIVE_INTERVAL_SEC", "600"))
    if not url or interval <= 0:
        logger.info("keep-alive pinger disabled")
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


def _hours_since_last_forecast() -> float | None:
    fc = agents.latest_forecast()
    if not fc:
        return None
    try:
        ts = datetime.fromisoformat(fc["created_at"])
        return (datetime.now(timezone.utc) - ts).total_seconds() / 3600
    except Exception:
        return None


async def _startup_warmup() -> None:
    await asyncio.sleep(STARTUP_DELAY_SEC)
    await collector.collect_latest()
    await collector.collect_context()
    await news.refresh()
    for rng in ("1w", "1mo", "1y"):
        await collector.get_chart(rng)
    age = _hours_since_last_forecast()
    if RUN_ON_STARTUP and (age is None or age > STARTUP_MAX_AGE_H):
        collector.emit("system", "부팅 워밍업: 위원회 사이클 시작", "info")
        await agents.run_cycle(trigger="startup", force=True)
        if analyst.hours_since_last() is None or analyst.hours_since_last() > 20:
            await analyst.run_analysis(trigger="startup", force=True)
    else:
        collector.emit("system",
                       f"부팅 완료 (최근 예측 {age:.1f}시간 전 — 재사용)" if age is not None
                       else "부팅 완료", "info")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler
    agents.load()
    analyst.load()
    _scheduler = AsyncIOScheduler(timezone=str(KST))
    _scheduler.add_job(collector.collect_latest,
                       IntervalTrigger(minutes=COLLECT_EVERY_MIN),
                       id="collect", max_instances=1, coalesce=True)
    _scheduler.add_job(collector.collect_context,
                       IntervalTrigger(minutes=max(30, COLLECT_EVERY_MIN * 3)),
                       id="context", max_instances=1, coalesce=True)
    _scheduler.add_job(news.refresh, IntervalTrigger(minutes=60),
                       id="news", max_instances=1, coalesce=True)
    _scheduler.add_job(lambda: asyncio.ensure_future(agents.run_cycle("scheduled")),
                       CronTrigger(hour=CYCLE_HOURS_KST, minute=20, timezone=str(KST)),
                       id="cycle", max_instances=1, coalesce=True)
    _scheduler.add_job(lambda: asyncio.ensure_future(analyst.run_analysis("scheduled")),
                       CronTrigger(hour=BRIEF_HOURS_KST, minute=30, timezone=str(KST)),
                       id="brief", max_instances=1, coalesce=True)
    _scheduler.start()
    asyncio.create_task(_startup_warmup())
    asyncio.create_task(_keepalive_pinger())
    collector.emit("system",
                   f"krw-watcher 시작 — 사이클 KST {CYCLE_HOURS_KST}시20분, "
                   f"브리프 {BRIEF_HOURS_KST}시30분, 에이전트 {len(agents.ROSTER)}", "info")
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
    fc = agents.latest_forecast()
    return {
        "status": "ok",
        "app": "krw-watcher",
        "model": MODEL_ID,
        "broker": "paper",
        "live_trading": False,
        "spot": collector.latest.get("rate"),
        "realized_vol_krw": agents.realized_vol_krw(),
        "data_last_collected": collector.latest.get("collected_at"),
        "agent_count": len(agents.ROSTER),
        "started_at": STARTED_AT.isoformat(),
        "last_forecast_kst": (fc or {}).get("created_kst"),
        "cycle_running": agents.is_running(),
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


@app.get("/api/forecast")
async def api_forecast():
    fc = agents.latest_forecast()
    if not fc:
        return JSONResponse({"status": "no_forecast",
                             "message": "아직 생성된 예측이 없습니다. 첫 사이클이 곧 완료됩니다."})
    return fc


@app.get("/api/forecasts")
async def api_forecasts(limit: int = 10):
    return [
        {k: f.get(k) for k in ("created_kst", "spot", "horizons", "headline",
                               "agents_ok", "trigger")}
        for f in agents.forecasts[:max(1, min(limit, 100))]
    ]


@app.get("/api/agents/status")
async def api_agents_status():
    return {
        "running": agents.is_running(),
        "agents": [
            {"name": name, "tier": tier,
             **{k: v for k, v in agents.agent_states.get(name, {}).items() if k != "tier"}}
            for name, tier, _ in agents.ROSTER
        ],
    }


@app.get("/api/news")
async def api_news():
    return await news.api_payload()


@app.get("/api/analysis")
async def api_analysis():
    rec = analyst.latest_analysis()
    if not rec:
        return JSONResponse({"status": "no_analysis",
                             "message": "아직 생성된 브리프가 없습니다."})
    return rec


@app.get("/api/brief")
async def api_brief():
    return await api_analysis()


@app.get("/api/accuracy")
async def api_accuracy():
    await collector.get_chart("1y")
    return agents.accuracy_report()


@app.get("/api/trading")
async def api_trading():
    return agents.paper_book(collector.latest.get("rate"))


@app.get("/api/activity")
async def api_activity(limit: int = 50):
    return list(collector.activity)[:max(1, min(limit, 300))]


@app.post("/api/trigger-cycle")
async def api_trigger_cycle():
    if agents.is_running():
        return {"status": "already_running"}
    asyncio.create_task(agents.run_cycle(trigger="manual"))
    return {"status": "started", "agents": len(agents.ROSTER)}


@app.post("/api/trigger-analysis")
async def api_trigger_analysis():
    if analyst.is_running():
        return {"status": "already_running"}
    asyncio.create_task(analyst.run_analysis(trigger="manual"))
    return {"status": "started"}


@app.post("/api/trigger-brief")
async def api_trigger_brief():
    return await api_trigger_analysis()


_STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
if os.path.isdir(_STATIC_DIR):
    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
