"""
KRW-Watcher committee engine — verbatim port of the PC app's contract.

23 agents (학계 3 · 퍼블릭 6 · 프라이빗 14) → round-2 coordination of outliers
→ 3 group orchestrators → Chief reconciliation. Produces /api/forecast,
/api/agents, /api/hierarchy, /api/signal payload shapes exactly as the
original site's frontend consumes them. Paper broker + accuracy live here too.
"""
import asyncio
import json
import logging
import os
import re
import statistics
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

from . import collector
from .claude_cli import call_claude, verify_auth, ClaudeAuthError

logger = logging.getLogger("krw_watcher.engine")
KST = ZoneInfo("Asia/Seoul")
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
STORE = os.path.join(DATA_DIR, "state.json")

HORIZONS = ("1w", "1m", "3m", "12m")
H_DAYS = {"1w": 7, "1m": 30, "3m": 91, "12m": 365}
CONF_FLOOR = float(os.getenv("SIGNAL_CONF_FLOOR", "0.48"))
CASH_USD = 100000.0

# (name, group, persona focus) — names/groups mirror the original UI exactly.
ROSTER: list[tuple[str, str, str]] = [
    ("Fed_Policy",      "public",  "미 연준 통화정책 경로(점도표·QT·연설)와 달러 방향"),
    ("BOK_Policy",      "public",  "한국은행 기준금리 경로·금통위 스탠스·BOK 보고서/이슈노트와 원화"),
    ("US_Fiscal_Dollar","public",  "미국 재정적자·국채발행·달러 유동성"),
    ("Korea_External",  "public",  "한국 경상수지·투자소득 환류(BOK 2026-15)·외환보유액·대외건전성"),
    ("ECB_Global_CB",   "public",  "ECB 등 글로벌 중앙은행 정책과 교차환율 파급"),
    ("BOJ_Yen_Carry",   "public",  "BOJ 정책·엔캐리 청산이 원화에 주는 파급"),
    ("Intl_Bodies",     "academic","IMF·BIS·OECD 시각의 원화 밸류에이션·자본흐름"),
    ("Academic_FX",     "academic","환율결정이론(PPP·UIP·자산접근법) 기반 적정가치"),
    ("Monetary_BoP",    "academic","통화량(M2)·유동성·국제수지 항등식 관점의 중기 환율 경로"),
    ("Rate_Carry",      "private", "한미 금리차·스왑포인트·캐리 수익률"),
    ("Global_Risk",     "private", "국내외 리스크(지정학·신용·자본유출)와 위험선호·안전통화 수요"),
    ("Technical_Flow",  "private", "기술적 분석(추세·지지저항)과 수급 플로우"),
    ("CNY_Asia_EM",     "private", "위안화·아시아 통화 동조성과 신흥국 리스크"),
    ("Consensus",       "private", "IB 컨센서스·선물환 내재 경로 대비 괴리"),
    ("Market_Linkage",  "private", "주식·채권 등 자산시장 연계 신호(코스피 외인 수급)"),
    ("News_Sentiment",  "private", "최신 뉴스 톤·정부 정책 발표·외환당국의 안정 의지(구두개입·스무딩)"),
    ("Desk_GS",         "private", "골드만삭스 하우스뷰 스타일의 전망"),
    ("Desk_JPM",        "private", "JP모건 하우스뷰 스타일의 전망"),
    ("Desk_MS",         "private", "모건스탠리 하우스뷰 스타일의 전망"),
    ("Desk_Nomura",     "private", "노무라 하우스뷰 스타일의 전망"),
    ("Desk_Citi",       "private", "씨티 하우스뷰 스타일의 전망"),
    ("Desk_Samsung_Sec","private", "삼성증권 리서치 스타일의 전망"),
    ("Desk_Mirae",      "private", "미래에셋 리서치 스타일의 전망"),
]
GROUP_LABEL = {"academic": "학계(Academic)", "public": "퍼블릭(Public)", "private": "프라이빗(Private)"}

AGENT_SYSTEM = """당신은 USD/KRW 예측 위원회의 에이전트 '{name}'입니다. 전문 관점: {focus}
주어진 시장 데이터·뉴스·구조적 컨텍스트(연구 노트)만 근거로 당신 관점의 예측을 냅니다. 과장 금지.
경상수지 관련 판단 시: 흑자 헤드라인이 아니라 실제 달러 환류(송금·환전) 여부로 평가하세요(BOK 2026-15).
confidence는 당신의 실제 확신도를 0~1로 솔직하게: 근거가 뚜렷하면 0.7~0.85, 방향은 서면 0.55~0.7,
이론이 상충하거나 근거가 약하면 0.3~0.45. 예시 숫자를 그대로 베끼지 말고 스스로 판단하세요.
반드시 아래 JSON만 출력(코드펜스 금지). delta_krw는 스팟 대비 원(₩), 원화강세=음수, confidence는 0~1 소수:
{{"signal":"krw_weak|neutral|krw_strong","confidence":0.6,
 "horizons":{{"1w":{{"delta_krw":2,"confidence":0.62}},"1m":{{"delta_krw":5,"confidence":0.58,"rationale":"1개월 관점 근거 한 문장"}},"3m":{{"delta_krw":10,"confidence":0.5}},"12m":{{"delta_krw":20,"confidence":0.4}}}}}}"""

