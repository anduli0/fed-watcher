"""
23-agent hierarchical USD/KRW forecast committee (학계 → 섹터 → 수석), the
web port of the owner's PC krw-watcher. Every agent is one `claude -p` call on
the owner's Claude subscription; the Chief synthesizes horizon forecasts
(1w/1m/3m/12m Δ₩), today's high/low/close, and a KO/EN derivation report.
Forecasts persist to JSON so accuracy can be scored as days pass.
"""
import asyncio
import json
import logging
import os
import re
import statistics
from datetime import datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from . import collector
from .claude_cli import call_claude, verify_auth, ClaudeAuthError

logger = logging.getLogger("krw_watcher.agents")
KST = ZoneInfo("Asia/Seoul")

DATA_DIR = os.getenv("DATA_DIR", "/app/data")
FORECAST_STORE = os.path.join(DATA_DIR, "forecasts.json")
MAX_FORECASTS = 400

HORIZONS = ("1w", "1m", "3m", "12m")

# ── The committee (23 agents: 3 학계 + 19 섹터 + Consensus; Chief synthesizes) ──
ROSTER: list[tuple[str, str, str]] = [
    # (name, tier, focus)
    ("Academic_FX",        "학계", "환율결정이론(구매력평가, 금리평가, 자산접근법) 관점의 USD/KRW 적정 수준"),
    ("Academic_Macro",     "학계", "거시경제 학술 문헌 관점의 달러/원 사이클과 구조적 추세"),
    ("Academic_TimeSeries","학계", "시계열·모멘텀·평균회귀 통계 관점의 단기 경로"),
    ("Intl_Bodies",        "섹터", "IMF/BIS/OECD 등 국제기구 시각의 원화 밸류에이션과 자본흐름"),
    ("Macro_US",           "섹터", "미국 성장/물가/고용 지표와 달러 방향"),
    ("Macro_KR",           "섹터", "한국 성장/물가/수출입 지표와 원화 펀더멘털"),
    ("Monetary_Fed",       "섹터", "연준 통화정책 경로(점도표, QT, 발언)와 달러"),
    ("Monetary_BoK",       "섹터", "한국은행 기준금리 경로와 원화"),
    ("Monetary_BoP",       "섹터", "국제수지(경상/자본수지), 외환보유액, 대외건전성"),
    ("Rates_Differential", "섹터", "한미 금리차와 내외금리차 기반 환율 압력"),
    ("DXY_Majors",         "섹터", "달러인덱스(DXY)와 주요통화(EUR/JPY) 흐름의 파급"),
    ("CNY_Asia_EM",        "섹터", "위안화·아시아 통화·신흥국 리스크와 원화 동조성"),
    ("JPY_Carry",          "섹터", "엔캐리·엔/달러 변동이 원화에 주는 파급"),
    ("Equity_Kospi_Flows", "섹터", "코스피 외국인 수급과 주식자금 유출입"),
    ("Bond_Flows",         "섹터", "채권자금 유출입과 WGBI 등 지수 편입 효과"),
    ("Trade_Balance",      "섹터", "무역수지, 반도체 수출 사이클, 조선/자동차 수주"),
    ("Energy_Commodities", "섹터", "유가/원자재 가격과 수입물가 경로"),
    ("Politics_Geopol",    "섹터", "지정학(북한, 미중, 중동)과 국내 정치 리스크"),
    ("Policy_Intervention","섹터", "외환당국 개입 가능성, 구두개입, 스무딩오퍼레이션"),
    ("Positioning_Sentiment","섹터","투기적 포지셔닝, 역외 NDF 수급, 시장 심리"),
    ("Market_Linkage",     "섹터", "미 국채금리·주가·크레딧 등 자산시장 연계 신호"),
    ("News_Media",         "섹터", "최근 뉴스 헤드라인 톤과 이벤트 리스크"),
    ("Consensus",          "섹터", "시장 컨센서스(투자은행 전망, 선물환 내재 경로) 대비 괴리"),
]

AGENT_SYSTEM = """당신은 USD/KRW(원/달러) 환율 전문 분석 에이전트 '{name}'입니다.
전문 분야: {focus}
주어진 시장 데이터를 당신의 전문 분야 관점에서만 평가하세요. 과장 금지.

반드시 아래 JSON만 출력(코드펜스 금지):
{{
  "stance": "krw_strong" | "neutral" | "krw_weak",
  "delta_1w": 숫자(1주 후 예상 변화, 원, 원화강세=음수),
  "delta_1m": 숫자, "delta_3m": 숫자, "delta_12m": 숫자,
  "confidence": 0~100 정수,
  "note": "핵심 근거 한 문장(한국어)"
}}"""

