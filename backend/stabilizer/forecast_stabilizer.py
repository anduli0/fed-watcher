from dataclasses import dataclass
from typing import Optional

# ── Stability parameters ────────────────────────────────────────────────────
ALPHA_NORMAL   = 0.25   # 평시: 이전 예측에 75% 앵커
ALPHA_EVENT    = 0.60   # 이벤트일: 신호에 60% 반응
MIN_CONFIDENCE = 0.65   # 이 미만이면 전일 예측 유지 (이벤트일 제외)
QUANTIZE_BPS   = 25.0   # 25 bps 단위 (Fed 1회 인상/인하)
HALF_QUANTUM   = QUANTIZE_BPS / 2  # 12.5 bps — 이 미만 변화는 항상 노이즈


@dataclass
class StabilizationResult:
    raw_delta: float
    smoothed_delta: float
    published_delta: float
    changed: bool
    unchanged_streak: int
    justification: Optional[str] = None


def _hold(
    raw_delta: float,
    smoothed: float,
    prev: float,
    streak: int,
) -> StabilizationResult:
    return StabilizationResult(
        raw_delta=raw_delta,
        smoothed_delta=smoothed,
        published_delta=prev,
        changed=False,
        unchanged_streak=streak + 1,
    )


def stabilize(
    new_raw_delta: float,
    new_confidence: float,
    prev_published_delta: float,
    prev_streak: int,
    event: dict | None,
    bypass_ema: bool = False,
) -> StabilizationResult:
    """
    4-stage stabilization pipeline.

    Stage 0: bypass_ema=True (forced cycles) — skip EMA/gates, quantize raw directly.
    Stage 1: EMA smoothing (alpha depends on material event or first-run)
    Stage 2: Half-quantum gate — changes < 12.5 bps are ALWAYS noise regardless of confidence
    Stage 3: Conviction gate — low confidence blocks updates unless it's an event day
    Stage 4: 25 bps quantization + change detection
    """
    # Stage 0: Forced cycle bypass — publish raw signal without EMA dampening
    if bypass_ema:
        rounded = round(new_raw_delta / QUANTIZE_BPS) * QUANTIZE_BPS
        return StabilizationResult(
            raw_delta=new_raw_delta,
            smoothed_delta=new_raw_delta,
            published_delta=rounded,
            changed=(rounded != prev_published_delta),
            unchanged_streak=0 if rounded != prev_published_delta else prev_streak + 1,
        )

    # Stage 1: EMA smoothing
    # First-run (no history): use high alpha so the initial signal comes through.
    first_run = (prev_streak == 0 and prev_published_delta == 0.0)
    if first_run:
        alpha = 0.9
    elif event:
        alpha = event["alpha"]
    else:
        alpha = ALPHA_NORMAL
    smoothed = alpha * new_raw_delta + (1 - alpha) * prev_published_delta

    delta_from_prev = abs(smoothed - prev_published_delta)

    # Stage 2: Hard gate — sub-quantum change is always noise
    if delta_from_prev < HALF_QUANTUM:
        return _hold(new_raw_delta, smoothed, prev_published_delta, prev_streak)

    # Stage 3: Conviction gate (bypassed on material event days)
    if not event and new_confidence < MIN_CONFIDENCE:
        return _hold(new_raw_delta, smoothed, prev_published_delta, prev_streak)

    # Stage 4: Quantize and detect change
    rounded = round(smoothed / QUANTIZE_BPS) * QUANTIZE_BPS
    changed = rounded != prev_published_delta
    streak = 0 if changed else prev_streak + 1

    return StabilizationResult(
        raw_delta=new_raw_delta,
        smoothed_delta=smoothed,
        published_delta=rounded,
        changed=changed,
        unchanged_streak=streak,
    )