REVIEW_SYSTEM = """당신은 에이전트 '{name}'입니다. 위원회 1개월 합의({consensus:+.0f}원)에서 당신의 예측({mine:+.0f}원)이 크게 벗어났습니다.
합의 근거를 검토하고, 새 정보가 설득력 있으면 수정하고 아니면 견해를 고수하세요(수정은 권장이지 페널티가 아님).
JSON만 출력: {{"revised":true/false,"horizons":{{"1w":{{"delta_krw":0,"confidence":0.5}},"1m":{{"delta_krw":0,"confidence":0.5,"rationale":"한 문장"}},"3m":{{"delta_krw":0,"confidence":0.4}},"12m":{{"delta_krw":0,"confidence":0.3}}}},"signal":"krw_weak|neutral|krw_strong","confidence":0.5}}"""

GROUP_SYSTEM = """당신은 USD/KRW 위원회 {label} 그룹의 오케스트레이터입니다.
그룹 멤버들의 예측을 종합하되 내부 이견을 드러내세요.
JSON만 출력: {{"horizons":{{"1w":{{"delta_krw":0,"confidence":0.5}},"1m":{{"delta_krw":0,"confidence":0.5}},"3m":{{"delta_krw":0,"confidence":0.4}},"12m":{{"delta_krw":0,"confidence":0.3}}}},
"synthesis":"그룹 종합 견해 2~3문장(한국어)","key_debate":"그룹 내 핵심 쟁점 한 문장(없으면 빈 문자열)"}}"""

CHIEF_SYSTEM = """당신은 USD/KRW 예측 위원회의 수석(Chief) 오케스트레이터입니다.
학계/퍼블릭/프라이빗 3개 그룹의 종합과 시장 데이터를 협의·조정해 최종 예측을 냅니다.

최종 판단 시 아래 4개 이론 축을 각각 명시적으로 평가하고 종합하세요(도출 리포트에 축별 판단 포함):
① 경상수지·환류 구조 — 흑자 헤드라인이 아닌 실제 달러 환류로 평가(BOK 2026-15: 해외투자 +3%→환율 +0.7%,
   투자소득 +8%→-0.4%, 유보·재투자 시 공급효과 없음. 삼성·하이닉스 미국 재투자 계획=환류 제한,
   국내 메가 프로젝트=부분 상쇄)
② 이자율평가(UIP/캐리) — 한미 금리차와 그 기대 경로
③ 통화량·유동성 가설 — 상대적 통화공급·재정과 중기 통화가치
④ 수급·정책 — NDF·역외, 외국인 자금, 정부 정책 발표, 외환당국의 환율안정 의지·개입 강도
제공되는 '정량 앵커'(모멘텀·평균회귀·캐리 프록시)와 위원회 분포에서 크게 벗어날 때는 근거를 명시하세요.
신뢰도는 근거 강도를 솔직히 반영: 이론이 한 방향으로 정렬되고 위원회 합의도가 높으면 0.7~0.85,
방향은 서되 이견이 있으면 0.55~0.7, 이론 간 신호가 상충하면 0.3~0.45로 낮추세요(과신 금지).
JSON만 출력:
{"horizons":{"1w":{"delta_krw":0,"confidence":0.62,"signal":"krw_weak|neutral|krw_strong"},
 "1m":{"delta_krw":0,"confidence":0.58,"signal":"neutral"},"3m":{"delta_krw":0,"confidence":0.5,"signal":"neutral"},
 "12m":{"delta_krw":0,"confidence":0.4,"signal":"neutral"}},
"reconciliation":"3섹터 협의 결과와 조정 근거 3~4문장(한국어)",
"report_ko":"도출 리포트: 최종 판단 근거를 6~9문장 한국어로. 채택/기각한 그룹 의견 포함.",
"report_en":"Concise English derivation report (4-6 sentences).",
"change_justification":"직전 발표 대비 예측을 바꿨다면 그 이유 한 문장, 아니면 빈 문자열"}"""