CHIEF_SYSTEM = """당신은 USD/KRW 예측 위원회의 수석(Chief) 애널리스트입니다.
23명의 전문 에이전트 의견(학계/섹터)과 시장 데이터를 계층적으로 종합해
최종 호라이즌 예측과 도출 리포트를 작성합니다. 에이전트 간 상충은 근거의
질로 조정하고, 신뢰도는 의견 일치도와 데이터 질을 반영하세요.

반드시 아래 JSON만 출력(코드펜스 금지):
{
  "horizons": {
    "1w":  {"delta_krw": 숫자, "confidence": 0~100, "signal": "krw_strong|neutral|krw_weak"},
    "1m":  {"delta_krw": 숫자, "confidence": 0~100, "signal": "..."},
    "3m":  {"delta_krw": 숫자, "confidence": 0~100, "signal": "..."},
    "12m": {"delta_krw": 숫자, "confidence": 0~100, "signal": "..."}
  },
  "today": {"high": 숫자, "low": 숫자, "close": 숫자},
  "headline": "한 줄 요약(한국어, 40자 이내)",
  "report_ko": "도출 리포트: 종합 판단의 근거를 5~8문장 한국어로. 어떤 에이전트 의견을 채택/기각했는지 포함.",
  "report_en": "The same derivation report in concise English (3-5 sentences)."
}"""

# ── state ────────────────────────────────────────────────────────────────────
forecasts: list[dict] = []          # newest first
agent_states: dict[str, dict] = {}  # name -> {tier, status, note, stance, updated}
_cycle_running = False
_last_cycle_started: Optional[datetime] = None
COOLDOWN_SEC = int(os.getenv("CYCLE_COOLDOWN_SEC", "900"))


def _ensure_dir() -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except OSError:
        pass


def load() -> None:
    global forecasts
    try:
        with open(FORECAST_STORE, encoding="utf-8") as f:
            forecasts = json.load(f)[:MAX_FORECASTS]
        logger.info("loaded %d stored forecasts", len(forecasts))
    except FileNotFoundError:
        forecasts = []
    except Exception as e:
        logger.warning("could not load %s: %s", FORECAST_STORE, e)
        forecasts = []
    for name, tier, _ in ROSTER:
        agent_states.setdefault(name, {"tier": tier, "status": "idle"})


def _save() -> None:
    _ensure_dir()
    try:
        with open(FORECAST_STORE, "w", encoding="utf-8") as f:
            json.dump(forecasts[:MAX_FORECASTS], f, ensure_ascii=False)
    except Exception as e:
        logger.warning("could not save forecasts: %s", e)


def latest_forecast() -> Optional[dict]:
    return forecasts[0] if forecasts else None


def is_running() -> bool:
    return _cycle_running


def realized_vol_krw() -> Optional[float]:
    """Stdev of daily ₩ changes over the cached 1mo series."""
    pts = [p[1] for p in (collector._charts.get("1mo") or {}).get("points", [])]
    if len(pts) < 8:
        return None
    diffs = [b - a for a, b in zip(pts, pts[1:])]
    try:
        return round(statistics.stdev(diffs), 3)
    except statistics.StatisticsError:
        return None


def _parse_json(text: str) -> dict:
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.S)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", t, flags=re.S)
        if m:
            return json.loads(m.group(0))
        raise


def _market_brief(news_lines: list[str]) -> str:
    snap = collector.latest or {}
    ctx = collector.context or {}
    chg = {r: collector.pct_change_over(r) for r in ("1d", "1w", "1mo", "1y")}
    ctx_lines = [
        f"- {c['label']}: {c.get('price')} ({c.get('change_pct', '?')}%)"
        for c in ctx.values()
    ]
    now_kst = datetime.now(KST)
    return f"""현재 시각(KST): {now_kst.strftime('%Y-%m-%d %H:%M')}
USD/KRW 현물: {snap.get('rate')}원 (전일比 {snap.get('change')}원 / {snap.get('change_pct')}%)
기간 변화율: 1일 {chg.get('1d')}%, 1주 {chg.get('1w')}%, 1개월 {chg.get('1mo')}%, 1년 {chg.get('1y')}%
실현변동성(일별Δ 표준편차, 1개월): {realized_vol_krw()}원
주변 지표:
{chr(10).join(ctx_lines) if ctx_lines else '- (수집 실패)'}
주요 뉴스 헤드라인:
{chr(10).join(news_lines[:8]) if news_lines else '- (없음)'}"""


