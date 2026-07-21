"""Daily fed-watcher job for GitHub Actions (no server, no Render).

Reproduces the schedule the cloud deployment ran, but on the Actions runner:
data collection -> 21-agent cycle -> briefing — then snapshots every
read-only API endpoint the frontend calls into static JSON files under
frontend/public/data/, so the statically-exported Next.js site on
GitHub Pages serves identical payloads without a backend.

MODE env selects what runs (default: full):
  full      collect + AI cycle (+ briefing if past 07:00 KST and missing) + export
  briefing  collect + briefing + export          (07:30 KST slot)
  refresh   collect + export — no AI tokens      (hourly market-data freshness)
  export    export only (re-publish from the stored DB)
"""
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# CI defaults — set before any backend import reads them.
os.environ.setdefault("DEV_MODE", "true")            # skip MAC hardware lock
os.environ.setdefault("ALLOWED_IPS", "*")
os.environ.setdefault("KEEPALIVE_INTERVAL_SEC", "0")
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite+aiosqlite:///{(ROOT / 'data' / 'fed_watcher.db').as_posix()}",
)
(ROOT / "data").mkdir(exist_ok=True)

EXPORT_DIR = ROOT / "frontend" / "public" / "data"

# Currently-deployed site — used to carry the activity feed across deploys so
# the Live tab streams continuously instead of resetting every run.
PAGES_URL = os.getenv("PAGES_URL", "https://anduli0.github.io/fed-watcher")

MODE = os.getenv("MODE", "full").strip().lower()

# (endpoint, output file) — mirrors every GET the frontend makes (lib/api.ts
# static adapter maps the same URLs to these paths).
ENDPOINTS = [
    ("/api/forecast/horizons", "forecast/horizons.json"),
    ("/api/forecast/history", "forecast/history.json"),
    ("/api/forecast/report?lang=ko", "forecast/report.ko.json"),
    ("/api/forecast/report?lang=en", "forecast/report.en.json"),
    ("/api/agents/status", "agents/status.json"),
    ("/api/today", "today.json"),
    ("/api/macro/indicators", "macro/indicators.json"),
    ("/api/macro/series/DFF", "macro/series/DFF.json"),
    ("/api/macro/series/GS2", "macro/series/GS2.json"),
    ("/api/macro/series/GS10", "macro/series/GS10.json"),
    ("/api/macro/series/T5YIE", "macro/series/T5YIE.json"),
    ("/api/track-record", "track-record.json"),
    ("/api/accuracy/summary", "accuracy/summary.json"),
    ("/api/accuracy/quality", "accuracy/quality.json"),
    ("/api/backtest/skill", "backtest/skill.json"),
    ("/api/trading", "trading.json"),
    ("/api/trading/desk", "trading/desk.json"),
    ("/api/briefings/latest?lang=ko", "briefings/latest.ko.json"),
    ("/api/briefings/latest?lang=en", "briefings/latest.en.json"),
]


def _now_kst():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Asia/Seoul"))


async def run_briefing():
    from backend.briefing.pipeline import run_briefing_pipeline
    try:
        await run_briefing_pipeline(target_date=_now_kst().date(), force=False)
    except Exception as e:
        print(f"[ci_daily] briefing failed (non-fatal): {e}")


async def run_pipeline():
    from backend.main import run_data_collection, trigger_cycle

    await run_data_collection()

    if MODE in ("full",):
        await trigger_cycle("scheduled")
        # Keep the briefing's original 07:30 KST cadence: the dedicated
        # briefing slot creates it; later full cycles only backfill if it is
        # still missing. Pre-dawn cycles (00:30/05:00 KST) never pre-generate.
        if _now_kst().hour >= 7:
            await run_briefing()
    elif MODE == "briefing":
        await run_briefing()


async def _merged_activity(client) -> list:
    """New in-process events appended after the currently-deployed feed, with
    ids continuing the old sequence — so the frontend's after_id polling picks
    up only what's new. Never fatal: falls back to just the new events."""
    r = await client.get("/api/activity")
    new = r.json() if r.status_code == 200 else []
    old = []
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15) as web:
            wr = await web.get(f"{PAGES_URL}/data/activity.json")
            if wr.status_code == 200 and isinstance(wr.json(), list):
                old = wr.json()
    except Exception:
        pass
    base = max((e.get("id", 0) for e in old), default=0)
    for i, e in enumerate(new):
        e["id"] = base + i + 1
    return (old + new)[-50:]


async def export_static():
    import httpx
    from backend.main import app

    def write(rel: str, payload) -> None:
        path = EXPORT_DIR / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        print(f"[ci_daily] exported {rel}")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://ci") as client:
        failures = []

        async def snap(url: str, rel: str):
            r = await client.get(url)
            if r.status_code != 200:
                failures.append(f"{url} -> {r.status_code}")
                return
            write(rel, r.json())

        for url, rel in ENDPOINTS:
            await snap(url, rel)

        # API-shaped mirror (extensionless files under data/api/...) so external
        # consumers — e.g. the MARKET watcher's serverless build — can point their
        # FED_WATCHER_BASE_URL at .../fed-watcher/data and reuse the exact live-API
        # paths with zero adapter changes. Korean variants are served at the bare
        # path (that is what the MARKET watcher consumes).
        for url, rel in [
            ("/api/forecast/horizons", "api/forecast/horizons"),
            ("/api/backtest/skill", "api/backtest/skill"),
            ("/api/briefings/latest?lang=ko", "api/briefings/latest"),
            ("/api/forecast/report?lang=ko", "api/forecast/report"),
        ]:
            await snap(url, rel)

        write("activity.json", await _merged_activity(client))

        # Briefing archive: index per language + one file per date.
        for lang in ("en", "ko"):
            r = await client.get(f"/api/briefings?lang={lang}&limit=60")
            items = r.json() if r.status_code == 200 else []
            write(f"briefings/index.{lang}.json", items)
            for it in items:
                d = it.get("briefing_date")
                if d:
                    await snap(f"/api/briefings/{d}?lang={lang}",
                               f"briefings/{d}.{lang}.json")

        if failures:
            print("[ci_daily] endpoints that failed to export:")
            for f in failures:
                print("  ", f)

    # The forecast is the one payload the site cannot ship without.
    if not (EXPORT_DIR / "forecast/horizons.json").exists():
        raise SystemExit("[ci_daily] FATAL: forecast/horizons.json was not exported")


async def main():
    print(f"[ci_daily] mode={MODE}")
    from backend.database.init_db import init_db
    await init_db()
    if MODE != "export":
        await run_pipeline()
    await export_static()
    print("[ci_daily] done")


if __name__ == "__main__":
    asyncio.run(main())