# ── persistent state ─────────────────────────────────────────────────────────
S: dict[str, Any] = {
    "run_id": 0, "forecast": None, "forecasts": [],  # published history (newest first)
    "agents": [], "run": None, "eval": None, "hierarchy": None,
    "signal": None, "positions": [], "closed": [],
    "agent_err": {},  # name -> {sum_abs_err, n} for ranking (1w matured)
}
_running = False
_last_started: Optional[datetime] = None
COOLDOWN = int(os.getenv("CYCLE_COOLDOWN_SEC", "900"))


def load() -> None:
    global S
    try:
        with open(STORE, encoding="utf-8") as f:
            S.update(json.load(f))
        logger.info("state loaded: %d forecasts, run_id=%s", len(S.get("forecasts", [])), S.get("run_id"))
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning("state load failed: %s", e)


def save() -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(STORE, "w", encoding="utf-8") as f:
            json.dump(S, f, ensure_ascii=False)
    except Exception as e:
        logger.warning("state save failed: %s", e)


def is_running() -> bool:
    return _running


def _pj(text: str) -> dict:
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.S)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", t, flags=re.S)
        if m:
            return json.loads(m.group(0))
        raise


def _norm_h(h: dict) -> dict:
    out = {}
    for k in HORIZONS:
        v = (h or {}).get(k) or {}
        c = float(v.get("confidence", 0) or 0)
        if c > 1:
            c = c / 100.0
        out[k] = {"delta_krw": round(float(v.get("delta_krw", 0) or 0), 1),
                  "confidence": round(min(max(c, 0.0), 1.0), 2)}
        if v.get("rationale"):
            out[k]["rationale"] = str(v["rationale"])[:300]
    return out


def realized_vol_krw() -> Optional[float]:
    from . import quant
    closes = [r["c"] for r in quant.daily_history()[-22:]]
    if len(closes) < 8:
        return None
    diffs = [b - a for a, b in zip(closes, closes[1:])]
    try:
        return round(statistics.stdev(diffs), 3)
    except statistics.StatisticsError:
        return None


async def _agent_call(name: str, group: str, focus: str, brief: str) -> Optional[dict]:
    collector.emit(name, "analyzing (round 1)…", "info", category="agent")
    try:
        d = _pj(await call_claude(AGENT_SYSTEM.format(name=name, focus=focus), brief))
        hz = _norm_h(d.get("horizons"))
        conf = float(d.get("confidence", 0) or 0)
        conf = conf / 100 if conf > 1 else conf
        rec = {"agent_name": name, "group": group,
               "signal": str(d.get("signal", "neutral")),
               "delta_krw": hz["1m"]["delta_krw"],
               "confidence": round(min(max(conf, 0), 1), 2),
               "round": 1, "horizons": hz}
        note = (hz["1m"].get("rationale") or "")[:60]
        collector.emit(name, f"{rec['signal']} Δ{rec['delta_krw']:+.0f}원 conf {round(rec['confidence']*100)}% — {note}",
                       "ok", category="agent")
        return rec
    except ClaudeAuthError:
        raise
    except Exception as e:
        collector.emit(name, f"failed: {str(e)[:90]}", "error", category="agent")
        return None


async def _review_call(rec: dict, consensus: float, brief: str) -> dict:
    name = rec["agent_name"]
    collector.emit(name, "analyzing (round 2 · 합의 재검토)…", "info", category="agent")
    review = {"agent": name, "group": rec["group"],
              "before_delta": rec["delta_krw"], "after_delta": rec["delta_krw"], "revised": False}
    try:
        d = _pj(await call_claude(
            REVIEW_SYSTEM.format(name=name, consensus=consensus, mine=rec["delta_krw"]), brief))
        if d.get("revised"):
            hz = _norm_h(d.get("horizons"))
            rec.update({"horizons": hz, "delta_krw": hz["1m"]["delta_krw"],
                        "signal": str(d.get("signal", rec["signal"])), "round": 2, "revised": True})
            conf = float(d.get("confidence", rec["confidence"]) or 0)
            rec["confidence"] = round(min(max(conf / 100 if conf > 1 else conf, 0), 1), 2)
            review.update({"after_delta": rec["delta_krw"], "revised": True})
        collector.emit(name, f"{rec['signal']} Δ{rec['delta_krw']:+.0f}원 conf {round(rec['confidence']*100)}% — "
                             f"{'수정(R2)' if review['revised'] else '견해 고수(R2)'}", "ok", category="agent")
    except Exception as e:
        collector.emit(name, f"R2 실패: {str(e)[:80]}", "error", category="agent")
    return review


