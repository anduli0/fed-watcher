"""
Claude-powered USD/KRW analysis: a Korean market briefing plus a short-term
outlook, generated on a schedule (and on demand) via the owner's Claude
subscription. Records persist to a JSON file so restarts keep history.
"""
import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

from . import collector
from .claude_cli import call_claude, verify_auth, ClaudeAuthError

logger = logging.getLogger("krw_watcher.analyst")

KST = ZoneInfo("Asia/Seoul")
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
STORE = os.path.join(DATA_DIR, "analyses.json")
MAX_RECORDS = 60
COOLDOWN_SEC = int(os.getenv("ANALYSIS_COOLDOWN_SEC", "600"))

analyses: list[dict] = []
_running = False
_last_started: Optional[datetime] = None

SYSTEM_PROMPT = """당신은 원/달러 환율 전문 애널리스트입니다.
주어진 시장 데이터만 근거로 간결하고 실용적인 한국어 브리핑을 작성합니다.
과장하지 말고, 데이터가 부족한 부분은 부족하다고 명시하세요.

반드시 아래 JSON 형식으로만 답하세요(코드펜스, 다른 텍스트 금지):
{
  "headline": "한 줄 헤드라인 (40자 이내)",
  "commentary": "3~5문장의 시장 해설. 최근 흐름의 원인과 맥락.",
  "drivers": ["핵심 동인 1", "핵심 동인 2", "핵심 동인 3"],
  "outlook": {
    "direction": "상승" | "하락" | "중립",
    "range_low": 숫자(1주 예상 하단, 원),
    "range_high": 숫자(1주 예상 상단, 원),
    "confidence": 0~100 정수,
    "rationale": "전망 근거 1~2문장"
  }
}"""


def _ensure_dir() -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except OSError:
        pass


def load() -> None:
    global analyses
    try:
        with open(STORE, encoding="utf-8") as f:
            analyses = json.load(f)[:MAX_RECORDS]
        logger.info("loaded %d stored analyses", len(analyses))
    except FileNotFoundError:
        analyses = []
    except Exception as e:
        logger.warning("could not load %s: %s", STORE, e)
        analyses = []


def _save() -> None:
    _ensure_dir()
    try:
        with open(STORE, "w", encoding="utf-8") as f:
            json.dump(analyses[:MAX_RECORDS], f, ensure_ascii=False)
    except Exception as e:
        logger.warning("could not save %s: %s", STORE, e)


def latest_analysis() -> Optional[dict]:
    return analyses[0] if analyses else None


def hours_since_last() -> Optional[float]:
    rec = latest_analysis()
    if not rec:
        return None
    try:
        ts = datetime.fromisoformat(rec["created_at"])
        return (datetime.now(timezone.utc) - ts).total_seconds() / 3600
    except Exception:
        return None


def _parse_json(text: str) -> dict:
    """Parse the model's JSON, tolerating code fences / stray prose."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", t, flags=re.S)
        if m:
            return json.loads(m.group(0))
        raise


async def run_analysis(trigger: str = "scheduled", force: bool = False) -> Optional[dict]:
    """Collect fresh data, ask Claude for a briefing, store + return it."""
    global _running, _last_started
    if _running:
        collector.emit("analyst", "이미 분석이 진행 중 — 요청 무시", "info")
        return None
    if not force and _last_started and \
            (datetime.now(timezone.utc) - _last_started).total_seconds() < COOLDOWN_SEC:
        collector.emit("analyst", "쿨다운 중 — 요청 무시", "info")
        return None

    _running = True
    _last_started = datetime.now(timezone.utc)
    try:
        collector.emit("analyst", f"AI 분석 시작 (trigger={trigger})", "info")

        # Fresh inputs (rate is required; the rest is best-effort)
        snap = await collector.collect_latest()
        if not snap:
            snap = collector.latest
        if not snap or not snap.get("rate"):
            collector.emit("analyst", "환율 데이터가 없어 분석 중단", "error")
            return None
        await collector.collect_context()
        for rng in ("1w", "1mo", "1y"):
            await collector.get_chart(rng)

        ok, detail = await verify_auth()
        if not ok:
            collector.emit("analyst", f"클로드 인증 실패로 분석 중단: {detail[:120]}", "error")
            logger.error(
                "Claude CLI auth failed: %s\n  → Fix: set CLAUDE_CODE_OAUTH_TOKEN "
                "(run `claude setup-token` locally) in the deployment env.", detail)
            return None

        now_kst = datetime.now(KST)
        ctx_lines = [
            f"- {c['label']}: {c['price']} ({c['change_pct']:+.2f}%)" if c.get("change_pct") is not None
            else f"- {c['label']}: {c['price']}"
            for c in collector.context.values()
        ]
        chg = {r: collector.pct_change_over(r) for r in ("1d", "1w", "1mo", "1y")}
        prev_line = ""
        prev = latest_analysis()
        if prev:
            po = prev.get("outlook", {})
            prev_line = (f"\n직전 분석({prev.get('created_kst','')[:16]}): "
                         f"{po.get('direction','?')} / 범위 {po.get('range_low','?')}~{po.get('range_high','?')}원")

        user_msg = f"""현재 시각(KST): {now_kst.strftime('%Y-%m-%d %H:%M')}
원/달러 환율: {snap['rate']}원 (전일 대비 {snap.get('change') if snap.get('change') is not None else '?'}원, {snap.get('change_pct') if snap.get('change_pct') is not None else '?'}%)
데이터 소스: {snap.get('source')}

기간별 변화율: 1일 {chg.get('1d')}%, 1주 {chg.get('1w')}%, 1개월 {chg.get('1mo')}%, 1년 {chg.get('1y')}%

주변 지표:
{chr(10).join(ctx_lines) if ctx_lines else '- (수집 실패)'}
{prev_line}

위 데이터를 바탕으로 지정된 JSON 형식의 브리핑을 작성하세요."""

        raw = await call_claude(SYSTEM_PROMPT, user_msg)
        parsed = _parse_json(raw)

        record = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_kst": now_kst.isoformat(),
            "trigger": trigger,
            "rate": snap["rate"],
            "headline": str(parsed.get("headline", ""))[:120],
            "commentary": str(parsed.get("commentary", ""))[:2000],
            "drivers": [str(d)[:120] for d in (parsed.get("drivers") or [])][:5],
            "outlook": parsed.get("outlook") or {},
        }
        analyses.insert(0, record)
        del analyses[MAX_RECORDS:]
        _save()
        collector.emit("analyst",
                       f"AI 분석 완료: {record['headline'] or '(제목 없음)'}", "ok")
        return record
    except ClaudeAuthError as e:
        collector.emit("analyst", f"클로드 인증 오류: {str(e)[:150]}", "error")
        return None
    except Exception as e:
        collector.emit("analyst", f"분석 실패: {str(e)[:200]}", "error")
        logger.exception("analysis failed")
        return None
    finally:
        _running = False


def is_running() -> bool:
    return _running
