"""
Accuracy / self-review / backtest endpoints — exact parity with the reference
build's shapes and scoring rules.

- /api/accuracy/summary : realized-DFF maturity ledger. 6m/12m calls are graded
  against DFF at maturity; 3y/10y are never graded vs DFF. Adaptive weights
  stay frozen until >=8 matured outcomes per agent — no proxy grading.
- /api/accuracy/quality : per-cycle process self-review (works pre-maturity);
  the latest critique is injected into the next cycle's prompts.
- /api/backtest/skill   : mechanical directional engine (market-implied +
  Taylor + curve + inflation gap) scored on 20y of FRED history. Reference /
  lower bound on live skill, never blended with live accuracy.
"""
import math
from datetime import datetime, timedelta, date

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from backend.config import settings
from backend.database.init_db import get_db
from backend.database.models import HorizonForecast, AgentOutput, RunLog, HORIZONS
from backend.data.cache import data_cache

router = APIRouter(prefix="/api")

WINDOW_DAYS = {"6m": 183, "12m": 365, "3y": 1095, "10y": 3650}
GRADEABLE = ("6m", "12m")          # only these ever mature vs realized DFF
MIN_MATURED_FOR_ADAPTIVE = 8

FRED_OBS = "https://api.stlouisfed.org/fred/series/observations"


async def _series_daily(series_id: str, limit: int = 800) -> list[dict]:
    cache_key = f"acc_hist_{series_id}"
    cached = data_cache.get(cache_key, ttl_seconds=4 * 3600)
    if cached:
        return cached
    params = {
        "series_id": series_id, "api_key": settings.FRED_API_KEY,
        "file_type": "json", "limit": limit, "sort_order": "desc",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(FRED_OBS, params=params)
        r.raise_for_status()
    obs = [o for o in r.json().get("observations", []) if o["value"] != "."]
    obs.reverse()
    data = [{"date": o["date"], "value": float(o["value"])} for o in obs]
    data_cache.set(cache_key, data)
    return data


async def _series_monthly(series_id: str, start: str = "2004-01-01") -> list[dict]:
    cache_key = f"acc_hist_m_{series_id}"
    cached = data_cache.get(cache_key, ttl_seconds=24 * 3600)
    if cached:
        return cached
    params = {
        "series_id": series_id, "api_key": settings.FRED_API_KEY,
        "file_type": "json", "observation_start": start,
        "frequency": "m", "aggregation_method": "eop", "limit": 100000,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(FRED_OBS, params=params)
        r.raise_for_status()
    obs = [o for o in r.json().get("observations", []) if o["value"] != "."]
    data = [{"date": o["date"], "value": float(o["value"])} for o in obs]
    data_cache.set(cache_key, data)
    return data


def _value_on_or_before(obs: list[dict], day: str) -> float | None:
    val = None
    for o in obs:
        if o["date"] <= day:
            val = o["value"]
        else:
            break
    return val


async def horizon_dispersion(db: AsyncSession, run_id: int | None) -> dict[str, float]:
    """Population std (bps) of round-final agent deltas per horizon for a run."""
    if not run_id:
        return {}
    res = await db.execute(select(AgentOutput).where(AgentOutput.run_id == run_id))
    rows = list(res.scalars().all())
    # Round 2 output supersedes round 1 per agent
    by_agent: dict[int, AgentOutput] = {}
    for r in rows:
        cur = by_agent.get(r.agent_id)
        if cur is None or (r.round or 1) > (cur.round or 1):
            by_agent[r.agent_id] = r
    import json as _json
    out: dict[str, float] = {}
    for h in HORIZONS:
        vals = []
        for r in by_agent.values():
            try:
                hj = _json.loads(r.horizons_json or "{}")
                v = hj.get(h, {}).get("delta_bps")
                if v is None and h == "12m":
                    v = r.rate_path_delta_bps
                if v is not None:
                    vals.append(float(v))
            except Exception:
                continue
        if len(vals) >= 2:
            mean = sum(vals) / len(vals)
            out[h] = round(math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals)), 2)
    return out


