from dataclasses import dataclass
from typing import Optional
import statistics

# ── Stability parameters ────────────────────────────────────────────────────
# Adaptive EMA: alpha varies by volatility regime
ALPHA_LOW_VOL    = 0.18   # very stable: anchor harder to history
ALPHA_NORMAL     = 0.32   # baseline (was 0.25 — too sticky in regime changes)
ALPHA_HIGH_VOL   = 0.48   # high volatility: respond faster to new signal
ALPHA_EVENT      = 0.70   # material event day (was 0.60)
ALPHA_FIRST_RUN  = 0.92   # cold start

# Volatility thresholds (bps stdev across recent cycles)
VOL_LOW_THRESHOLD  = 18.0
VOL_HIGH_THRESHOLD = 55.0

# Conviction gates
MIN_CONFIDENCE      = 0.62   # was 0.65 — slightly lower since we now have committee-disagreement penalty
QUANTIZE_BPS        = 25.0
HALF_QUANTUM        = QUANTIZE_BPS / 2  # 12.5 bps — sub-quantum is always noise


@dataclass
class StabilizationResult:
    raw_delta: float
    smoothed_delta: float
    published_delta: float
    changed: bool
    unchanged_streak: int
    justification: Optional[str] = None
    alpha_used: float = 0.0
    regime: str = "normal"   # "low_vol" | "normal" | "high_vol" | "event" | "first_run"


def _adaptive_alpha(
    recent_raw_deltas: list[float] | None,
    is_event: bool,
    is_first_run: bool,
    event_alpha: float | None,
) -> tuple[float, str]:
    """Choose alpha based on regime — first run > event > volatility-adaptive."""
    if is_first_run:
        return ALPHA_FIRST_RUN, "first_run"
    if is_event:
        return (event_alpha if event_alpha is not None else ALPHA_EVENT), "event"
    if recent_raw_deltas and len(recent_raw_deltas) >= 3:
        vol = statistics.stdev(recent_raw_deltas)
        if vol < VOL_LOW_THRESHOLD:
            return ALPHA_LOW_VOL, "low_vol"
        if vol > VOL_HIGH_THRESHOLD:
            return ALPHA_HIGH_VOL, "high_vol"
    return ALPHA_NORMAL, "normal"


def _hold(
    raw_delta: float,
    smoothed: float,
    prev: float,
    streak: int,
    alpha: float,
    regime: str,
) -> StabilizationResult:
    return StabilizationResult(
        raw_delta=raw_delta,
        smoothed_delta=smoothed,
        published_delta=prev,
        changed=False,
        unchanged_streak=streak + 1,
        alpha_used=alpha,
        regime=regime,
    )


def stabilize(
    new_raw_delta: float,
    new_confidence: float,
    prev_published_delta: float,
    prev_streak: int,
    event: dict | None,
    bypass_ema: bool = False,
    recent_raw_deltas: list[float] | None = None,
) -> StabilizationResult:
    """
    5-stage stabilization with volatility-adaptive EMA.

    Stage 0: bypass_ema=True — quantize raw directly (forced cycles, flash analysis)
    Stage 1: Adaptive EMA — alpha depends on volatility regime, event, first-run
    Stage 2: Half-quantum gate — sub-12.5bps changes are always noise
    Stage 3: Conviction gate — low confidence blocks updates (event days bypass)
    Stage 4: 25 bps quantization + change detection
    """
    # Stage 0: Forced cycle bypass
    if bypass_ema:
        rounded = round(new_raw_delta / QUANTIZE_BPS) * QUANTIZE_BPS
        return StabilizationResult(
            raw_delta=new_raw_delta,
            smoothed_delta=new_raw_delta,
            published_delta=rounded,
            changed=(rounded != prev_published_delta),
            unchanged_streak=0 if rounded != prev_published_delta else prev_streak + 1,
            alpha_used=1.0,
            regime="bypass",
        )

    # Stage 1: Adaptive EMA
    first_run = (prev_streak == 0 and prev_published_delta == 0.0)
    event_alpha = event.get("alpha") if event else None
    alpha, regime = _adaptive_alpha(recent_raw_deltas, bool(event), first_run, event_alpha)
    smoothed = alpha * new_raw_delta + (1 - alpha) * prev_published_delta
    delta_from_prev = abs(smoothed - prev_published_delta)

    # Stage 2: Sub-quantum gate
    if delta_from_prev < HALF_QUANTUM:
        return _hold(new_raw_delta, smoothed, prev_published_delta, prev_streak, alpha, regime)

    # Stage 3: Conviction gate (bypassed on event days)
    if not event and new_confidence < MIN_CONFIDENCE:
        return _hold(new_raw_delta, smoothed, prev_published_delta, prev_streak, alpha, regime)

    # Stage 4: Quantize + detect change
    rounded = round(smoothed / QUANTIZE_BPS) * QUANTIZE_BPS
    changed = rounded != prev_published_delta
    streak = 0 if changed else prev_streak + 1

    return StabilizationResult(
        raw_delta=new_raw_delta,
        smoothed_delta=smoothed,
        published_delta=rounded,
        changed=changed,
        unchanged_streak=streak,
        alpha_used=alpha,
        regime=regime,
    )