async def _run_agent(name: str, tier: str, focus: str, brief: str) -> Optional[dict]:
    agent_states[name] = {"tier": tier, "status": "analyzing",
                          "updated": datetime.now(timezone.utc).isoformat()}
    collector.emit(name, "analyzing (round 1)…", "info")
    try:
        raw = await call_claude(AGENT_SYSTEM.format(name=name, focus=focus), brief)
        d = _parse_json(raw)
        out = {
            "name": name, "tier": tier,
            "stance": str(d.get("stance", "neutral")),
            "deltas": {h: float(d.get(f"delta_{h}", 0) or 0) for h in HORIZONS},
            "confidence": int(d.get("confidence", 0) or 0),
            "note": str(d.get("note", ""))[:200],
        }
        agent_states[name] = {"tier": tier, "status": "ok", "stance": out["stance"],
                              "note": out["note"], "confidence": out["confidence"],
                              "updated": datetime.now(timezone.utc).isoformat()}
        collector.emit(name, f"{out['stance']} · {out['note'][:70]}", "ok")
        return out
    except ClaudeAuthError:
        agent_states[name] = {"tier": tier, "status": "error", "note": "auth"}
        raise
    except Exception as e:
        agent_states[name] = {"tier": tier, "status": "error", "note": str(e)[:120],
                              "updated": datetime.now(timezone.utc).isoformat()}
        collector.emit(name, f"failed: {str(e)[:100]}", "error")
        return None


async def run_cycle(trigger: str = "scheduled", force: bool = False) -> Optional[dict]:
    """Full committee cycle → forecast record. Serialized agents (free tier)."""
    global _cycle_running, _last_cycle_started
    if _cycle_running:
        collector.emit("system", "사이클이 이미 진행 중 — 요청 무시", "info")
        return None
    if not force and _last_cycle_started and \
            (datetime.now(timezone.utc) - _last_cycle_started).total_seconds() < COOLDOWN_SEC:
        collector.emit("system", "사이클 쿨다운 중 — 요청 무시", "info")
        return None

    _cycle_running = True
    _last_cycle_started = datetime.now(timezone.utc)
    try:
        collector.emit("system", f"예측 사이클 시작 (trigger={trigger}, agents={len(ROSTER)})", "info")

        snap = await collector.collect_latest() or collector.latest
        if not snap or not snap.get("rate"):
            collector.emit("system", "환율 데이터 없음 — 사이클 중단", "error")
            return None
        await collector.collect_context()
        for rng in ("1w", "1mo", "1y"):
            await collector.get_chart(rng)

        ok, detail = await verify_auth()
        if not ok:
            collector.emit("system",
                           f"클로드 인증 실패 — 사이클 중단: {detail[:120]}", "error")
            return None

        from . import news as news_mod
        news_lines = await news_mod.headline_lines()
        brief = _market_brief(news_lines)
        spot = float(snap["rate"])

        results: list[dict] = []
        for name, tier, focus in ROSTER:
            r = await _run_agent(name, tier, focus, brief)
            if r:
                results.append(r)
        collector.emit("system",
                       f"에이전트 완료: {len(results)}/{len(ROSTER)} — Chief 종합 시작", "info")

        if not results:
            collector.emit("system", "성공한 에이전트가 없어 사이클 중단", "error")
            return None

        agent_lines = [
            f"[{r['tier']}] {r['name']}: {r['stance']}, Δ₩ 1w={r['deltas']['1w']}, "
            f"1m={r['deltas']['1m']}, 3m={r['deltas']['3m']}, 12m={r['deltas']['12m']}, "
            f"conf={r['confidence']} — {r['note']}"
            for r in results
        ]
        chief_input = brief + "\n\n=== 에이전트 의견 (23인 위원회) ===\n" + "\n".join(agent_lines)
        collector.emit("Chief", "계층형 종합 및 도출 리포트 작성 중…", "info")
        raw = await call_claude(CHIEF_SYSTEM, chief_input, timeout=300)
        chief = _parse_json(raw)

        horizons = {}
        prev = latest_forecast()
        for h in HORIZONS:
            hd = (chief.get("horizons") or {}).get(h) or {}
            delta = float(hd.get("delta_krw", 0) or 0)
            prev_h = ((prev or {}).get("horizons") or {}).get(h) or {}
            streak = int(prev_h.get("unchanged_streak_days", 0)) + 1 \
                if prev and abs(float(prev_h.get("published_delta_krw", 1e9)) - delta) < 0.5 else 1
            horizons[h] = {
                "published_delta_krw": round(delta, 1),
                "implied_rate": round(spot + delta, 2),
                "confidence": int(hd.get("confidence", 0) or 0),
                "signal": str(hd.get("signal", "neutral")),
                "unchanged_streak_days": streak,
                "spot_at_run": spot,
                "target_date": datetime.now(KST).date().isoformat(),
            }

        record = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_kst": datetime.now(KST).isoformat(),
            "trigger": trigger,
            "spot": spot,
            "horizons": horizons,
            "today": chief.get("today") or {},
            "headline": str(chief.get("headline", ""))[:120],
            "report_ko": str(chief.get("report_ko", ""))[:4000],
            "report_en": str(chief.get("report_en", ""))[:3000],
            "agents_ok": len(results),
            "agents_total": len(ROSTER),
            "agent_summary": [
                {"name": r["name"], "tier": r["tier"], "stance": r["stance"],
                 "confidence": r["confidence"], "note": r["note"]}
                for r in results
            ],
        }
        forecasts.insert(0, record)
        del forecasts[MAX_FORECASTS:]
        _save()
        collector.emit("Chief",
                       f"사이클 완료: {record['headline'] or '(제목 없음)'} "
                       f"(1w {horizons['1w']['published_delta_krw']:+.1f}₩)", "ok")
        return record
    except ClaudeAuthError as e:
        collector.emit("system", f"클로드 인증 오류: {str(e)[:150]}", "error")
        return None
    except Exception as e:
        collector.emit("system", f"사이클 실패: {str(e)[:200]}", "error")
        logger.exception("cycle failed")
        return None
    finally:
        _cycle_running = False