# ── Maturity ledger (realized-DFF grading only) ──────────────────────────────

@router.get("/accuracy/summary")
async def accuracy_summary(db: AsyncSession = Depends(get_db)):
    today = date.today()
    try:
        dff = await _series_daily("DFF")
    except Exception:
        dff = []
    dff_now = dff[-1]["value"] if dff else None

    result = await db.execute(
        select(HorizonForecast)
        .where(HorizonForecast.is_published == True)  # noqa: E712
        .order_by(HorizonForecast.published_at)
    )
    forecasts = list(result.scalars().all())
    latest: dict[str, HorizonForecast] = {}
    for f in forecasts:
        latest[f.horizon] = f

    latest_issue = None
    tracking = []
    for h in HORIZONS:
        f = latest.get(h)
        if not f or not f.published_at:
            continue
        issued = f.published_at.date()
        latest_issue = issued if latest_issue is None else max(latest_issue, issued)
        dff_at_issue = _value_on_or_before(dff, issued.isoformat()) if dff else None
        realized = (
            round((dff_now - dff_at_issue) * 100, 1)
            if (dff_now is not None and dff_at_issue is not None) else None
        )
        tracking.append({
            "horizon": h,
            "predicted_delta_bps": f.published_delta,
            "signal": f.signal,
            "confidence": f.confidence,
            "dff_realized_so_far_bps": realized,
            "elapsed_days": (today - issued).days,
            "window_days": WINDOW_DAYS[h],
            "gradeable_vs_dff": h in GRADEABLE,
        })

    # Ledger: the latest issue per horizon; long horizons never grade vs DFF
    ledger = []
    matured_count = 0
    matured_hits = 0
    for h in HORIZONS:
        f = latest.get(h)
        if not f or not f.published_at:
            continue
        issued = f.published_at.date()
        if h not in GRADEABLE:
            ledger.append({
                "horizon": h,
                "issued": issued.isoformat(),
                "matures_on": None,
                "predicted_delta_bps": f.published_delta,
                "status": "never_vs_dff",
                "days_remaining": None,
            })
            continue
        matures = issued + timedelta(days=WINDOW_DAYS[h])
        entry = {
            "horizon": h,
            "issued": issued.isoformat(),
            "matures_on": matures.isoformat(),
            "predicted_delta_bps": f.published_delta,
            "status": "pending",
            "days_remaining": max(0, (matures - today).days),
        }
        if today >= matures and dff:
            y0 = _value_on_or_before(dff, issued.isoformat())
            y1 = _value_on_or_before(dff, matures.isoformat())
            if y0 is not None and y1 is not None:
                realized = round((y1 - y0) * 100, 1)
                pred = f.published_delta or 0.0
                hit = abs(realized) < 25.0 if abs(pred) < 12.5 else (pred * realized) > 0
                entry.update(status="matured", dff_realized_bps=realized, hit=hit)
                matured_count += 1
                if hit:
                    matured_hits += 1
        ledger.append(entry)

    # DFF move since the latest issue (context for "the Fed has held flat")
    dff_move = None
    if dff and latest_issue and dff_now is not None:
        base = _value_on_or_before(dff, latest_issue.isoformat())
        if base is not None:
            dff_move = round((dff_now - base) * 100, 1)

    first_maturity = None
    for e in ledger:
        if e.get("matures_on"):
            first_maturity = e["matures_on"] if first_maturity is None else min(first_maturity, e["matures_on"])

    return {
        "as_of": today.isoformat(),
        "matured_count": matured_count,
        "matured_hits": matured_hits,
        "dff_realized_move_bps": dff_move,
        "dff_flat": abs(dff_move) < 5 if dff_move is not None else None,
        "tracking": tracking,
        "maturity_ledger": ledger,
        "feedback_loop": {
            "status": "frozen_until_maturity" if matured_count < MIN_MATURED_FOR_ADAPTIVE else "active",
            "min_matured_for_adaptive": MIN_MATURED_FOR_ADAPTIVE,
            "note": (
                "Realized-DFF grader runs every cycle; adaptive agent weights stay "
                f"at 1.0 until ≥{MIN_MATURED_FOR_ADAPTIVE} matured outcomes per agent, "
                "then activate automatically. No fake proxy is used."
            ),
        },
        "disclaimer": (
            "No forecast has matured yet"
            + (f" (first 6m realized outcome ≈ {first_maturity})" if first_maturity else "")
            + " and the Fed has held flat, so a realized accuracy score is not yet "
            "computable. Near-term tracking is an indicative leading indicator, NOT a "
            "scored outcome. See /api/backtest/skill for historical skill of the core "
            "directional logic."
        ) if matured_count == 0 else None,
    }


