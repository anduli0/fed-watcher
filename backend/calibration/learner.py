"""Learning layer — turns matured FOMC outcomes into model corrections.

Fitted once per cycle from the DB (no AI tokens) and stored in `model_state`:

  agent_skill     empirical-Bayes agent multipliers by months-ahead bucket:
                  w_a ∝ 1 / (MSE_a + τ), normalised to mean 1, clipped [0.5, 2].
                  τ (prior strength) shrinks toward equal weights when n is small.
  conf_map        isotonic regression stated-confidence → P(direction correct),
                  fitted on matured per-meeting agent calls. Identity until n ≥ N_MIN.
  conformal       split-conformal |published − realized| quantiles (68 / 90 %) by
                  bucket → prediction band. Falls back to committee dispersion.
  scores          committee Brier / log score of the per-meeting hike/hold/cut
                  probabilities, hit-rate, MAE — the honest outcome track record.

Empirical basis (2026-07-21 → 09-04 sample, 193 cycles, one realized +25 bp):
confidence is informative (corr(conf,|err|) = −0.42 at 6m; conf^2.5 weighting
beat equal / inverse-MSE / BMA out of sample), the ±1σ dispersion band covered
100 % (nominal 68 %), and shrinking toward the market prior only hurt. So the
defaults keep confidence weighting, use conformal bands once available, and
apply no market shrinkage.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models import AgentOutput, HorizonForecast, ModelState

logger = logging.getLogger("fed_watcher.calibration")

STATE_KEY = "calibration_v1"
SETTLE_DAYS = 2                 # DFF reflects a decision from the next business day
N_MIN_SKILL = 8                 # matured outcomes per agent before skill weights move
N_MIN_CONF = 60                 # matured agent calls before the isotonic map is used
N_MIN_CONFORMAL = 20            # matured committee calls per bucket for conformal bands
TAU_BPS2 = 400.0                # EB prior strength (bps²) — 20 bps "typical" error
SKILL_CLIP = (0.5, 2.0)
STATES = (-100, -75, -50, -25, 0, 25, 50, 75, 100)   # cumulative-delta states (bps)
SIGN_BAND = 12.5

BUCKETS = (("0-6m", 0, 6), ("6-18m", 6, 18), ("18m+", 18, 10_000))


def bucket_of(months_ahead: float | None) -> str:
    m = months_ahead if months_ahead is not None else 12.0
    for name, lo, hi in BUCKETS:
        if lo <= m < hi:
            return name
    return BUCKETS[-1][0]


def _sign(x: float) -> int:
    return 1 if x >= SIGN_BAND else (-1 if x <= -SIGN_BAND else 0)


# ── probability distribution over quantised states ──────────────────────────

def state_distribution(deltas: list[float], weights: list[float], confs: list[float]) -> dict:
    """Weighted kernel mixture of agent calls over the 25 bp state grid.
    Each agent contributes a discrete Gaussian centred on its delta whose width
    shrinks with its (calibrated) confidence: σ = 50 bps at conf 0 → 12 bps at
    conf 1. Returns the state pmf plus P(cut / hold / hike) and the mean."""
    if not deltas:
        return {"states": {}, "p_cut": None, "p_hold": None, "p_hike": None, "mean": None}
    pmf = {s: 0.0 for s in STATES}
    wsum = 0.0
    for d, w, c in zip(deltas, weights, confs):
        c = max(0.0, min(1.0, c or 0.0))
        sigma = 50.0 - 38.0 * c
        ks = {s: math.exp(-0.5 * ((s - d) / sigma) ** 2) for s in STATES}
        z = sum(ks.values()) or 1.0
        for s in STATES:
            pmf[s] += w * ks[s] / z
        wsum += w
    if wsum <= 0:
        return {"states": {}, "p_cut": None, "p_hold": None, "p_hike": None, "mean": None}
    pmf = {s: v / wsum for s, v in pmf.items()}
    return {
        "states": {str(s): round(v, 4) for s, v in pmf.items()},
        "p_cut": round(sum(v for s, v in pmf.items() if s < 0), 4),
        "p_hold": round(pmf[0], 4),
        "p_hike": round(sum(v for s, v in pmf.items() if s > 0), 4),
        "mean": round(sum(s * v for s, v in pmf.items()), 1),
    }


def brier_3way(p_cut: float, p_hold: float, p_hike: float, realized_bps: float) -> float:
    r = _sign(realized_bps)
    y = {-1: 0.0, 0: 0.0, 1: 0.0}
    y[r] = 1.0
    return ((p_cut - y[-1]) ** 2 + (p_hold - y[0]) ** 2 + (p_hike - y[1]) ** 2) / 3.0


# ── isotonic regression (PAVA) — no sklearn dependency at runtime ───────────

def fit_isotonic(x: list[float], y: list[float]) -> list[tuple[float, float]]:
    """Pool-adjacent-violators on (x, y) → increasing step function as
    [(x_knot, y_hat)], y_hat non-decreasing in x."""
    pts = sorted(zip(x, y))
    blocks: list[list[float]] = []   # [sum_y, n, x_max]
    for xi, yi in pts:
        blocks.append([yi, 1, xi])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            a, b = blocks.pop(), blocks.pop()
            blocks.append([a[0] + b[0], a[1] + b[1], max(a[2], b[2])])
    knots: list[tuple[float, float]] = []
    for b in blocks:                       # merge blocks sharing the same x (keep the last, higher y)
        k = (round(b[2], 4), round(b[0] / b[1], 4))
        if knots and knots[-1][0] == k[0]:
            knots[-1] = k
        else:
            knots.append(k)
    return knots


def apply_isotonic(knots: list[tuple[float, float]] | None, x: float) -> float:
    if not knots:
        return x
    y = knots[0][1]
    for kx, ky in knots:
        if x >= kx:
            y = ky
        else:
            break
    return float(y)


# ── state container ─────────────────────────────────────────────────────────

@dataclass
class Calibration:
    fitted_at: str = ""
    n_matured_committee: int = 0
    n_matured_agent_calls: int = 0
    agent_skill: dict[str, dict[str, float]] = field(default_factory=dict)   # bucket → agent_id → multiplier
    agent_skill_n: dict[str, dict[str, int]] = field(default_factory=dict)
    conf_map: list[tuple[float, float]] | None = None
    conformal: dict[str, dict[str, float]] = field(default_factory=dict)     # bucket → {q68, q90, n}
    scores: dict = field(default_factory=dict)
    market_shrink: float = 0.0
    notes: list[str] = field(default_factory=list)

    def skill_multiplier(self, agent_id: int, months_ahead: float | None) -> float:
        return float(self.agent_skill.get(bucket_of(months_ahead), {}).get(str(agent_id), 1.0))

    def calibrated_conf(self, conf: float) -> float:
        return apply_isotonic(self.conf_map, conf)

    def band_bps(self, months_ahead: float | None, dispersion: float | None) -> tuple[float | None, str]:
        c = self.conformal.get(bucket_of(months_ahead))
        if c and c.get("n", 0) >= N_MIN_CONFORMAL:
            return float(c["q68"]), "conformal"
        return (float(dispersion) if dispersion is not None else None), "dispersion"

    def to_json(self) -> str:
        d = self.__dict__.copy()
        return json.dumps(d, ensure_ascii=False)

    @classmethod
    def from_json(cls, s: str) -> "Calibration":
        d = json.loads(s)
        c = cls()
        for k, v in d.items():
            if hasattr(c, k):
                setattr(c, k, v)
        if c.conf_map:
            c.conf_map = [tuple(p) for p in c.conf_map]
        return c


_CACHE: Calibration | None = None


async def load_calibration(db: AsyncSession) -> Calibration:
    global _CACHE
    row = (await db.execute(select(ModelState).where(ModelState.key == STATE_KEY))).scalar_one_or_none()
    _CACHE = Calibration.from_json(row.value_json) if row and row.value_json else Calibration()
    return _CACHE


def current_calibration() -> Calibration:
    return _CACHE or Calibration()


# ── fitting ─────────────────────────────────────────────────────────────────

async def fit_calibration(db: AsyncSession, dff_daily: list[dict]) -> Calibration:
    """Rebuild the calibration from every matured FOMC-meeting call in the DB.
    `dff_daily` = [{"date": "YYYY-MM-DD", "value": pct}] ascending."""
    cal = Calibration(fitted_at=datetime.utcnow().isoformat())
    if not dff_daily:
        cal.notes.append("no DFF series — calibration unchanged")
        return cal

    def dff_on(day: date) -> float | None:
        val = None
        s = day.isoformat()
        for o in dff_daily:
            if o["date"] <= s:
                val = o["value"]
            else:
                break
        return val

    today = date.today()
    rows = (await db.execute(
        select(HorizonForecast)
        .where(HorizonForecast.horizon_kind == "fomc")
        .where(HorizonForecast.is_published == True)  # noqa: E712
        .where(HorizonForecast.meeting_date.isnot(None))
    )).scalars().all()

    # Final pre-meeting call per (meeting) is what the ledger grades; for learning
    # we use EVERY issued call whose meeting has settled (more samples, each an
    # honest forecast at its issue time).
    matured: list[dict] = []
    for f in rows:
        m = date.fromisoformat(f.meeting_date)
        settle = m + timedelta(days=SETTLE_DAYS)
        if today < settle or not f.published_at:
            continue
        y0, y1 = dff_on(f.published_at.date()), dff_on(settle)
        if y0 is None or y1 is None:
            continue
        months = (m - f.published_at.date()).days / 30.4375
        matured.append({"run_id": f.run_id, "horizon": f.horizon, "months": months,
                        "pub": float(f.published_delta or 0.0), "real": (y1 - y0) * 100.0,
                        "probs": json.loads(f.probs_json) if f.probs_json else None})
    cal.n_matured_committee = len(matured)

    # ── committee scores + conformal residuals by bucket ──
    resid: dict[str, list[float]] = {}
    hits = briers = 0.0
    n_b = 0
    for r in matured:
        resid.setdefault(bucket_of(r["months"]), []).append(abs(r["pub"] - r["real"]))
        hits += 1.0 if _sign(r["pub"]) == _sign(r["real"]) else 0.0
        p = r["probs"]
        if p and p.get("p_cut") is not None:
            briers += brier_3way(p["p_cut"], p["p_hold"], p["p_hike"], r["real"])
            n_b += 1
    if matured:
        cal.scores = {
            "n": len(matured),
            "hit_rate": round(hits / len(matured), 3),
            "mae_bps": round(sum(abs(r["pub"] - r["real"]) for r in matured) / len(matured), 1),
            "brier": round(briers / n_b, 4) if n_b else None,
            "brier_n": n_b,
            "brier_climatology": 0.2222,   # uniform 1/3 over cut/hold/hike
        }
    for b, rs in resid.items():
        rs = sorted(rs)
        q = lambda p: rs[min(len(rs) - 1, int(math.ceil(p * len(rs)) - 1))]
        cal.conformal[b] = {"q68": round(q(0.68), 1), "q90": round(q(0.90), 1), "n": len(rs)}

    # ── agent-level: skill by bucket + confidence calibration ──
    if matured:
        run_ids = {r["run_id"] for r in matured}
        by_run: dict[int, list[dict]] = {}
        for r in matured:
            by_run.setdefault(r["run_id"], []).append(r)
        ao = (await db.execute(select(AgentOutput).where(AgentOutput.run_id.in_(run_ids)))).scalars().all()
        latest: dict[tuple[int, int], AgentOutput] = {}
        for a in ao:
            k = (a.run_id, a.agent_id)
            if k not in latest or (a.round or 1) > (latest[k].round or 1):
                latest[k] = a
        sq: dict[str, dict[int, list[float]]] = {}
        xs, ys = [], []
        for (run_id, agent_id), a in latest.items():
            try:
                hz = json.loads(a.horizons_json or "{}")
            except Exception:
                continue
            for r in by_run.get(run_id, []):
                v = hz.get(r["horizon"])
                if not isinstance(v, dict):
                    continue
                d = float(v.get("delta_bps", 0) or 0)
                c = float(v.get("confidence", 0) or 0)
                sq.setdefault(bucket_of(r["months"]), {}).setdefault(agent_id, []).append((d - r["real"]) ** 2)
                xs.append(c)
                ys.append(1.0 if _sign(d) == _sign(r["real"]) else 0.0)
        cal.n_matured_agent_calls = len(xs)
        for b, per_agent in sq.items():
            raw = {}
            for aid, errs in per_agent.items():
                if len(errs) >= N_MIN_SKILL:
                    raw[aid] = 1.0 / (sum(errs) / len(errs) + TAU_BPS2)
            if raw:
                mean_w = sum(raw.values()) / len(raw)
                cal.agent_skill[b] = {str(a): round(max(SKILL_CLIP[0], min(SKILL_CLIP[1], w / mean_w)), 3)
                                      for a, w in raw.items()}
                cal.agent_skill_n[b] = {str(a): len(per_agent[a]) for a in raw}
        if len(xs) >= N_MIN_CONF:
            cal.conf_map = fit_isotonic(xs, ys)
        else:
            cal.notes.append(f"conf_map identity: {len(xs)} matured agent calls < {N_MIN_CONF}")
    else:
        cal.notes.append("no matured FOMC-meeting calls yet — all corrections at defaults")

    # persist
    row = (await db.execute(select(ModelState).where(ModelState.key == STATE_KEY))).scalar_one_or_none()
    if row is None:
        row = ModelState(key=STATE_KEY)
        db.add(row)
    row.value_json = cal.to_json()
    row.updated_at = datetime.utcnow()
    await db.commit()
    global _CACHE
    _CACHE = cal
    logger.info("Calibration fitted: %d matured committee calls, %d agent calls, skill buckets %s",
                cal.n_matured_committee, cal.n_matured_agent_calls, list(cal.agent_skill))
    return cal
