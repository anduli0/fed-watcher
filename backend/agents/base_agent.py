from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import asyncio
import time
import json
import re
import statistics
import anthropic
from backend.config import settings

REASONING_TRUNCATE = 600
HORIZONS = ("6m", "12m", "3y", "10y")

# Cross-horizon coherence: max acceptable absolute change between consecutive horizons (bps)
# E.g., 6m to 12m can differ by up to 100 bps (4 Fed moves over 6 months is extreme)
COHERENCE_LIMITS = {
    ("6m", "12m"):  100,
    ("12m", "3y"):  150,
    ("3y", "10y"):  200,
}

# Confidence floor for incoherent outputs (if output fails coherence check)
COHERENCE_PENALTY_CAP = 0.5


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


def check_coherence(horizons: dict[str, HorizonOutput]) -> tuple[bool, str]:
    """
    Validate cross-horizon coherence. Returns (is_coherent, reason).
    A path that swings violently between consecutive horizons is suspect.
    """
    for (h1, h2), limit in COHERENCE_LIMITS.items():
        d1 = horizons.get(h1, HorizonOutput(0, 0)).delta_bps
        d2 = horizons.get(h2, HorizonOutput(0, 0)).delta_bps
        if abs(d2 - d1) > limit:
            return False, f"|{h1}→{h2}| {abs(d2 - d1):.0f}bps > {limit}bps limit"
    # Direction reversal with both magnitudes large = suspect
    deltas = [horizons.get(h, HorizonOutput(0, 0)).delta_bps for h in HORIZONS]
    sign_flips = sum(
        1 for i in range(len(deltas) - 1)
        if deltas[i] * deltas[i + 1] < 0 and abs(deltas[i]) > 30 and abs(deltas[i + 1]) > 30
    )
    if sign_flips >= 2:
        return False, f"{sign_flips} large-magnitude sign reversals"
    return True, ""


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
        self._client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    @abstractmethod
    def _system_prompt(self) -> str: ...

    @abstractmethod
    def _user_message(self, ctx: AgentContext) -> str: ...

    async def run(self, ctx: AgentContext) -> AgentResult:
        from backend.data import activity_log as AL
        round_num = 2 if ctx.consensus_summary else 1
        AL.agent_start(self.agent_name, round_num)
        t0 = time.time()

        if self.self_consistency_n > 1:
            result = await self._self_consistency_call(ctx)
        else:
            result = await self._call_claude(ctx)

        # Post-parse coherence validation
        coherent, reason = check_coherence(result.horizons)
        if not coherent:
            result.coherent = False
            # Cap confidence on all horizons
            for h, ho in result.horizons.items():
                ho.confidence = min(ho.confidence, COHERENCE_PENALTY_CAP)
            result.confidence = min(result.confidence, COHERENCE_PENALTY_CAP)
            AL.emit("agent", self.agent_name,
                    f"⚠ Incoherent output ({reason}) — confidence capped",
                    "#E5A03E", "warn")

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
        for h in HORIZONS:
            deltas = [r.horizon_delta(h) for r in valid]
            confs = [r.horizon_confidence(h) for r in valid]
            merged_horizons[h] = HorizonOutput(
                delta_bps=statistics.median(deltas),
                confidence=statistics.mean(confs),
                rationale=valid[0].horizons.get(h, HorizonOutput(0, 0)).rationale,
            )
        twelve = merged_horizons["12m"]
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
        )

    async def _call_claude(self, ctx: AgentContext, temperature: float = 1.0) -> AgentResult:
        user_msg = (
            ctx.negative_examples_block()
            + ctx.collaboration_block()
            + "\n\n"
            + self._user_message(ctx)
        )
        kwargs: dict = {
            "model": settings.MODEL_ID,
            "max_tokens": 1500 + (self.thinking_budget if self.enable_thinking else 0),
            "system": [{
                "type": "text",
                "text": self._system_prompt(),
                "cache_control": {"type": "ephemeral"},
            }],
            "messages": [{"role": "user", "content": user_msg}],
        }
        if self.enable_thinking:
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": self.thinking_budget}
            # Thinking requires temperature=1.0
            kwargs["temperature"] = 1.0
        else:
            kwargs["temperature"] = temperature

        try:
            response = await self._client.messages.create(**kwargs)
        except anthropic.BadRequestError:
            # Some models don't support thinking — fall back gracefully
            kwargs.pop("thinking", None)
            kwargs["temperature"] = temperature
            response = await self._client.messages.create(**kwargs)

        # Extract text content (skip thinking blocks)
        raw = ""
        for block in response.content:
            if hasattr(block, "text"):
                raw += block.text
        return self._parse(raw)

    def _parse(self, raw: str) -> AgentResult:
        try:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
                horizons_raw = data.get("horizons", {}) or {}
                horizons = {}
                for h in HORIZONS:
                    h_data = horizons_raw.get(h, {})
                    horizons[h] = HorizonOutput(
                        delta_bps=float(h_data.get("delta_bps", 0)),
                        confidence=max(0.0, min(1.0, float(h_data.get("confidence", 0.4)))),
                        rationale=str(h_data.get("rationale", ""))[:200],
                    )
                twelve = horizons["12m"]
                return AgentResult(
                    agent_id=self.agent_id,
                    agent_name=self.agent_name,
                    signal=data.get("signal", "neutral"),
                    rate_path_delta_bps=twelve.delta_bps,
                    confidence=twelve.confidence,
                    reasoning=str(data.get("reasoning", raw[:REASONING_TRUNCATE]))[:REASONING_TRUNCATE],
                    horizons=horizons,
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
            horizons={h: HorizonOutput(0.0, 0.3, "parse_failed") for h in HORIZONS},
        )


OUTPUT_SCHEMA = """
Respond ONLY with this JSON structure — no prose before or after:
{
  "signal": "hawkish" | "neutral" | "dovish",
  "horizons": {
    "6m":  {"delta_bps": <float>, "confidence": <0.0-1.0>, "rationale": "<one sentence>"},
    "12m": {"delta_bps": <float>, "confidence": <0.0-1.0>, "rationale": "<one sentence>"},
    "3y":  {"delta_bps": <float>, "confidence": <0.0-1.0>, "rationale": "<one sentence>"},
    "10y": {"delta_bps": <float>, "confidence": <0.0-1.0>, "rationale": "<one sentence>"}
  },
  "reasoning": "<2-3 sentence dominant thesis>"
}

CRITICAL RULES:
1. Cross-horizon coherence: Adjacent horizons cannot diverge by >100bps (6m↔12m) or >150bps (12m↔3y).
   10y should tend toward long-run neutral (~2.5%), so delta = neutral_rate - current_rate ± structural shift.
2. Confidence calibration:
   - 0.7–0.9: Strong data directly relevant to your domain + clear thesis
   - 0.5–0.7: Good data but some uncertainty or mixed signals
   - 0.3–0.5: Limited/partial data or significant uncertainty
   - 0.1–0.3: Little/no data — you are guessing; BE HONEST about this
   IMPORTANT: If the data section below is sparse or empty, set confidence 0.15–0.25, NOT higher.
   Overconfident guessing is WORSE than honest low confidence.
3. delta_bps: cumulative change from current Fed Funds Rate; negative=cuts, positive=hikes.
"""