# ── Per-cycle process self-review ────────────────────────────────────────────

def _sign(x: float, band: float = 12.5) -> int:
    if x >= band:
        return 1
    if x <= -band:
        return -1
    return 0


def _quality_for_run(hf_by_h: dict, agents: list[AgentOutput],
                     prev_by_h: dict | None, dispersion_12m: float | None):
    deltas = [hf_by_h[h].published_delta or 0.0 for h in HORIZONS if h in hf_by_h]
    signs = [_sign(d) for d in deltas]
    flips = sum(1 for a, b in zip(signs, signs[1:]) if a != 0 and b != 0 and a != b)
    term_coherence = max(0.0, 1.0 - flips / max(1, len(signs) - 1))

    ok = tot = 0
    for h in HORIZONS:
        f = hf_by_h.get(h)
        if not f:
            continue
        tot += 1
        expect = "hawkish" if (f.published_delta or 0) >= 25 else \
                 "dovish" if (f.published_delta or 0) <= -25 else "neutral"
        if f.signal == expect:
            ok += 1
    signal_consistency = ok / tot if tot else None

    # Consensus: applied-weight share of agents whose 12m sign matches the call
    consensus = None
    f12 = hf_by_h.get("12m")
    if f12 is not None and agents:
        by_agent: dict[int, AgentOutput] = {}
        for r in agents:
            cur = by_agent.get(r.agent_id)
            if cur is None or (r.round or 1) > (cur.round or 1):
                by_agent[r.agent_id] = r
        pub_sign = _sign(f12.published_delta or 0.0)
        wsum = agree = 0.0
        for r in by_agent.values():
            w = r.weight_applied or 1.0
            wsum += w
            if _sign(r.rate_path_delta_bps or 0.0) == pub_sign:
                agree += w
        if wsum > 0:
            consensus = agree / wsum

    # Calibration: committee dispersion should stay small relative to a full
    # hiking cycle's range (reference constant matches the original build).
    calibration = None
    if dispersion_12m is not None:
        calibration = round(max(0.0, 1.0 - dispersion_12m / 114.0), 6)

    prior_coherence = None
    if prev_by_h:
        jumps = []
        for h in HORIZONS:
            f, p = hf_by_h.get(h), prev_by_h.get(h)
            if f is not None and p is not None:
                jumps.append(abs((f.published_delta or 0) - (p.published_delta or 0)))
        if jumps:
            prior_coherence = round(max(0.0, 1.0 - (sum(jumps) / len(jumps)) / 100.0), 2)

    parts = [v for v in (term_coherence, signal_consistency, calibration,
                         consensus, prior_coherence) if v is not None]
    overall = round(sum(parts) / len(parts), 3) if parts else None

    critique = None
    dims = {
        "term_coherence": (term_coherence,
            "직전 사이클의 기간구조가 지그재그였다(부호가 6m→12m→3y→10y에서 반복 반전). "
            "다음 예측에선 각 호라이즌이 경제적으로 일관된 경로(완만한 전환)를 이루도록 하라."),
        "calibration": (calibration,
            "위원회 분산이 과도했다. 근거가 갈리면 신뢰도를 낮추고, 25bps 양자화 앵커로 수렴시켜라."),
        "consensus": (consensus,
            "가중 합의가 약한 채로 방향이 발표됐다. 소수 의견의 근거를 다음 사이클에서 재검증하라."),
        "signal_consistency": (signal_consistency,
            "발표 시그널 라벨이 델타 부호와 불일치했다. 라벨 규칙(±25bps 경계)을 재확인하라."),
        "prior_coherence": (prior_coherence,
            "직전 사이클 대비 발표치가 급변했다. 변경 사유를 명시적으로 정당화하라."),
    }
    scored = [(k, v, m) for k, (v, m) in dims.items() if v is not None]
    if scored:
        worst = min(scored, key=lambda x: x[1])
        if worst[1] < 0.85:
            critique = f"[PROCESS SELF-REVIEW · {worst[0]} {worst[1]:.2f}] {worst[2]}"

    return {
        "overall": overall,
        "term_coherence": term_coherence,
        "calibration": calibration,
        "signal_consistency": signal_consistency,
        "consensus": consensus,
        "prior_coherence": prior_coherence,
        "critique": critique,
    }