def _confidence_eval(agents: list[dict]) -> dict:
    total = len(agents)
    dist = {"krw_weak": 0, "neutral": 0, "krw_strong": 0}
    for a in agents:
        dist[a["signal"]] = dist.get(a["signal"], 0) + 1
    majority = max(dist, key=dist.get) if agents else "neutral"
    agree = dist.get(majority, 0) / total if total else 0
    mean_conf = sum(a["confidence"] for a in agents) / total if total else 0
    score = 0.5 * mean_conf + 0.5 * agree
    rating = "높음" if score >= 0.62 else "보통" if score >= 0.45 else "낮음"
    return {"rating": rating, "mean_confidence": round(mean_conf, 2),
            "agreement": round(agree, 2), "agree_count": dist.get(majority, 0),
            "total": total, "distribution": dist, "majority_signal": majority}


def _dir_bucket(d: float) -> int:
    """Direction bucket of a delta: +1 원화약세, -1 원화강세, 0 중립(±1원 이내)."""
    return 1 if d > 1 else -1 if d < -1 else 0


def _horizon_confidence(h: str, agents: list[dict], published_delta: float,
                        chief_conf: float, conf_cap: float) -> float:
    """증거 기반 신뢰도(0~conf_cap).

    단일 LLM의 자기보고 숫자(저앵커링) 대신, 위원회 23인의 **방향 합의도**와
    **앙상블 응집도**(예측 분산의 작음)를 실제 근거로 삼아 산출한다. 수석의
    자기보고 신뢰도는 사전확률(prior)로만 15% 반영한다. 위원회가 한 방향으로
    강하게 모이면 신뢰도가 정직하게 높아지고(예: 20/23 동의 → 0.8+), 12개월처럼
    이견이 크면 자연히 낮게 유지된다 — 인위적 부풀림이 아니라 합의의 정량화다.
    """
    deltas = [a["horizons"][h]["delta_krw"] for a in agents
              if (a.get("horizons") or {}).get(h) is not None]
    n = len(deltas)
    chief_conf = min(max(float(chief_conf or 0.0), 0.0), 1.0)
    if n < 3:
        return round(min(chief_conf, conf_cap, 0.85), 2)
    pub = _dir_bucket(published_delta)
    # ① 발표 방향에 동의하는 위원 비율 → 확신도(우연 수준 ~1/3에서 0, 만장일치에서 1)
    agree = sum(1 for d in deltas if _dir_bucket(d) == pub) / n
    agree_score = max(0.0, (agree - 0.34) / 0.66)
    # ② 앙상블 응집도: 예측 분산이 기간별 전형 스케일(√시간)보다 작을수록 확신↑
    disp = statistics.pstdev(deltas) if n > 1 else 0.0
    scale = 6.0 * (H_DAYS[h] / 30) ** 0.5
    tight = max(0.0, 1.0 - disp / scale) if scale else 0.0
    evidence = 0.60 * agree_score + 0.40 * tight
    conf = 0.30 + 0.55 * evidence + 0.15 * chief_conf
    return round(min(conf, conf_cap, 0.85), 2)


def _sector_agreement(groups: dict) -> dict:
    out = {}
    for h in HORIZONS:
        ds = [(groups[g]["horizons"].get(h) or {}).get("delta_krw", 0) for g in groups]
        signs = {1 if d > 1 else -1 if d < -1 else 0 for d in ds}
        out[h] = "aligned" if len(signs) == 1 else "split" if (1 in signs and -1 in signs) else "mixed"
    return out


def _make_signal(fc: dict, spot: float, adj: dict) -> dict:
    best_h, best = None, {"confidence": -1}
    for h in HORIZONS:
        x = fc["horizons"][h]
        if x["confidence"] > best["confidence"]:
            best_h, best = h, x
    conf = min(best["confidence"], adj.get("conf_cap", 0.85))
    now = datetime.now(timezone.utc).isoformat()
    if conf < CONF_FLOOR or abs(best["published_delta_krw"]) < 1.0:
        return {"side": "FLAT", "horizon": best_h, "spot_entry": spot, "target": None,
                "stop": None, "notional_usd": 0.0, "confidence": round(conf, 2),
                "expected_edge_krw": 0.0,
                "rationale": f"FLAT - best-horizon({best_h}) confidence {round(conf*100)}% < floor {round(CONF_FLOOR*100)}%"
                if conf < CONF_FLOOR else f"FLAT - expected edge {best['published_delta_krw']:+.1f}₩ too small",
                "status": "proposed", "created_at": now}
    delta = best["published_delta_krw"]
    side = "LONG" if delta > 0 else "SHORT"
    return {"side": side, "horizon": best_h, "spot_entry": spot,
            "target": round(spot + delta, 1),
            "stop": round(spot - 0.6 * delta, 1),
            "notional_usd": round(CASH_USD * min(conf, 0.75), 0),
            "confidence": round(conf, 2), "expected_edge_krw": round(abs(delta), 1),
            "rationale": f"{side} USD/KRW — {best_h} Δ{delta:+.1f}₩ conf {round(conf*100)}% ≥ floor {round(CONF_FLOOR*100)}%",
            "status": "proposed", "created_at": now}


