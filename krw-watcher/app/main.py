"""
krw-watcher — 원본 PC 앱의 API 계약을 그대로 제공하는 웹 서비스.
프론트엔드는 원본 사이트 HTML을 그대로 서빙한다. 모든 AI는 소유자의 클로드
구독(`claude -p`)으로 서버에서 실행되며, PC와 완전히 독립적으로 동작한다.
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

from . import briefing, collector, engine, news, quant
from .claude_cli import auth_mode, last_auth_status

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("krw_watcher")

KST = ZoneInfo("Asia/Seoul")
MODEL_ID = os.getenv("MODEL_ID", "claude-sonnet-4-6")

COLLECT_EVERY_MIN = int(os.getenv("COLLECT_EVERY_MIN", "10"))
CYCLE_HOURS_KST = os.getenv("CYCLE_HOURS_KST", "8,13,20")
BRIEF_HOURS_KST = os.getenv("BRIEF_HOURS_KST", "7")
RUN_ON_STARTUP = os.getenv("RUN_ON_STARTUP", "true").lower() in ("1", "true", "yes", "on")
STARTUP_DELAY_SEC = float(os.getenv("STARTUP_DELAY_SEC", "10"))
STARTUP_MAX_AGE_H = float(os.getenv("STARTUP_MAX_AGE_H", "8"))

_scheduler: AsyncIOScheduler | None = None


async def _keepalive() -> None:
    url = os.getenv("KEEPALIVE_URL") or os.getenv("RENDER_EXTERNAL_URL", "")
    interval = int(os.getenv("KEEPALIVE_INTERVAL_SEC", "600"))
    if not url or interval <= 0:
        return
    ping = url.rstrip("/") + "/health"
    logger.info("keep-alive: %s every %ds", ping, interval)
    while True:
        await asyncio.sleep(interval)
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                await c.get(ping)
        except Exception as e:
            logger.warning("keep-alive failed: %s", e)


def _forecast_age_h() -> float | None:
    fc = engine.S.get("forecast")
    if not fc:
        return None
    try:
        ts = datetime.fromisoformat(fc["created_kst"])
        return (datetime.now(KST) - ts).total_seconds() / 3600
    except Exception:
        return None


async def _warmup() -> None:
    await asyncio.sleep(STARTUP_DELAY_SEC)
    await collector.collect_latest()
    await collector.collect_context()
    await news.refresh()
    await asyncio.to_thread(quant.daily_tick)
    age = _forecast_age_h()
    if RUN_ON_STARTUP and (age is None or age > STARTUP_MAX_AGE_H):
        collector.emit("system", "부팅 워밍업: 위원회 사이클 시작", "info")
        await engine.run_cycle("startup", force=True)
        if not briefing.get(datetime.now(KST).date().isoformat()):
            await briefing.generate("startup")
    else:
        collector.emit("system",
                       f"부팅 완료 (최근 예측 {age:.1f}시간 전 — 재사용)" if age is not None else "부팅 완료",
                       "info")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler
    engine.load()
    briefing.load()
    quant.load()
    _scheduler = AsyncIOScheduler(timezone=str(KST))
    _scheduler.add_job(collector.collect_latest, IntervalTrigger(minutes=COLLECT_EVERY_MIN),
                       id="collect", max_instances=1, coalesce=True)
    _scheduler.add_job(collector.collect_context, IntervalTrigger(minutes=30),
                       id="context", max_instances=1, coalesce=True)
    _scheduler.add_job(news.refresh, IntervalTrigger(minutes=60), id="news",
                       max_instances=1, coalesce=True)
    _scheduler.add_job(lambda: asyncio.ensure_future(asyncio.to_thread(quant.daily_tick)),
                       CronTrigger(hour="0,9,16", minute=10, timezone=str(KST)), id="daily")
    _scheduler.add_job(lambda: asyncio.ensure_future(engine.run_cycle("scheduled")),
                       CronTrigger(hour=CYCLE_HOURS_KST, minute=20, timezone=str(KST)),
                       id="cycle", max_instances=1, coalesce=True)
    _scheduler.add_job(lambda: asyncio.ensure_future(briefing.generate("scheduled")),
                       CronTrigger(hour=BRIEF_HOURS_KST, minute=30, timezone=str(KST)),
                       id="brief", max_instances=1, coalesce=True)
    _scheduler.start()
    asyncio.create_task(_warmup())
    asyncio.create_task(_keepalive())
    collector.emit("system",
                   f"KRW-Watcher 시작 — 사이클 KST {CYCLE_HOURS_KST}시20분 · 브리프 {BRIEF_HOURS_KST}시30분 "
                   f"· 에이전트 {len(engine.ROSTER)} · 2-round", "info")
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
    return {"status": "ok", "model": MODEL_ID, "broker": "paper", "live_trading": False,
            "spot": collector.latest.get("rate"),
            "realized_vol_krw": engine.realized_vol_krw(),
            "data_last_collected": collector.latest.get("collected_at"),
            "agent_count": len(engine.ROSTER),
            "cycle_running": engine.is_running(),
            "claude_auth": {"ok": ok, "mode": auth_mode(), "detail": detail}}


@app.get("/api/forecast")
async def api_forecast():
    fc = engine.S.get("forecast")
    if not fc:
        return {"horizons": {}, "report_ko": "첫 사이클 진행 중 — 곧 생성됩니다.", "report_en": "First cycle in progress."}
    return fc


@app.get("/api/signal")
async def api_signal():
    return {"signal": engine.S.get("signal"),
            "broker": engine.broker_state(collector.latest.get("rate"))}


@app.get("/api/agents")
async def api_agents():
    return {"run": engine.S.get("run"), "agents": engine.S.get("agents") or [],
            "confidence_eval": engine.S.get("eval")}


@app.get("/api/hierarchy")
async def api_hierarchy():
    h = engine.S.get("hierarchy")
    if not h:
        return {"hierarchy": None}
    return {"hierarchy": h, "updated_at": (engine.S.get("run") or {}).get("completed_at")}


@app.get("/api/accuracy")
async def api_accuracy():
    return await asyncio.to_thread(engine.accuracy_payload)


@app.get("/api/accuracy/track")
async def api_accuracy_track(horizon: str = "1m"):
    return await asyncio.to_thread(quant.track_payload, horizon, engine.S.get("forecasts") or [])


@app.get("/api/daily-ohlc")
async def api_daily_ohlc():
    return await asyncio.to_thread(quant.daily_payload)


@app.get("/api/news")
async def api_news():
    return await news.api_payload()


@app.get("/api/briefing/latest")
async def api_brief_latest(date: str | None = None):
    b = briefing.get(date)
    return {"brief": b}


@app.get("/api/briefing/list")
async def api_brief_list():
    return {"items": briefing.list_items()}


@app.post("/api/briefing/generate")
async def api_brief_generate():
    return await briefing.generate("manual")


@app.get("/api/activity")
async def api_activity(after: int = 0, limit: int = 200):
    return {"events": collector.events_after(after, min(limit, 300))}


@app.post("/api/cycle")
async def api_cycle():
    if engine.is_running():
        return {"status": "already_running"}
    asyncio.create_task(engine.run_cycle("manual", force=True))
    return {"status": "started", "agents": len(engine.ROSTER)}


@app.post("/api/backtest")
async def api_backtest(years: int = 12, lookback: int = 20, horizon: str = "1m"):
    return await asyncio.to_thread(quant.backtest, years, lookback, horizon)


@app.get("/api/notes")
async def api_notes():
    from . import notes as notes_mod
    return {"notes": notes_mod.load()}


@app.post("/api/notes")
async def api_notes_add(payload: dict):
    from . import notes as notes_mod
    title = str(payload.get("title", "")).strip()
    body = str(payload.get("body", "")).strip()
    if not title or not body:
        return JSONResponse({"ok": False, "error": "title/body required"}, status_code=400)
    rec = notes_mod.add(title, body)
    collector.emit("system", f"연구 노트 추가: {rec['title'][:60]}", "ok")
    return {"ok": True, "note": rec}


# 보조(원본 외 유지): 차트/최신값 — 다른 클라이언트 호환용
@app.get("/api/latest")
async def api_latest():
    if not collector.latest:
        await collector.collect_latest()
    return {"latest": collector.latest or None, "context": collector.context}


@app.get("/api/chart")
async def api_chart(range: str = "1d"):
    return await collector.get_chart(range)


_STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
if os.path.isdir(_STATIC_DIR):
    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
