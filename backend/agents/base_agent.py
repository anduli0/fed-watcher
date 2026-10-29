from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import asyncio
import os
import time
import json
import re
import statistics

# Constrained hosts (e.g. Render free tier) can't afford N serialized claude
# calls per agent — cap self-consistency sampling via env. 0 = no cap.
_SELF_CONSISTENCY_CAP = int(os.getenv("AGENT_SELF_CONSISTENCY_CAP", "0"))
from backend.claude_cli import call_claude
from backend.config import settings
from backend.fomc_calendar import HorizonSpec, schedule_block

REASONING_TRUNCATE = 600

# Cross-horizon coherence: max acceptable absolute change between consecutive
# horizons (bps). Adjacent FOMC meetings can move at most 75 bps (a 50 bps move
# is already a fast cycle); the jump into / between the long-run keys is looser.
COHERENCE_LIMIT_FOMC_STEP = 75
COHERENCE_LIMIT_LONG_STEP = 150

# Confidence floor for incoherent outputs (if output fails coherence check)
COHERENCE_PENALTY_CAP = 0.5

# Data-availability ceilings — agents reporting overconfidence on sparse data are capped.
# Calibrates the well-known "Claude is too eager" problem.
DATA_RICH_CONF_FLOOR   = 0.0    # rich data → no cap (allow up to 0.95)
DATA_MEDIUM_CONF_CAP   = 0.65   # ≥2 of 4 sources missing → cap at 0.65
DATA_SPARSE_CONF_CAP   = 0.45   # ≥3 of 4 sources missing → cap at 0.45


@dataclass
class AgentContext:
    macro_snapshot_text: str = ""
    speeches_text: str = ""
    fomc_minutes_texts: list[str] = field(default_factory=list)
    beige_book_text: str = ""
    regional_stances_text: str = ""
    cme_probabilities: dict = field(default_factory=dict)
    negative_examples: list[str] = field(default_factory=list)
    material_event: Optional[str] = None
    consensus_summary: Optional[str] = None
    own_round1_output: Optional[str] = None
    market_prior_text: str = ""      # market-implied path prior (curve forwards per meeting)
    market_implied: dict[str, float] = field(default_factory=dict)  # horizon key → implied bps
    self_critique: Optional[str] = None  # previous cycle's process self-review
    fed_forward_signals: str = ""    # SEP dot plot + latest Fed-policy signals/news
    horizon_specs: list[HorizonSpec] = field(default_factory=list)  # FOMC-meeting horizons
    primary_key: Optional[str] = None  # headline key (meeting nearest 12 months ahead)

    @property
    def horizon_keys(self) -> list[str]:
        return [s.key for s in self.horizon_specs]

    def schedule_block(self) -> str:
        if not self.horizon_specs:
            return ""
        from datetime import date as _date
        return schedule_block(self.horizon_specs, self.primary_key, _date.today())

    def fed_forward_block(self) -> str:
        if not self.fed_forward_signals:
            return ""
        return (
            "\n\n### FORWARD-GUIDANCE SIGNALS (SEP dot plot + latest Fed-policy news)\n"
            + self.fed_forward_signals
            + "\nWeigh these forward-looking signals explicitly. The SEP dot-plot "
            "median relative to the current funds rate is a primary directional cue "
            "(median above current rate ⇒ hikes still projected). Remarks from current "
            "OR prospective Fed leadership can move the path. If the evidence points to "
            "hikes or cuts, reflect it — with a stated reason, quantized to 25bps.\n"
        )

    def market_prior_block(self) -> str:
        if not self.market_prior_text:
            return ""
        return (
            "\n\n### MARKET-IMPLIED PATH PRIOR (anchor discipline)\n"
            + self.market_prior_text
            + "\nStart from this market-implied path for each meeting. Deviate ONLY with explicit "
            "evidence, state the deviation in bps per meeting, and quantize your deltas to 25bps "
            "Fed-move increments. The market is usually right about the NEXT 1-2 meetings; your "
            "edge, if any, is in the 3-18 month range where data and Fed reaction functions matter "
            "more than pricing. Keep the meeting-by-meeting path economically coherent "
            "(smooth transitions, no sign zigzags).\n"
        )

    def self_critique_block(self) -> str:
        if not self.self_critique:
            return ""
        return (
            "\n\n### PROCESS SELF-REVIEW FROM PREVIOUS CYCLE (address this):\n"
            + self.self_critique + "\n"
        )

    def negative_examples_block(self) -> str:
        if not self.negative_examples:
            return ""
        block = "\n\n### NEGATIVE EXAMPLES (past prediction errors — learn from these):\n"
        for ex in self.negative_examples[-10:]:
            block += f"- {ex}\n"
        return block

    def collaboration_block(self) -> str:
        if not self.consensus_summary:
            return ""
        return (
            "\n\n### COLLABORATION REVIEW\n"
            "You previously analyzed independently. Now you see the aggregate consensus from your peers.\n"
            f"Your Round 1 output: {self.own_round1_output}\n\n"
            f"Peer consensus: {self.consensus_summary}\n\n"
            "Given this peer view, either confirm your original estimate OR revise it. "
            "Be honest — if other agents have stronger evidence, update. "
            "If you have a contrarian thesis worth holding, defend it.\n"
        )