# ── accuracy & paper trading (derived from stored forecasts) ─────────────────
_H_DAYS = {"1w": 7, "1m": 30, "3m": 91, "12m": 365}


def accuracy_report() -> dict:
    """Score past 1w forecasts whose target period has elapsed against the
    current/known spot path (uses the 1y daily chart as the realized series)."""
    pts = (collector._charts.get("1y") or {}).get("points") or []
    daily = sorted(
        (datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat(), c)
        for t, c in pts
    )
    rows, hit = [], 0
    for f in reversed(forecasts):  # oldest first
        h = (f.get("horizons") or {}).get("1w")
        if not h:
            continue
        try:
            run_date = datetime.fromisoformat(f["created_at"]).date()
        except Exception:
            continue
        target_day = datetime.fromordinal(run_date.toordinal() + 7).date().isoformat()
        target = next((c for d, c in daily if d >= target_day), None)
        if target is None:
            continue
        pred_dir = 1 if h["published_delta_krw"] > 0.5 else (-1 if h["published_delta_krw"] < -0.5 else 0)
        real_delta = target - h["spot_at_run"]
        real_dir = 1 if real_delta > 0.5 else (-1 if real_delta < -0.5 else 0)
        ok = pred_dir == real_dir
        hit += 1 if ok else 0
        rows.append({"date": f["created_kst"][:10], "pred_delta": h["published_delta_krw"],
                     "real_delta": round(real_delta, 1), "hit": ok})
    return {"scored": len(rows), "hits": hit,
            "hit_rate": round(hit / len(rows) * 100, 1) if rows else None,
            "rows": rows[-30:]}


def paper_book(spot: Optional[float]) -> dict:
    """Lean paper broker: each cycle's 1w signal opens a notional 1-unit
    position at spot_at_run; mark-to-market against the current spot."""
    if spot is None:
        spot = (collector.latest or {}).get("rate")
    positions, pnl = [], 0.0
    for f in forecasts[:20]:
        h = (f.get("horizons") or {}).get("1w") or {}
        sig = h.get("signal")
        if sig not in ("krw_weak", "krw_strong") or not spot:
            continue
        direction = 1 if sig == "krw_weak" else -1  # long USD if 원화약세
        entry = h.get("spot_at_run")
        if not entry:
            continue
        p = round((spot - entry) * direction, 2)
        pnl += p
        positions.append({"opened": f["created_kst"][:16], "side": "USD롱" if direction == 1 else "USD숏",
                          "entry": entry, "mark": spot, "pnl_krw": p,
                          "confidence": h.get("confidence")})
    return {"broker": "paper", "live_trading": False,
            "open_positions": positions[:10], "mtm_pnl_krw": round(pnl, 2)}