def _update_broker(sig: dict, spot: float) -> None:
    """Paper broker: fill non-FLAT proposals; close on horizon expiry/target/stop."""
    now = datetime.now(timezone.utc)
    still = []
    for p in S["positions"]:
        d = 1 if p["side"] == "LONG" else -1
        pnl = (spot - p["entry"]) * d * p["notional_usd"] / p["entry"]
        expired = datetime.fromisoformat(p["opened"]) + timedelta(days=H_DAYS[p["horizon"]]) < now
        hit_tp = p.get("target") and ((spot - p["target"]) * d >= 0)
        hit_sl = p.get("stop") and ((spot - p["stop"]) * d <= 0)
        if expired or hit_tp or hit_sl:
            S["closed"].append({**p, "closed": now.isoformat(), "exit": spot,
                                "pnl_krw": round(pnl, 0), "won": pnl > 0,
                                "reason": "target" if hit_tp else "stop" if hit_sl else "expiry"})
            collector.emit("broker", f"포지션 청산({p['side']} {p['horizon']}): "
                                     f"{'익절' if hit_tp else '손절' if hit_sl else '만기'} P&L {pnl:+.0f}원",
                           "ok", category="orchestrator")
        else:
            still.append(p)
    S["positions"] = still
    if sig["side"] in ("LONG", "SHORT") and not any(p["horizon"] == sig["horizon"] for p in still):
        S["positions"].append({"side": sig["side"], "horizon": sig["horizon"],
                               "entry": spot, "target": sig["target"], "stop": sig["stop"],
                               "notional_usd": sig["notional_usd"], "confidence": sig["confidence"],
                               "opened": now.isoformat()})
        sig["status"] = "filled"


def broker_state(spot: Optional[float]) -> dict:
    upnl = 0.0
    if spot:
        for p in S["positions"]:
            d = 1 if p["side"] == "LONG" else -1
            upnl += (spot - p["entry"]) * d * p["notional_usd"] / p["entry"]
    return {"broker": "paper", "is_live": False, "cash_usd": CASH_USD,
            "open_positions": len(S["positions"]),
            "unrealized_pnl_krw": round(upnl, 0), "orders_count": len(S["closed"])}


def trading_stats() -> dict:
    cl = S["closed"]
    if not cl:
        return {"closed_trades": 0}
    pnls = [c["pnl_krw"] for c in cl]
    wins = [p for p in pnls if p > 0]
    losses = [-p for p in pnls if p < 0]
    cal: dict[str, dict] = {}
    for c in cl:
        b = c.get("confidence", 0)
        key = f"{int(b*20)/20:.2f}-{int(b*20)/20+0.10:.2f}"
        cal.setdefault(key, {"n": 0, "w": 0})
        cal[key]["n"] += 1
        cal[key]["w"] += 1 if c["won"] else 0
    try:
        sharpe = round(statistics.mean(pnls) / (statistics.stdev(pnls) or 1), 2) if len(pnls) > 1 else None
    except statistics.StatisticsError:
        sharpe = None
    return {"closed_trades": len(cl),
            "win_rate": round(len(wins) / len(cl), 2),
            "total_pnl_krw": round(sum(pnls), 0),
            "avg_pnl_pct": round(statistics.mean(p / CASH_USD * 100 for p in pnls), 3),
            "profit_factor": round(sum(wins) / sum(losses), 2) if losses else None,
            "sharpe_per_trade": sharpe,
            "best_krw": max(pnls), "worst_krw": min(pnls),
            "calibration": {k: {"n": v["n"], "win_rate": round(v["w"] / v["n"], 2)} for k, v in cal.items()}}