@dataclass
class HorizonOutput:
    delta_bps: float
    confidence: float
    rationale: str = ""


@dataclass
class AgentResult:
    agent_id: int
    agent_name: str
    signal: str
    rate_path_delta_bps: float
    confidence: float
    reasoning: str
    horizons: dict[str, HorizonOutput] = field(default_factory=dict)
    primary_key: str = ""               # key behind rate_path_delta_bps / confidence
    limited_mode: bool = False
    duration_ms: int = 0
    round: int = 1
    revised: bool = False
    coherent: bool = True               # Cross-horizon coherence check passed?

    def horizon_delta(self, horizon: str) -> float:
        h = self.horizons.get(horizon)
        return h.delta_bps if h else self.rate_path_delta_bps

    def horizon_confidence(self, horizon: str) -> float:
        h = self.horizons.get(horizon)
        return h.confidence if h else self.confidence


def check_coherence(horizons: dict[str, HorizonOutput], specs: list[HorizonSpec]) -> tuple[bool, str]:
    """
    Validate cross-horizon coherence along the ordered FOMC path. Returns
    (is_coherent, reason). A path that swings violently between consecutive
    meetings is suspect.
    """
    ordered = [s for s in specs if s.key in horizons]
    for a, b in zip(ordered, ordered[1:]):
        limit = COHERENCE_LIMIT_FOMC_STEP if (a.is_fomc and b.is_fomc) else COHERENCE_LIMIT_LONG_STEP
        d1, d2 = horizons[a.key].delta_bps, horizons[b.key].delta_bps
        if abs(d2 - d1) > limit:
            return False, f"|{a.key}→{b.key}| {abs(d2 - d1):.0f}bps > {limit}bps limit"
    # Direction reversal with both magnitudes large = suspect
    deltas = [horizons[s.key].delta_bps for s in ordered]
    sign_flips = sum(
        1 for i in range(len(deltas) - 1)
        if deltas[i] * deltas[i + 1] < 0 and abs(deltas[i]) > 30 and abs(deltas[i + 1]) > 30
    )
    if sign_flips >= 2:
        return False, f"{sign_flips} large-magnitude sign reversals"
    return True, ""


def data_availability_cap(ctx: "AgentContext") -> float:
    """
    Compute a confidence ceiling based on how much data the agent actually received.
    Agents claiming high confidence on empty contexts get capped.

    Returns 1.0 (no cap) for rich contexts, 0.45 for sparse.
    """
    score = 0
    if ctx.macro_snapshot_text and len(ctx.macro_snapshot_text.strip()) > 100:
        score += 1
    if ctx.speeches_text and len(ctx.speeches_text.strip()) > 100:
        score += 1
    if ctx.fomc_minutes_texts and any(len(t.strip()) > 100 for t in ctx.fomc_minutes_texts):
        score += 1
    if ctx.cme_probabilities or (ctx.beige_book_text and len(ctx.beige_book_text.strip()) > 100):
        score += 1
    # 4=rich, 3=normal, 2=medium, ≤1=sparse
    if score >= 3:
        return 1.0
    if score == 2:
        return DATA_MEDIUM_CONF_CAP
    return DATA_SPARSE_CONF_CAP