async def _quality_trend(db: AsyncSession, limit: int = 40) -> list[dict]:
    runs_res = await db.execute(
        select(RunLog).where(RunLog.status == "completed")
        .order_by(desc(RunLog.id)).limit(limit)
    )
    runs = list(runs_res.scalars().all())[::-1]
    trend = []
    prev_by_h: dict | None = None
    for run in runs:
        hf_res = await db.execute(
            select(HorizonForecast).where(HorizonForecast.run_id == run.id)
        )
        hf_by_h = {f.horizon: f for f in hf_res.scalars().all()}
        if not hf_by_h:
            continue
        ag_res = await db.execute(
            select(AgentOutput).where(AgentOutput.run_id == run.id)
        )
        agents = list(ag_res.scalars().all())
        disp = await horizon_dispersion(db, run.id)
        q = _quality_for_run(hf_by_h, agents, prev_by_h, disp.get("12m"))
        q["run_id"] = run.id
        q["at"] = run.completed_at.isoformat() if run.completed_at else None
        trend.append(q)
        prev_by_h = hf_by_h
    return trend


async def latest_critique(db: AsyncSession) -> str | None:
    """The most recent cycle's self-review critique — injected into the next cycle."""
    trend = await _quality_trend(db, limit=2)
    if trend and trend[-1].get("critique"):
        return trend[-1]["critique"]
    return None


@router.get("/accuracy/quality")
async def accuracy_quality(db: AsyncSession = Depends(get_db)):
    trend = await _quality_trend(db, limit=40)
    overalls = [t["overall"] for t in trend if t["overall"] is not None]
    return {
        "as_of": date.today().isoformat(),
        "n_cycles": len(trend),
        "latest": trend[-1] if trend else None,
        "mean_overall": round(sum(overalls) / len(overalls), 3) if overalls else None,
        "trend": trend,
    }


# ── Mechanical backtest (reference / lower bound) ────────────────────────────