def accuracy_payload() -> dict:
    """Score matured published forecasts against realized daily closes."""
    from . import quant
    hist = {r["date"]: r["c"] for r in quant.daily_history()}
    days_sorted = sorted(hist)
    out_h, ranking_src, total = {}, {}, 0
    for h in HORIZONS:
        errs, hits = [], []
        for f in S["forecasts"]:
            x = f["horizons"].get(h)
            if not x:
                continue
            run_d = f["created_kst"][:10]
            tgt = (datetime.fromisoformat(run_d) + timedelta(days=H_DAYS[h])).date().isoformat()
            real = next((hist[d] for d in days_sorted if d >= tgt), None)
            if real is None:
                continue
            pred = x["spot_at_run"] + x["published_delta_krw"]
            errs.append(abs(pred - real))
            pd_ = x["published_delta_krw"]; rd = real - x["spot_at_run"]
            hits.append((pd_ > 0.5 and rd > 0) or (pd_ < -0.5 and rd < 0) or (abs(pd_) <= 0.5 and abs(rd) <= 3))
            if h == "1w":
                for a in f.get("agents_snapshot", []):
                    e = abs(a["delta"] - rd)
                    s = ranking_src.setdefault(a["name"], {"s": 0.0, "n": 0})
                    s["s"] += e; s["n"] += 1
        out_h[h] = {"samples": len(errs)}
        if errs:
            out_h[h].update({"directional_hit_rate": round(sum(hits) / len(hits), 3),
                             "mae_krw": round(statistics.mean(errs), 2)})
            total += len(errs)
    ranking = sorted(
        ({"agent_id": i + 1, "agent": n, "mae_krw": round(v["s"] / v["n"], 2), "n": v["n"]}
         for i, (n, v) in enumerate(ranking_src.items()) if v["n"]),
        key=lambda r: r["mae_krw"])
    return {"forecast": {"horizons": out_h, "agent_ranking": ranking[:20], "total_samples": total},
            "trading": trading_stats()}


async def run_cycle(cycle_type: str = "scheduled", force: bool = False) -> Optional[dict]:
    global _running, _last_started
    if _running:
        collector.emit("system", "사이클이 이미 진행 중 — 요청 무시", "info")
        return None
    if not force and _last_started and (datetime.now(timezone.utc) - _last_started).total_seconds() < COOLDOWN:
        collector.emit("system", "사이클 쿨다운 중 — 요청 무시", "info")
        return None
    _running = True
    _last_started = datetime.now(timezone.utc)
    try:
        return await _run_cycle_inner(cycle_type)
    finally:
        _running = False