class BaseAgent(ABC):
    agent_id: int
    agent_name: str
    weight: float = 1.0
    cache_ttl: int = 3600

    # ── Accuracy enhancements ──
    enable_thinking: bool = False        # Use extended thinking for higher-quality reasoning
    thinking_budget: int = 4000           # Tokens reserved for thinking
    self_consistency_n: int = 1           # Run N times and take median (1=disabled)

    def __init__(self):
        pass

    @abstractmethod
    def _system_prompt(self) -> str: ...

    @abstractmethod
    def _user_message(self, ctx: AgentContext) -> str: ...

    async def run(self, ctx: AgentContext) -> AgentResult:
        from backend.data import activity_log as AL
        round_num = 2 if ctx.consensus_summary else 1
        AL.agent_start(self.agent_name, round_num)
        t0 = time.time()

        sc_n = self.self_consistency_n
        if _SELF_CONSISTENCY_CAP > 0:
            sc_n = min(sc_n, _SELF_CONSISTENCY_CAP)
        if sc_n > 1:
            result = await self._self_consistency_call(ctx)
        else:
            result = await self._call_claude(ctx)

        # Post-parse coherence validation
        coherent, reason = check_coherence(result.horizons, ctx.horizon_specs)
        if not coherent:
            result.coherent = False
            for h, ho in result.horizons.items():
                ho.confidence = min(ho.confidence, COHERENCE_PENALTY_CAP)
            result.confidence = min(result.confidence, COHERENCE_PENALTY_CAP)
            AL.emit("agent", self.agent_name,
                    f"Incoherent output ({reason}) - confidence capped",
                    "#E5A03E", "warn")

        # Data-availability calibration: cap confidence when agent ran on sparse context
        data_cap = data_availability_cap(ctx)
        if data_cap < 1.0:
            for h, ho in result.horizons.items():
                ho.confidence = min(ho.confidence, data_cap)
            result.confidence = min(result.confidence, data_cap)

        result.duration_ms = int((time.time() - t0) * 1000)
        return result

    async def _self_consistency_call(self, ctx: AgentContext) -> AgentResult:
        """Run N samples in parallel, aggregate by median delta and mean confidence."""
        tasks = [self._call_claude(ctx, temperature=0.7) for _ in range(self.self_consistency_n)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid = [r for r in results if isinstance(r, AgentResult)]
        if not valid:
            return await self._call_claude(ctx)
        if len(valid) == 1:
            return valid[0]

        # Aggregate horizons by median delta, mean confidence
        merged_horizons = {}
        for h in ctx.horizon_keys:
            deltas = [r.horizon_delta(h) for r in valid]
            confs = [r.horizon_confidence(h) for r in valid]
            merged_horizons[h] = HorizonOutput(
                delta_bps=statistics.median(deltas),
                confidence=statistics.mean(confs),
                rationale=valid[0].horizons.get(h, HorizonOutput(0, 0)).rationale,
            )
        primary = ctx.primary_key or (ctx.horizon_keys[0] if ctx.horizon_keys else "")
        twelve = merged_horizons.get(primary, HorizonOutput(0.0, 0.3))
        # Signal from majority vote
        sig_counts = {"hawkish": 0, "neutral": 0, "dovish": 0}
        for r in valid:
            sig_counts[r.signal] = sig_counts.get(r.signal, 0) + 1
        majority_sig = max(sig_counts, key=sig_counts.get)

        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            signal=majority_sig,
            rate_path_delta_bps=twelve.delta_bps,
            confidence=twelve.confidence,
            reasoning=f"[Self-consistency n={len(valid)}] " + valid[0].reasoning[:400],
            horizons=merged_horizons,
            primary_key=primary,
        )

    async def _call_claude(self, ctx: AgentContext, temperature: float = 1.0) -> AgentResult:
        user_msg = (
            ctx.schedule_block()
            + ctx.market_prior_block()
            + ctx.fed_forward_block()
            + ctx.self_critique_block()
            + ctx.negative_examples_block()
            + ctx.collaboration_block()
            + "\n\n"
            + self._user_message(ctx)
        )
        raw = await call_claude(self._system_prompt(), user_msg)
        return self._parse(raw, ctx.horizon_keys, ctx.primary_key)

    def _parse(self, raw: str, keys: list[str], primary: Optional[str] = None) -> AgentResult:
        primary = primary or (keys[0] if keys else "")
        try:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
                horizons_raw = data.get("horizons", {}) or {}
                horizons = {}
                prev: HorizonOutput | None = None
                for h in keys:
                    h_data = horizons_raw.get(h)
                    if not isinstance(h_data, dict):
                        # Missing meeting → carry the previous meeting's call forward
                        # (a hold), at reduced confidence.
                        horizons[h] = HorizonOutput(
                            delta_bps=prev.delta_bps if prev else 0.0,
                            confidence=(prev.confidence * 0.8) if prev else 0.3,
                            rationale="carried forward (not reported)",
                        )
                    else:
                        horizons[h] = HorizonOutput(
                            delta_bps=float(h_data.get("delta_bps", prev.delta_bps if prev else 0)),
                            confidence=max(0.0, min(1.0, float(h_data.get("confidence", 0.4)))),
                            rationale=str(h_data.get("rationale", ""))[:200],
                        )
                    prev = horizons[h]
                twelve = horizons.get(primary, HorizonOutput(0.0, 0.3))
                return AgentResult(
                    agent_id=self.agent_id,
                    agent_name=self.agent_name,
                    signal=data.get("signal", "neutral"),
                    rate_path_delta_bps=twelve.delta_bps,
                    confidence=twelve.confidence,
                    reasoning=str(data.get("reasoning", raw[:REASONING_TRUNCATE]))[:REASONING_TRUNCATE],
                    horizons=horizons,
                    primary_key=primary,
                )
        except Exception:
            pass

        signal = "neutral"
        if any(w in raw.lower() for w in ["hawkish", "hike", "tighten"]):
            signal = "hawkish"
        elif any(w in raw.lower() for w in ["dovish", "cut", "ease"]):
            signal = "dovish"
        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            signal=signal,
            rate_path_delta_bps=0.0,
            confidence=0.3,
            reasoning=raw[:REASONING_TRUNCATE],
            horizons={h: HorizonOutput(0.0, 0.3, "parse_failed") for h in keys},
            primary_key=primary,
        )


