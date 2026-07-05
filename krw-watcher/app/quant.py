"""
Quant layer — verbatim port of the PC app's data-driven subsystems:
- 15y daily USD/KRW history (stooq full CSV, yahoo fallback)
- /api/accuracy/track: walk-forward sim of a momentum+mean-reversion proxy
  (+ live matured committee forecasts) and the auto-correction adjustment
- /api/daily-ohlc: daily H/L/C prediction with band-multiplier feedback
- /api/backtest: proxy strategy backtest with equity curve
"""
import json
import logging
import math
import os
import statistics
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

import httpx

from . import collector

logger = logging.getLogger("krw_watcher.quant")
KST = ZoneInfo("Asia/Seoul")
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
DSTORE = os.path.join(DATA_DIR, "daily.json")

H_DAYS = {"1w": 7, "1m": 30, "3m": 91, "12m": 365}
TARGET_COV = 0.8

_hist: dict[str, Any] = {"rows": [], "fetched": 0.0}
D: dict[str, Any] = {"track": [], "band_mult": 1.15, "band_prior": 1.15}


def load() -> None:
    global D
    try:
        with open(DSTORE, encoding="utf-8") as f:
            D.update(json.load(f))
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning("daily store load failed: %s", e)


def _save() -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(DSTORE, "w", encoding="utf-8") as f:
            json.dump(D, f, ensure_ascii=False)
    except Exception as e:
        logger.warning("daily store save failed: %s", e)


def daily_history() -> list[dict]:
    """Full daily OHLC history [{date,o,h,l,c}], cached 6h. stooq → yahoo."""
    if _hist["rows"] and time.time() - _hist["fetched"] < 21600:
        return _hist["rows"]
    rows: list[dict] = []
    try:
        r = httpx.get("https://stooq.com/q/d/l/", params={"s": "usdkrw", "i": "d"},
                      headers={"User-Agent": "Mozilla/5.0 krw-watcher"}, timeout=25)
        r.raise_for_status()
        for ln in r.text.strip().splitlines()[1:]:
            c = ln.split(",")
            if len(c) >= 5:
                try:
                    rows.append({"date": c[0], "o": float(c[1]), "h": float(c[2]),
                                 "l": float(c[3]), "c": float(c[4])})
                except ValueError:
                    continue
    except Exception as e:
        logger.info("stooq history failed: %s", str(e)[:80])
    if len(rows) < 100:
        try:
            r = httpx.get("https://query1.finance.yahoo.com/v8/finance/chart/KRW=X",
                          params={"range": "15y", "interval": "1d"},
                          headers={"User-Agent": "Mozilla/5.0"}, timeout=25)
            res = r.json()["chart"]["result"][0]
            q = res["indicators"]["quote"][0]
            for t, o, h, l, c in zip(res["timestamp"], q["open"], q["high"], q["low"], q["close"]):
                if c:
                    rows.append({"date": datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat(),
                                 "o": o or c, "h": h or c, "l": l or c, "c": c})
        except Exception as e:
            logger.info("yahoo history failed: %s", str(e)[:80])
    if rows:
        _hist["rows"] = rows
        _hist["fetched"] = time.time()
        collector.emit("collector", f"일별 히스토리 {len(rows)}일 확보", "ok")
    return _hist["rows"]


def _proxy_pred(closes: list[float], horizon_days: int, lookback: int = 20) -> float:
    """Momentum + mean-reversion proxy: predicted Δ over the horizon."""
    if len(closes) < lookback + 5:
        return 0.0
    mom = (closes[-1] - closes[-lookback]) / lookback          # daily drift
    ma = statistics.mean(closes[-lookback:])
    mr = (ma - closes[-1]) * 0.25                              # pull toward MA
    scale = math.sqrt(horizon_days)
    return mom * horizon_days * 0.35 + mr * min(scale / 4, 1.5)


