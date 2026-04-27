from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from backend.database.models import (
    RunLog, AgentOutput, PublishedForecast, FeedbackEntry, HorizonForecast,
    HORIZONS,
)
from datetime import datetime


async def create_run(db: AsyncSession, cycle_type: str = "scheduled") -> RunLog:
    run = RunLog(cycle_type=cycle_type)
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


async def complete_run(db: AsyncSession, run_id: int, status: str = "completed", collab_rounds: int = 1):
    result = await db.execute(select(RunLog).where(RunLog.id == run_id))
    run = result.scalar_one_or_none()
    if run:
        run.completed_at = datetime.utcnow()
        run.status = status
        run.collaboration_rounds = collab_rounds
        await db.commit()


async def save_agent_output(db: AsyncSession, data: dict) -> AgentOutput:
    obj = AgentOutput(**data)
    db.add(obj)
    await db.commit()
    return obj


# ── Horizon forecasts ──────────────────────────────────────────────────────

async def get_latest_horizon_forecast(db: AsyncSession, horizon: str) -> HorizonForecast | None:
    result = await db.execute(
        select(HorizonForecast)
        .where(HorizonForecast.horizon == horizon)
        .where(HorizonForecast.is_published == True)
        .order_by(desc(HorizonForecast.published_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_all_latest_horizons(db: AsyncSession) -> dict[str, HorizonForecast | None]:
    return {h: await get_latest_horizon_forecast(db, h) for h in HORIZONS}


async def save_horizon_forecast(db: AsyncSession, data: dict) -> HorizonForecast:
    obj = HorizonForecast(**data)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


async def get_horizon_history(db: AsyncSession, horizon: str, limit: int = 30) -> list[HorizonForecast]:
    result = await db.execute(
        select(HorizonForecast)
        .where(HorizonForecast.horizon == horizon)
        .where(HorizonForecast.is_published == True)
        .order_by(desc(HorizonForecast.published_at))
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_latest_report(db: AsyncSession, lang: str = "ko") -> str | None:
    """Master derivation report — returns Korean or English version."""
    result = await db.execute(
        select(HorizonForecast)
        .where(HorizonForecast.horizon == "12m")
        .where(HorizonForecast.is_published == True)
        .order_by(desc(HorizonForecast.published_at))
        .limit(1)
    )
    obj = result.scalar_one_or_none()
    if not obj:
        return None
    if lang == "en":
        return obj.report_text_en or obj.report_text   # fallback to KO if EN missing
    return obj.report_text or obj.report_text_en


# ── Backward-compat (12m PublishedForecast) ────────────────────────────────

async def get_latest_published_forecast(db: AsyncSession) -> PublishedForecast | None:
    result = await db.execute(
        select(PublishedForecast)
        .where(PublishedForecast.is_published == True)
        .order_by(desc(PublishedForecast.published_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def save_published_forecast(db: AsyncSession, data: dict) -> PublishedForecast:
    obj = PublishedForecast(**data)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


async def get_forecast_history(db: AsyncSession, limit: int = 30) -> list[PublishedForecast]:
    result = await db.execute(
        select(PublishedForecast)
        .where(PublishedForecast.is_published == True)
        .order_by(desc(PublishedForecast.published_at))
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_feedback_entries(db: AsyncSession, limit: int = 10) -> list[FeedbackEntry]:
    result = await db.execute(
        select(FeedbackEntry).order_by(desc(FeedbackEntry.created_at)).limit(limit)
    )
    return list(result.scalars().all())