OUTPUT_SCHEMA = """
Respond ONLY with this JSON structure — no prose before or after:
{
  "signal": "hawkish" | "neutral" | "dovish",
  "horizons": {
    "<key>": {"delta_bps": <float, multiple of 25 preferred>, "confidence": <0.00-0.95, two decimals>, "rationale": "<short phrase>"},
    ... ONE ENTRY FOR EVERY KEY listed under FORECAST HORIZONS — FOMC MEETING SCHEDULE
        (each FOMC decision date within 3 years, plus "5y", "10y", "30y") ...
  },
  "reasoning": "<2-3 sentence dominant thesis citing specific data points>"
}
Keys are the exact strings from the schedule (e.g. "2026-12-09", "5y"). "signal" and
"reasoning" describe the headline (primary) key. Keep each rationale under 12 words;
for a meeting that simply holds the prior level, "hold" is a sufficient rationale.

CRITICAL RULES — FAILURE TO COMPLY HURTS COMMITTEE ACCURACY:

1. PATH COHERENCE (hard constraint):
   delta_bps is CUMULATIVE from today's rate, so consecutive meetings differ by 0 or ±25 bps
   (±50 in a fast cycle, never more than 75). Steps into/between "5y", "10y", "30y" ≤ 150 bps.
   Long-run keys anchor to your long-run neutral rate view (~2.5-3%); deviation =
   (neutral - current) + structural premium. Two large-magnitude sign reversals is incoherent.

2. CONFIDENCE CALIBRATION (be brutally honest — your confidence is precision-weighted):
   - 0.80-0.90: You have direct, fresh, unambiguous data + a clear analytical chain → reasoning cites specifics.
   - 0.60-0.80: Strong data but some interpretation uncertainty or one missing input.
   - 0.40-0.60: Mixed signals, partial data, OR your domain only weakly informs this horizon.
   - 0.20-0.40: Sparse data, you are inferring more than measuring.
   - 0.10-0.20: You essentially have no signal — be honest, do not fabricate certainty.
   Confidence should normally DECLINE with distance: the next meeting is far more knowable
   than a meeting two years out, and "30y" is essentially a neutral-rate assumption.
   NEVER report confidence > 0.85 unless you can cite at least 3 specific data points.
   Overconfident guessing is the #1 source of committee error and is penalized in accuracy tracking.

3. DELTA_BPS PRECISION:
   - Cumulative change from CURRENT Fed Funds Rate in effect after that meeting. Negative = cuts. Positive = hikes.
   - Use multiples of 25 bps (the Fed moves in 25 bps quanta); 0 for a hold.
   - Avoid spurious precision (e.g., 23.7 bps).

4. REASONING QUALITY:
   - Cite specific data: "CPI 3.2% Mar→3.5% Apr → re-acceleration → +25 bps hawkish"
   - NOT vague: "Inflation pressures suggest potential tightening"
   - 2-3 sentences max. Lead with the strongest signal.
"""