def theory_anchors() -> dict:
    """호라이즌별 정량 이론 앵커 — 모멘텀+평균회귀 프록시(추세), 250일 평균으로의
    회귀(장기 균형/PPP형). 수석 프롬프트에 수치로 제공되고 최종 블렌딩에도 쓰인다."""
    rows = daily_history()
    closes = [r["c"] for r in rows]
    if len(closes) < 60:
        return {}
    out = {}
    ma = statistics.mean(closes[-250:]) if len(closes) >= 250 else statistics.mean(closes)
    for h, hd in H_DAYS.items():
        mm = _proxy_pred(closes, hd)
        ppp = (ma - closes[-1]) * min(hd / 365, 1.0) * 0.5
        out[h] = {"momentum_mr": round(mm, 1), "meanrev_250d": round(ppp, 1),
                  "mean": round((mm + ppp) / 2, 1)}
    return out


def track_payload(horizon: str, live_forecasts: list[dict]) -> dict:
    rows = daily_history()
    hd = H_DAYS.get(horizon, 30)
    closes = [r["c"] for r in rows]
    dates = [r["date"] for r in rows]
    series, preds, reals = [], [], []
    start = max(60, len(rows) - 3900)                          # ~15y of trading days
    step = max(1, (len(rows) - start - hd) // 160)             # ~160 chart points
    for i in range(start, len(rows) - hd, step):
        pred_d = _proxy_pred(closes[: i + 1], hd)
        real_d = closes[i + hd] - closes[i]
        series.append({"date": dates[i + hd], "from": dates[i],
                       "pred_rate": round(closes[i] + pred_d, 2),
                       "real_rate": round(closes[i + hd], 2),
                       "pred_delta": round(pred_d, 2), "real_delta": round(real_d, 2),
                       "hit": bool(pred_d * real_d > 0)})
        preds.append(pred_d)
        reals.append(real_d)
    # independent (non-overlapping) samples
    ind = [(p, r) for j, (p, r) in enumerate(zip(preds, reals)) if (j * step) % hd < step]
    ind_hits = [p * r > 0 for p, r in ind if abs(p) > 0.01]
    mae = statistics.mean(abs((p) - (r)) for p, r in zip(preds, reals)) if preds else None
    rw_mae = statistics.mean(abs(r) for r in reals) if reals else None
    ic = None
    if len(preds) > 5:
        try:
            mp, mr_ = statistics.mean(preds), statistics.mean(reals)
            cov = sum((p - mp) * (r - mr_) for p, r in zip(preds, reals))
            ic = round(cov / math.sqrt(sum((p - mp) ** 2 for p in preds) *
                                       sum((r - mr_) ** 2 for r in reals) or 1), 3)
        except Exception:
            ic = None
    metrics = {"n": len(series),
               "independent_hit": round(sum(ind_hits) / len(ind_hits), 3) if ind_hits else None,
               "independent_n": len(ind_hits),
               "overlap_hit": round(sum(1 for p, r in zip(preds, reals) if p * r > 0) / len(preds), 3) if preds else None,
               "mae_krw": round(mae, 2) if mae else None,
               "rw_mae_krw": round(rw_mae, 2) if rw_mae else None,
               "ic": ic,
               "skill_vs_rw": round(1 - mae / rw_mae, 3) if mae and rw_mae else None}
    # live matured committee forecasts
    hist = {r["date"]: r["c"] for r in rows}
    dsort = sorted(hist)
    pts, lhits = [], []
    for f in live_forecasts:
        x = f["horizons"].get(horizon)
        if not x:
            continue
        tgt = (datetime.fromisoformat(f["created_kst"][:10]) + timedelta(days=hd)).date().isoformat()
        rd = next((d for d in dsort if d >= tgt), None)
        if rd is None:
            continue
        pred_rate = x["spot_at_run"] + x["published_delta_krw"]
        hit = (x["published_delta_krw"] > 0.5) == (hist[rd] - x["spot_at_run"] > 0)
        pts.append({"date": rd, "pred_rate": round(pred_rate, 2),
                    "real_rate": round(hist[rd], 2), "hit": bool(hit)})
        lhits.append(hit)
    live = {"points": pts,
            "metrics": {"n": len(pts), "dir_hit": round(sum(lhits) / len(lhits), 3)} if pts else None}
    return {"horizon": horizon,
            "sim": {"series": series, "metrics": metrics,
                    "span": [series[0]["from"], series[-1]["date"]] if series else None},
            "live": live, "adjustment": adjustment(live_forecasts)}


def adjustment(live_forecasts: Optional[list[dict]] = None) -> dict:
    """Auto-correction from live realized 1m errors; sim-prior until data."""
    if live_forecasts:
        rows = daily_history()
        hist = {r["date"]: r["c"] for r in rows}
        dsort = sorted(hist)
        errs = []
        for f in live_forecasts:
            x = f["horizons"].get("1m")
            if not x:
                continue
            tgt = (datetime.fromisoformat(f["created_kst"][:10]) + timedelta(days=30)).date().isoformat()
            rd = next((d for d in dsort if d >= tgt), None)
            if rd:
                errs.append((hist[rd] - x["spot_at_run"]) - x["published_delta_krw"])
        if len(errs) >= 5:
            bias = statistics.mean(errs)
            return {"bias_krw": round(bias * 0.5, 1), "scale": 1.0,
                    "conf_scale": 1.0, "conf_cap": 0.85,
                    "n_real": len(errs), "source": "live-feedback"}
    return {"bias_krw": 0.0, "scale": 1.0, "conf_scale": 1.0,
            "conf_cap": 0.6, "n_real": 0, "source": "sim-prior"}


# ── daily H/L/C prediction with band feedback ────────────────────────────────
def _predict_day(prev_rows: list[dict], band_mult: float) -> dict:
    closes = [r["c"] for r in prev_rows]
    prev = prev_rows[-1]
    mom = statistics.mean(b - a for a, b in zip(closes[-6:], closes[-5:])) if len(closes) > 6 else 0
    ups = [r["h"] - r["o"] for r in prev_rows[-20:]]
    dns = [r["o"] - r["l"] for r in prev_rows[-20:]]
    up, dn = statistics.mean(ups), statistics.mean(dns)
    pred_close = prev["c"] + mom * 0.4
    return {"prev_close": round(prev["c"], 2), "pred_open": round(prev["c"], 2),
            "pred_high": round(prev["c"] + up * band_mult, 2),
            "pred_low": round(prev["c"] - dn * band_mult, 2),
            "pred_close": round(pred_close, 2),
            "band_mult": round(band_mult, 2),
            "exp_range": round((up + dn) * band_mult, 1)}


def daily_tick() -> None:
    """Ensure today's prediction exists; settle past days; adapt the band."""
    rows = daily_history()
    if len(rows) < 30:
        return
    today = datetime.now(KST).date().isoformat()
    track: list[dict] = D["track"]
    by_date = {t["date"]: t for t in track}
    # settle any past predictions with actual candles
    candles = {r["date"]: r for r in rows}
    changed = False
    for t in track:
        if t.get("actual_close") is None and t["date"] in candles and t["date"] < today:
            c = candles[t["date"]]
            t.update({"actual_high": c["h"], "actual_low": c["l"], "actual_close": c["c"],
                      "err_close": round(t["pred_close"] - c["c"], 2),
                      "close_in_band": bool(t["pred_low"] <= c["c"] <= t["pred_high"])})
            changed = True
    # band feedback
    settled = [t for t in track if t.get("actual_close") is not None][-40:]
    if len(settled) >= 8:
        cov = sum(1 for t in settled if t["close_in_band"]) / len(settled)
        prior = D["band_mult"]
        if cov < TARGET_COV - 0.05:
            D["band_mult"] = round(min(prior * 1.06, 2.5), 2)
        elif cov > TARGET_COV + 0.1:
            D["band_mult"] = round(max(prior * 0.97, 0.7), 2)
        if D["band_mult"] != prior:
            D["band_prior"] = prior
            changed = True
    # today's prediction
    if today not in by_date:
        hist_prev = [r for r in rows if r["date"] < today]
        p = _predict_day(hist_prev, D["band_mult"])
        track.append({"date": today, **p, "actual_high": None, "actual_low": None,
                      "actual_close": None, "err_close": None})
        del track[:-200]
        changed = True
        collector.emit("collector",
                       f"금일 고저종 예측: {p['pred_low']}~{p['pred_high']} 종 {p['pred_close']} (×{p['band_mult']})",
                       "ok")
    if changed:
        _save()


def daily_payload() -> dict:
    daily_tick()
    track = D["track"]
    today = track[-1] if track else None
    # live intraday actuals for today from yahoo cache
    if today:
        meta_pts = (collector._charts.get("1d") or {}).get("points") or []
        if meta_pts:
            closes = [p[1] for p in meta_pts]
            today = {**today, "actual_high": round(max(closes), 2) if today["actual_close"] is None else today["actual_high"],
                     "actual_low": round(min(closes), 2) if today["actual_close"] is None else today["actual_low"]}
            today["actual_close"] = today.get("actual_close")
    settled = [t for t in track if t.get("actual_close") is not None]
    live = {"n": len(settled)}
    if settled:
        live.update({
            "close_mae": round(statistics.mean(abs(t["err_close"]) for t in settled), 2),
            "high_mae": round(statistics.mean(abs(t["pred_high"] - t["actual_high"]) for t in settled), 2),
            "low_mae": round(statistics.mean(abs(t["pred_low"] - t["actual_low"]) for t in settled), 2),
            "coverage": round(sum(1 for t in settled if t["close_in_band"]) / len(settled), 2),
            "range_contained": round(sum(1 for t in settled
                                         if t["pred_low"] <= t["actual_low"] and t["actual_high"] <= t["pred_high"])
                                     / len(settled), 2)})
    else:
        live.update({"close_mae": None, "high_mae": None, "low_mae": None,
                     "coverage": None, "range_contained": None})
    return {"today": today, "track": track[-140:],
            "live": live,
            "band": {"current": D["band_mult"], "prior": D.get("band_prior"),
                     "target_coverage": TARGET_COV,
                     "realized_coverage": live.get("coverage"), "n": len(settled)}}


def backtest(years: int = 12, lookback: int = 20, horizon: str = "1m") -> dict:
    rows = daily_history()
    hd = H_DAYS.get(horizon, 30)
    n_days = min(len(rows) - hd - lookback - 5, years * 252)
    if n_days < 100:
        return {"ok": False, "error": "insufficient history"}
    closes = [r["c"] for r in rows]
    start = len(rows) - hd - n_days
    equity, eq, trades, wins, rets = [], 1.0, 0, 0, []
    i = start
    while i < len(rows) - hd:
        pred = _proxy_pred(closes[: i + 1], hd, lookback)
        if abs(pred) > 3.0:
            real = closes[i + hd] - closes[i]
            r = (real / closes[i]) * (1 if pred > 0 else -1)
            eq *= 1 + r
            trades += 1
            wins += 1 if r > 0 else 0
            rets.append(r)
            i += hd
        else:
            i += 5
        equity.append(round(eq, 4))
    if not trades:
        return {"ok": False, "error": "no trades"}
    peak, mdd = equity[0], 0.0
    for v in equity:
        peak = max(peak, v)
        mdd = max(mdd, (peak - v) / peak)
    sharpe = round(statistics.mean(rets) / (statistics.stdev(rets) or 1) * math.sqrt(max(1, 252 / hd)), 2) \
        if len(rets) > 1 else None
    dir_hits = sum(1 for r in rets if r > 0)
    return {"ok": True, "result": {
        "n_trades": trades, "span": f"{rows[start]['date']}~{rows[-1]['date']}",
        "win_rate": round(wins / trades, 2),
        "total_return_pct": round((eq - 1) * 100, 1),
        "directional_hit_rate": round(dir_hits / trades, 2),
        "sharpe": sharpe, "max_drawdown_pct": round(mdd * 100, 1),
        "equity_curve": equity[:: max(1, len(equity) // 120)],
        "note": f"정량 프록시(모멘텀+평균회귀) · {horizon} 보유 · lookback {lookback}일 · |Δ|>3₩ 진입"}}
