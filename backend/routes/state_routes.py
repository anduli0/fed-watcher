"""
State export/import — history survives container replacement.

The free tier has no persistent disk: every deploy (and any platform
instance replacement) starts from a fresh image and wipes SQLite. The
deploy workflow calls GET /api/state/export on the old container just
before deploying and POSTs the payload to /api/state/import on the new
one, so forecasts, the maturity ledger, trades, feedback and briefings
accumulate across deploys.

Both endpoints require the X-State-Key header to equal JWT_SECRET —
the deploy workflow already holds that secret.
"""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from backend.config import settings
from backend.database.init_db import get_db
from backend.database.models import (
    RunLog, AgentOutput, HorizonForecast, PublishedForecast,
    MockTrade, FeedbackEntry, DailyBriefing,
)

router = APIRouter(prefix="/api/state")

# Imported run ids are offset so they can never collide with runs the new
# container creates before the import lands.
RUN_ID_OFFSET = 100000

_DT_FIELDS = {"started_at", "completed_at", "published_at", "created_at",
              "updated_at", "injected_at", "generation_started_at",
              "generation_finished_at"}


def _check_key(key: str | None):
    if not key or key != settings.JWT_SECRET:
        raise HTTPException(401, "invalid state key")


def _row_to_dict(obj) -> dict:
    out = {}
    for col in obj.__table__.columns:
        v = getattr(obj, col.name)
        if isinstance(v, datetime):
            v = v.isoformat()
        out[col.name] = v
    return out


def _dict_to_kwargs(model, data: dict) -> dict:
    cols = {c.name for c in model.__table__.columns}
    out = {}
    for k, v in data.items():
        if k not in cols:
            continue
        if k in _DT_FIELDS and isinstance(v, str):
            try:
                v = datetime.fromisoformat(v)
            except ValueError:
                v = None
        out[k] = v
    return out


@router.get("/export")
async def export_state(
    db: AsyncSession = Depends(get_db),
    x_state_key: str | None = Header(default=None),
):
    _check_key(x_state_key)

    async def dump(model, order_col, limit: int | None = None):
        q = select(model).order_by(order_col)
        res = await db.execute(q)
        rows = [_row_to_dict(r) for r in res.scalars().all()]
        return rows[-limit:] if limit else rows

    # agent_output only for the runs still referenced by forecasts (dispersion
    # and the agents tab need them); cap to the last 30 runs to bound size.
    runs = await dump(RunLog, RunLog.id, limit=200)
    recent_run_ids = {r["id"] for r in runs[-30:]}
    res = await db.execute(
        select(AgentOutput).where(AgentOutput.run_id.in_(recent_run_ids))
    )
    agent_outputs = [_row_to_dict(r) for r in res.scalars().all()]

    return {
        "version": 1,
        "exported_at": datetime.utcnow().isoformat(),
        "run_log": runs,
        "agent_output": agent_outputs,
        "horizon_forecast": await dump(HorizonForecast, HorizonForecast.id),
        "published_forecast": await dump(PublishedForecast, PublishedForecast.id),
        "mock_trade": await dump(MockTrade, MockTrade.id),
        "feedback_entry": await dump(FeedbackEntry, FeedbackEntry.id, limit=500),
        "daily_briefing": await dump(DailyBriefing, DailyBriefing.id),
    }


@router.post("/import")
async def import_state(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    x_state_key: str | None = Header(default=None),
):
    _check_key(x_state_key)

    # Only restore into a fresh container: if published history already
    # exists, this container was either already restored or has run cycles
    # of its own — never merge on top.
    existing = await db.execute(select(func.count(HorizonForecast.id)))
    if (existing.scalar() or 0) > 0:
        return {"status": "skipped", "reason": "horizon_forecast not empty"}

    def off(v):
        return (v + RUN_ID_OFFSET) if isinstance(v, int) else v

    counts = {}
    id_fields_by_model = [
        (RunLog, "run_log", {"id"}),
        (AgentOutput, "agent_output", {"run_id"}),
        (HorizonForecast, "horizon_forecast", {"run_id"}),
        (MockTrade, "mock_trade", {"run_id"}),
        (FeedbackEntry, "feedback_entry", {"run_id"}),
        (PublishedForecast, "published_forecast", set()),
        (DailyBriefing, "daily_briefing", set()),
    ]
    for model, key, offset_fields in id_fields_by_model:
        rows = payload.get(key) or []
        n = 0
        for data in rows:
            kw = _dict_to_kwargs(model, data)
            for f in offset_fields:
                if kw.get(f) is not None:
                    kw[f] = off(kw[f])
            # drop primary keys except the offset run_log id (children
            # reference it), letting autoincrement assign fresh ids
            if model is not RunLog:
                kw.pop("id", None)
            db.add(model(**kw))
            n += 1
        counts[key] = n
    await db.commit()
    return {"status": "imported", "counts": counts}
