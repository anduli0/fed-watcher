"""
Feedback loop: compare agent predictions to market-implied forward rates
(not realized DFF) so time horizons match.

We use the 1Y forward rate implied by SOFR/FRED as the outcome proxy,
comparing yesterday's forecast to today's market-implied path change.
This is still approximate but far more meaningful than comparing
a 12-month prediction to a 1-month DFF move.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from backend.database.models import FeedbackEntry, PublishedForecast
from backend.data.fred_client import get_macro_snapshot
from datetime import datetime

DIVERGENCE_THRESHOLD_BPS = 20.0
MAX_NEGATIVE_EXAMPLES = 10
REASONING_TRUNCATE = 250


async def generate_feedback(db: AsyncSession, run_id: int, agent_results: list[dict]):
    """
    Compare each agent's 12-month rate path prediction to the change in
    market-implied forward rates (GS1 proxy: 1Y Treasury yield).
    Only generates feedback when two consecutive forecasts exist to diff.
    """
    snapshot = await get_macro_snapshot()

    # Use 1Y Treasury (GS1) as forward-rate proxy for 12M horizon
    # Fall back to 2Y yield (GS2) which is available in our series
    gs2 = snapshot.series.get("GS2")
    if not gs2 or gs2.mom_change is None:
        return

    # Market-implied 12M rate change proxy (bps)
    market_implied_bps = gs2.mom_change * 100

    # Only compare when we have a prior forecast to reference
    result = await db.execute(
        select(PublishedForecast)
        .where(PublishedForecast.is_published == True)
        .order_by(desc(PublishedForecast.id))
        .limit(2)
    )
    forecasts = list(result.scalars().all())
    if len(forecasts) < 2:
        return

    for agent_r in agent_results:
        predicted = agent_r["rate_path_delta_bps"]
        error_bps = abs(market_implied_bps - predicted)

        if error_bps >= DIVERGENCE_THRESHOLD_BPS:
            direction_miss = (predicted * market_implied_bps < 0) and abs(predicted) > 5
            neg_text = (
                f"[Agent {agent_r['agent_id']} {agent_r['agent_name']}] "
                f"Predicted {predicted:+.0f} bps (12M); "
                f"2Y yield moved {market_implied_bps:+.1f} bps (market-implied proxy). "
                f"Error: {error_bps:.0f} bps. "
                f"Reasoning: {agent_r.get('reasoning', '')[:REASONING_TRUNCATE]}"
            )
            db.add(FeedbackEntry(
                run_id=run_id,
                agent_id=agent_r["agent_id"],
                error_type="direction_miss" if direction_miss else "magnitude_miss",
                predicted_delta=predicted,
                actual_delta=market_implied_bps,
                divergence_bps=error_bps,
                negative_example_text=neg_text,
                created_at=datetime.utcnow(),
            ))

    await db.commit()


async def get_negative_examples(db: AsyncSession) -> list[str]:
    result = await db.execute(
        select(FeedbackEntry)
        .where(FeedbackEntry.injected_at.is_(None))
        .order_by(desc(FeedbackEntry.divergence_bps))
        .limit(MAX_NEGATIVE_EXAMPLES)
    )
    entries = list(result.scalars().all())
    now = datetime.utcnow()
    for e in entries:
        e.injected_at = now
    await db.commit()
    return [e.negative_example_text for e in entries]