@router.get("/backtest/skill")
async def backtest_skill():
    cached = data_cache.get("backtest_skill_v2", ttl_seconds=24 * 3600)
    if cached:
        return cached

    NEUTRAL_BAND = 25.0
    DEADBAND = 10.0
    ZLB = 0.5
    INFL_LAG = 1  # months of publication lag applied to CPI

    try:
        dff = await _series_monthly("DFF")
        gs2 = await _series_monthly("GS2")
        gs10 = await _series_monthly("GS10")
        cpi = await _series_monthly("CPIAUCSL")
    except Exception as e:
        return {"error": f"FRED unavailable: {e}"}

    by_date: dict[str, dict] = {}
    for series, key in ((dff, "dff"), (gs2, "gs2"), (gs10, "gs10"), (cpi, "cpi")):
        for row in series:
            by_date.setdefault(row["date"], {})[key] = row["value"]
    months = sorted(d for d, v in by_date.items() if "dff" in v and "gs2" in v)

    def cpi_yoy(i: int) -> float | None:
        j = i - INFL_LAG
        if j < 12:
            return None
        a = by_date.get(months[j], {}).get("cpi")
        b = by_date.get(months[j - 12], {}).get("cpi")
        if a is None or b is None or b == 0:
            return None
        return (a / b - 1.0) * 100.0

    def market_signal(i: int) -> int:
        row = by_date[months[i]]
        implied = (row["gs2"] - row["dff"]) * 100.0
        return 0 if abs(implied) < DEADBAND else (1 if implied > 0 else -1)

    def composite_signal(i: int) -> int:
        """market-implied + Taylor gap + curve slope + inflation gap, equal votes."""
        row = by_date[months[i]]
        votes = [market_signal(i)]
        yoy = cpi_yoy(i)
        if yoy is not None:
            taylor = 2.5 + yoy + 0.5 * (yoy - 2.0)   # output gap unobserved → omitted
            gap = (taylor - row["dff"]) * 100.0
            votes.append(0 if abs(gap) < NEUTRAL_BAND else (1 if gap > 0 else -1))
            votes.append(1 if yoy - 2.0 > 0.5 else (-1 if yoy - 2.0 < -0.5 else 0))
        if "gs10" in row:
            curve = (row["gs10"] - row["gs2"]) * 100.0
            votes.append(-1 if curve < -10 else (1 if curve > 150 else 0))
        s = sum(votes)
        return 0 if s == 0 else (1 if s > 0 else -1)

    def realized_sign(i: int, horizon_m: int, target: str) -> int | None:
        row, fwd = by_date[months[i]], by_date.get(months[i + horizon_m], {})
        if target not in row or target not in fwd:
            return None
        realized = (fwd[target] - row[target]) * 100.0
        return 0 if abs(realized) < NEUTRAL_BAND else (1 if realized > 0 else -1)

    # All horizons share the 12-month cutoff so 6m and 12m score the SAME
    # decision months (matches the reference build's uniform n).
    MAX_H = 12

    def eval_sign(signal_fn, horizon_m: int, excl_zlb: bool, target: str):
        n = hits = n_dir = hits_dir = 0
        for i in range(12 + INFL_LAG, len(months) - MAX_H):
            if excl_zlb and by_date[months[i]]["dff"] < ZLB:
                continue
            rs = realized_sign(i, horizon_m, target)
            if rs is None:
                continue
            sig = signal_fn(i)
            n += 1
            if sig == rs:
                hits += 1
            if sig != 0 and rs != 0:
                n_dir += 1
                if sig == rs:
                    hits_dir += 1
        return {
            "n": n,
            "hit_rate": round(hits / n, 3) if n else None,
            "hit_rate_directional_only": round(hits_dir / n_dir, 3) if n_dir else None,
            "n_directional": n_dir,
        }

    def eval_magnitude(horizon_m: int, excl_zlb: bool, target: str):
        errs, base_errs, n = [], [], 0
        for i in range(12 + INFL_LAG, len(months) - MAX_H):
            row = by_date[months[i]]
            if excl_zlb and row["dff"] < ZLB:
                continue
            fwd = by_date.get(months[i + horizon_m], {})
            if target not in row or target not in fwd:
                continue
            realized = (fwd[target] - row[target]) * 100.0
            pred = (row["gs2"] - row["dff"]) * 100.0 * 0.7 * (horizon_m / 12.0)
            errs.append(abs(realized - pred))
            base_errs.append(abs(realized))
            n += 1
        mae = round(sum(errs) / n, 1) if n else None
        base = round(sum(base_errs) / n, 1) if n else None
        return {
            "n": n,
            "predictor": "market_implied_point (GS2-DFF)*0.7*(h/12)",
            "mae_bps": mae,
            "baseline_no_change_mae_bps": base,
            "skill_vs_no_change": round(1 - mae / base, 3) if (mae is not None and base) else None,
        }

    def block(excl_zlb: bool, label: str):
        n_months = sum(
            1 for i in range(12 + INFL_LAG, len(months) - 12)
            if not (excl_zlb and by_date[months[i]]["dff"] < ZLB)
        )
        out = {"label": label, "n_months": n_months}
        for name, fn in (("market_only", market_signal), ("composite", composite_signal)):
            for target in ("DFF", "GS2"):
                for h in (6, 12):
                    out[f"sign__{name}__{target}__{h}m"] = eval_sign(fn, h, excl_zlb, target.lower())
        for target in ("DFF", "GS2"):
            for h in (6, 12):
                out[f"magnitude__{target}__{h}m"] = eval_magnitude(h, excl_zlb, target.lower())
        return out

    # Regime breakdown for DFF 6m: classify by the realized DFF move
    regimes = {"cutting": [0, 0, 0, 0], "hiking": [0, 0, 0, 0],
               "on_hold": [0, 0, 0, 0], "zlb": [0, 0, 0, 0]}
    for i in range(12 + INFL_LAG, len(months) - MAX_H):
        row = by_date[months[i]]
        rs = realized_sign(i, 6, "dff")
        if rs is None:
            continue
        if row["dff"] < ZLB:
            key = "zlb"
        elif rs > 0:
            key = "hiking"
        elif rs < 0:
            key = "cutting"
        else:
            key = "on_hold"
        sig = market_signal(i)
        r = regimes[key]
        r[0] += 1
        if sig == rs:
            r[1] += 1
        if sig != 0 and rs != 0:
            r[2] += 1
            if sig == rs:
                r[3] += 1
    regime_out = {
        k: {
            "n": v[0],
            "hit_rate": round(v[1] / v[0], 3) if v[0] else None,
            "hit_rate_directional_only": round(v[3] / v[2], 3) if v[2] else None,
            "n_directional": v[2],
        } for k, v in regimes.items()
    }

    payload = {
        "as_of_note": (
            "Backtest of the MECHANICAL directional engine (market-implied + Taylor "
            "+ curve + inflation gap), NOT the live 21-agent ensemble. "
            "Reference/lower bound on live skill."
        ),
        "data_range": {
            "start": months[12 + INFL_LAG][:7] if len(months) > 13 else None,
            "end": months[-1][:7] if months else None,
            "n_decision_months": max(0, len(months) - 12 - INFL_LAG - 12),
        },
        "knobs": {
            "neutral_band_bps": NEUTRAL_BAND,
            "market_deadband_bps": DEADBAND,
            "zlb_dff_pct": ZLB,
            "inflation_lag_months": INFL_LAG,
            "horizons_m": [6, 12],
        },
        "headline_excl_zlb": block(True, "All months excl. zero-lower-bound (DFF>=0.5%)"),
        "all_months": block(False, "All months incl. ZLB"),
        "regime_breakdown_DFF_6m": regime_out,
        "metric_note": (
            "hit_rate = directional SIGN accuracy of the signal; magnitude__* skill = "
            "separate MAGNITUDE error of the market-implied point forecast. They are "
            "distinct constructs and are reported separately, never blended into one number."
        ),
        "caveats": [
            "Overlapping monthly windows are autocorrelated → naive CIs are too tight; "
            "treat hit-rates as indicative, not significant point estimates.",
            "CPI/PCE use a 1-month publication lag but NOT full ALFRED vintaging, so "
            "small data revisions can leak; the headline market-only signal (GS2-DFF) "
            "is revision-free.",
            "GS2 target partly mechanical (signal is built from GS2-DFF) → DFF is the "
            "primary skill metric; GS2 is a secondary diagnostic.",
            "ZLB months (DFF<0.5%) excluded from headline because the funds rate "
            "physically cannot fall further there.",
        ],
    }
    data_cache.set("backtest_skill_v2", payload)
    return payload