async def _run_cycle_inner(cycle_type: str) -> Optional[dict]:
    from . import news as news_mod, quant
    collector.emit("orchestrator", f"사이클 시작 (type={cycle_type}, agents={len(ROSTER)}, 2-round)",
                   "info", category="orchestrator")
    snap = await collector.collect_latest() or collector.latest
    if not snap.get("rate"):
        collector.emit("system", "환율 데이터 없음 — 사이클 중단", "error")
        return None
    await collector.collect_context()
    quant.daily_history()
    ok, detail = await verify_auth()
    if not ok:
        collector.emit("system", f"클로드 인증 실패 — 사이클 중단: {detail[:120]}", "error")
        return None

    spot = float(snap["rate"])
    news_lines = await news_mod.headline_lines(8)
    ctx = "\n".join(f"- {c['label']}: {c.get('price')} ({c.get('change_pct','?')}%)"
                    for c in collector.context.values())
    chg = {r: collector.pct_change_over(r) for r in ("1d", "1w", "1mo", "1y")}
    from . import notes as notes_mod
    brief = (f"현재(KST {datetime.now(KST).strftime('%m-%d %H:%M')}) USD/KRW: {spot}원 "
             f"(전일比 {snap.get('change')}원/{snap.get('change_pct')}%)\n"
             f"변화율: 1일 {chg['1d']}% 1주 {chg['1w']}% 1개월 {chg['1mo']}% 1년 {chg['1y']}%\n"
             f"실현변동성(일별): {realized_vol_krw()}원\n지표:\n{ctx}\n뉴스:\n" + "\n".join(news_lines) +
             "\n\n" + notes_mod.context_block())

    # ── Round 1 ──
    agents: list[dict] = []
    for name, group, focus in ROSTER:
        r = await _agent_call(name, group, focus, brief)
        if r:
            agents.append(r)
    if not agents:
        collector.emit("system", "성공한 에이전트 없음 — 사이클 중단", "error")
        return None

    # ── Round 2: outlier coordination ──
    deltas = [a["delta_krw"] for a in agents]
    consensus = statistics.mean(deltas)
    spread = statistics.stdev(deltas) if len(deltas) > 1 else 0
    thr = max(6.0, 1.4 * spread)
    outliers = [a for a in agents if abs(a["delta_krw"] - consensus) > thr][:5]
    collector.emit("orchestrator",
                   f"라운드1 완료 {len(agents)}/{len(ROSTER)} · 1M 합의 {consensus:+.0f}원 · 이탈 {len(outliers)}명 재검토",
                   "info", category="orchestrator")
    reviews = []
    for a in outliers:
        reviews.append(await _review_call(a, consensus, brief +
                                          f"\n\n[위원회 1개월 합의: {consensus:+.0f}원 · 당신: {a['delta_krw']:+.0f}원]"))
    collaboration = {"consensus_1m": round(consensus, 1), "outlier_count": len(outliers),
                     "revised_count": sum(1 for r in reviews if r["revised"]), "reviews": reviews}

    # ── Group synthesis (3 orchestrators) ──
    groups_out: dict[str, dict] = {}
    for gkey in ("academic", "public", "private"):
        mem = [a for a in agents if a["group"] == gkey]
        collector.emit("orchestrator", f"{GROUP_LABEL[gkey]} 그룹 종합 중… ({len(mem)}명)",
                       "info", category="orchestrator")
        lines = [f"{a['agent_name']}: {a['signal']} " +
                 " ".join(f"{h}={a['horizons'][h]['delta_krw']:+.0f}₩({a['horizons'][h]['confidence']:.2f})"
                          for h in HORIZONS) +
                 f" — {a['horizons']['1m'].get('rationale','')}" for a in mem]
        try:
            g = _pj(await call_claude(GROUP_SYSTEM.format(label=GROUP_LABEL[gkey]),
                                      brief + "\n\n[그룹 멤버 의견]\n" + "\n".join(lines)))
            groups_out[gkey] = {"group": GROUP_LABEL[gkey], "horizons": _norm_h(g.get("horizons")),
                                "synthesis": str(g.get("synthesis", ""))[:600],
                                "key_debate": str(g.get("key_debate", ""))[:300],
                                "agents": [a["agent_name"] for a in mem]}
        except Exception as e:
            collector.emit("orchestrator", f"{gkey} 종합 실패: {str(e)[:80]}", "error", category="orchestrator")
            avg = {h: {"delta_krw": round(statistics.mean(a["horizons"][h]["delta_krw"] for a in mem), 1),
                       "confidence": round(statistics.mean(a["horizons"][h]["confidence"] for a in mem), 2)}
                   for h in HORIZONS} if mem else {}
            groups_out[gkey] = {"group": GROUP_LABEL[gkey], "horizons": avg,
                                "synthesis": "(정량 평균 사용 — 종합 호출 실패)", "key_debate": "",
                                "agents": [a["agent_name"] for a in mem]}

    # ── Chief reconciliation ──
    collector.emit("Chief", "수석 종합·도출 리포트 작성 중… (3섹터 협의)", "info", category="orchestrator")
    prev = S.get("forecast")
    prev_line = ""
    if prev:
        prev_line = "\n직전 발표: " + " ".join(
            f"{h}={prev['horizons'][h]['published_delta_krw']:+.0f}₩" for h in HORIZONS)
    ginput = "\n\n".join(
        f"[{v['group']}] " + " ".join(f"{h}={v['horizons'].get(h,{}).get('delta_krw',0):+.0f}₩" for h in HORIZONS) +
        f"\n종합: {v['synthesis']}\n쟁점: {v['key_debate']}" for v in groups_out.values())
    ev = _confidence_eval(agents)
    anchors = quant.theory_anchors()
    anchor_line = "\n정량 앵커(참고): " + " · ".join(
        f"{h}: 모멘텀 {a['momentum_mr']:+.0f}₩ / 250일회귀 {a['meanrev_250d']:+.0f}₩"
        for h, a in anchors.items()) if anchors else ""
    try:
        chief = _pj(await call_claude(CHIEF_SYSTEM, brief + "\n\n" + ginput + prev_line + anchor_line +
                                      f"\n위원회 합의도 {ev['agreement']:.0%}, 평균신뢰도 {ev['mean_confidence']:.0%}",
                                      timeout=300))
    except Exception as e:
        collector.emit("Chief", f"수석 종합 실패 — 정량 앵커 사용: {str(e)[:80]}", "error", category="orchestrator")
        chief = {"horizons": {h: {"delta_krw": consensus * (H_DAYS[h] / 30) ** 0.5,
                                  "confidence": 0.2, "signal": "neutral"} for h in HORIZONS},
                 "reconciliation": "(수석 종합 실패 — 정량 앵커 사용)",
                 "report_ko": "(리포트 생성 실패)", "report_en": ""}

    adj = quant.adjustment()
    chz = _norm_h(chief.get("horizons"))
    horizons = {}
    today_kst = datetime.now(KST).date()

    def _trimmed_mean(vals: list[float]) -> Optional[float]:
        if not vals:
            return None
        s = sorted(vals)
        k = max(0, len(s) // 10)
        core = s[k: len(s) - k] or s
        return statistics.mean(core)

    for h in HORIZONS:
        # 앙상블 축소(shrinkage): 수석 판단을 위원회 절사평균·정량 앵커와 블렌딩해
        # 점예측 오차를 줄인다 (수석 55% · 위원회 30% · 정량 앵커 15%).
        chief_d = chz[h]["delta_krw"]
        comm_d = _trimmed_mean([a["horizons"][h]["delta_krw"] for a in agents])
        anch_d = (anchors.get(h) or {}).get("mean")
        blended = chief_d
        if comm_d is not None and anch_d is not None:
            blended = 0.55 * chief_d + 0.30 * comm_d + 0.15 * anch_d
        elif comm_d is not None:
            blended = 0.65 * chief_d + 0.35 * comm_d
        raw = blended * adj.get("scale", 1.0) + adj.get("bias_krw", 0.0)
        if h == "1m":
            collector.emit("orchestrator",
                           f"앙상블 블렌딩(1M): 수석 {chief_d:+.1f} · 위원회 {comm_d:+.1f} · "
                           f"앵커 {anch_d if anch_d is not None else '—'} → 발표 {raw:+.1f}₩",
                           "info", category="orchestrator")
        conf = _horizon_confidence(h, agents, raw, chz[h].get("confidence", 0.0),
                                   adj.get("conf_cap", 0.85))
        sig = (chief.get("horizons", {}).get(h) or {}).get("signal") or \
              ("krw_weak" if raw > 1 else "krw_strong" if raw < -1 else "neutral")
        if h == "1m":
            _ags = [a["horizons"][h]["delta_krw"] for a in agents
                    if (a.get("horizons") or {}).get(h) is not None]
            _agree = (sum(1 for d in _ags if _dir_bucket(d) == _dir_bucket(raw)) / len(_ags)) if _ags else 0
            collector.emit("orchestrator",
                           f"신뢰도(1M): 위원회 방향합의 {_agree:.0%} · 수석 {chz[h].get('confidence',0):.0%} "
                           f"→ 발표 신뢰도 {conf:.0%}", "info", category="orchestrator")
        prev_h = (prev or {}).get("horizons", {}).get(h, {})
        streak = prev_h.get("unchanged_streak_days", 0) + 1 \
            if prev and abs(prev_h.get("published_delta_krw", 1e9) - raw) < 0.5 else 1
        horizons[h] = {"published_delta_krw": round(raw, 1),
                       "implied_rate": round(spot + raw, 2),
                       "confidence": round(conf, 2), "signal": sig,
                       "unchanged_streak_days": streak, "spot_at_run": spot,
                       "target_date": (today_kst + timedelta(days=H_DAYS[h])).isoformat(),
                       "change_justification": (str(chief.get("change_justification") or "")[:200] or None)
                       if h == "1m" else None}

    S["run_id"] = int(S.get("run_id", 0)) + 1
    fc = {"horizons": horizons,
          "report_ko": str(chief.get("report_ko", ""))[:5000],
          "report_en": str(chief.get("report_en", ""))[:4000],
          "created_kst": datetime.now(KST).isoformat(), "spot": spot}
    S["forecast"] = fc
    S["forecasts"].insert(0, {"created_kst": fc["created_kst"], "horizons": horizons,
                              "agents_snapshot": [{"name": a["agent_name"],
                                                   "delta": a["horizons"]["1w"]["delta_krw"]} for a in agents]})
    del S["forecasts"][500:]
    S["agents"] = agents
    S["run"] = {"id": S["run_id"], "cycle_type": cycle_type, "spot_at_run": spot,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "collaboration_rounds": 2 if outliers else 1}
    S["eval"] = ev
    S["hierarchy"] = {
        "academic": groups_out["academic"], "public": groups_out["public"], "private": groups_out["private"],
        "chief": {"reconciliation": str(chief.get("reconciliation", ""))[:800],
                  "horizons": {h: {"delta_krw": horizons[h]["published_delta_krw"],
                                   "confidence": horizons[h]["confidence"]} for h in HORIZONS}},
        "members": {g: [{"name": a["agent_name"], "delta_1m": a["delta_krw"], "signal": a["signal"],
                         "conf": a["confidence"], "revised": bool(a.get("revised"))}
                        for a in agents if a["group"] == g] for g in ("academic", "public", "private")},
        "collaboration": collaboration,
        "sector_agreement": _sector_agreement(groups_out),
        "spot": spot,
    }
    sig = _make_signal(fc, spot, adj)
    _update_broker(sig, spot)
    S["signal"] = sig
    save()
    one = horizons["1m"]
    collector.emit("Chief", f"도출 완료 · 1M {one['published_delta_krw']:+.1f}원({one['signal']}, "
                            f"conf {round(one['confidence']*100)}%) · 신호 {sig['side']}", "ok",
                   category="orchestrator")
    return fc
