from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from backend.database.init_db import get_db
from backend.database import crud
from backend.database.models import FeedbackEntry
from sqlalchemy import select, desc

router = APIRouter(prefix="/admin-secure-panel/api")


def require_admin(request: Request):
    if getattr(request.state, "role", None) != "admin":
        raise HTTPException(403, "Admin access required")


class WeightUpdate(BaseModel):
    agent_id: int
    weight: float


import json
from pathlib import Path

# Path relative to this file's parent (backend/) → project root
WEIGHTS_FILE = Path(__file__).resolve().parent.parent.parent / ".agent_weights.json"


def load_weights() -> dict:
    try:
        return json.loads(WEIGHTS_FILE.read_text(encoding="utf-8")) if WEIGHTS_FILE.exists() else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_weights(weights: dict):
    try:
        WEIGHTS_FILE.write_text(json.dumps(weights, indent=2), encoding="utf-8")
    except OSError as e:
        import logging
        logging.getLogger("fed_watcher").error("Failed to save weights: %s", e)


@router.get("/weights", dependencies=[Depends(require_admin)])
async def get_weights(request: Request):
    from backend.agents.orchestrator import ALL_AGENTS
    weights = load_weights()
    return [
        {
            "agent_id": a.agent_id,
            "agent_name": a.agent_name,
            "weight": weights.get(str(a.agent_id), a.weight),
        }
        for a in ALL_AGENTS
    ]


@router.patch("/weights", dependencies=[Depends(require_admin)])
async def update_weight(request: Request, update: WeightUpdate):
    if not (0.0 <= update.weight <= 2.0):
        raise HTTPException(400, "Weight must be 0.0–2.0")
    weights = load_weights()
    weights[str(update.agent_id)] = update.weight
    save_weights(weights)

    # Apply immediately to live orchestrator (no restart needed)
    from backend.agents.orchestrator import apply_weight_override
    apply_weight_override(update.agent_id, update.weight)
    return {"status": "updated", "agent_id": update.agent_id, "weight": update.weight}


@router.post("/run", dependencies=[Depends(require_admin)])
async def force_run(request: Request, db: AsyncSession = Depends(get_db)):
    """Trigger an immediate Orchestrator cycle."""
    from backend.main import trigger_cycle
    import asyncio
    asyncio.create_task(trigger_cycle("forced"))
    return {"status": "triggered"}


@router.get("/feedback", dependencies=[Depends(require_admin)])
async def get_feedback(request: Request, db: AsyncSession = Depends(get_db)):
    entries = await crud.get_feedback_entries(db, limit=50)
    return [
        {
            "id": e.id,
            "agent_id": e.agent_id,
            "error_type": e.error_type,
            "predicted_delta": e.predicted_delta,
            "actual_delta": e.actual_delta,
            "divergence_bps": e.divergence_bps,
            "negative_example_text": e.negative_example_text,
            "created_at": e.created_at,
            "curated_by_admin": e.curated_by_admin,
        }
        for e in entries
    ]


@router.delete("/feedback/{entry_id}", dependencies=[Depends(require_admin)])
async def delete_feedback(request: Request, entry_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FeedbackEntry).where(FeedbackEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Not found")
    await db.delete(entry)
    await db.commit()
    return {"status": "deleted"}


@router.get("/runs", dependencies=[Depends(require_admin)])
async def get_runs(request: Request, db: AsyncSession = Depends(get_db)):
    from backend.database.models import RunLog
    result = await db.execute(
        select(RunLog).order_by(desc(RunLog.id)).limit(20)
    )
    runs = list(result.scalars().all())
    return [
        {
            "id": r.id,
            "started_at": r.started_at,
            "completed_at": r.completed_at,
            "status": r.status,
            "cycle_type": r.cycle_type,
        }
        for r in runs
    ]
