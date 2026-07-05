"""데일리 브리프 — 원본 계약({brief:{date,title,headline,forecast_summary,
analysis,news_digest,trading_view,risks,sources,fc_lines}}) 그대로. 생성 시
텔레그램 전송(TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID 설정 시)."""
import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

import httpx

from . import collector, engine
from .claude_cli import call_claude

logger = logging.getLogger("krw_watcher.briefing")
KST = ZoneInfo("Asia/Seoul")
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
STORE = os.path.join(DATA_DIR, "briefs.json")
HZ_KO = {"1w": "1주", "1m": "1개월", "3m": "3개월", "12m": "1년"}

briefs: dict[str, dict] = {}

SYSTEM = """당신은 원/달러 데일리 브리프 작성자입니다. 위원회 예측·시장 데이터·뉴스·구조 노트를 종합해
전문적이고 간결한 한국어 브리프를 씁니다.
analysis는 자금이동 서술에 치우치지 말고 4개 이론 축을 균형 있게 다루세요(각 1~2문장):
① 경상수지·환류 구조 — 흑자 헤드라인이 아닌 실제 달러 환류로 평가(BOK 2026-15; 삼성·하이닉스
   미국 재투자=환류 제한, 국내 메가 프로젝트=부분 상쇄) ② 이자율평가(한미 금리차·캐리)
③ 통화량·유동성 ④ 수급·포지셔닝(개입·역외·외국인 자금). JSON만 출력:
{"analysis":"이론 축별 균형 분석 5~8문장","news_digest":["핵심 뉴스 종합 3~5개(각 한 문장)"],
"trading_view":"트레이딩 함의 1~2문장","risks":["리스크 2~3개"]}"""


def load() -> None:
    global briefs
    try:
        with open(STORE, encoding="utf-8") as f:
            briefs = json.load(f)
    except FileNotFoundError:
        briefs = {}
    except Exception as e:
        logger.warning("briefs load failed: %s", e)


def _save() -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(STORE, "w", encoding="utf-8") as f:
            json.dump(briefs, f, ensure_ascii=False)
    except Exception as e:
        logger.warning("briefs save failed: %s", e)


def get(date: Optional[str] = None) -> Optional[dict]:
    if date:
        return briefs.get(date)
    if not briefs:
        return None
    return briefs[max(briefs)]


def list_items() -> list[dict]:
    return [{"date": d, "title": b.get("title", ""), "headline": b.get("headline", "")}
            for d, b in sorted(briefs.items(), reverse=True)][:30]


def _fc_lines(fc: dict) -> list[str]:
    out = []
    for h in ("1w", "1m", "3m", "12m"):
        x = fc["horizons"][h]
        out.append(f"{HZ_KO[h]}: {x['published_delta_krw']:+.1f}원 → {x['implied_rate']:.2f} "
                   f"({x['signal']}, conf {round(x['confidence']*100)}%)")
    return out


async def generate(trigger: str = "manual") -> dict:
    from . import news as news_mod
    fc = engine.S.get("forecast")
    date = datetime.now(KST).date().isoformat()
    collector.emit("orchestrator", f"데일리 브리프 생성 시작 ({trigger})", "info", category="orchestrator")
    news_items = (await news_mod.refresh())[:10]
    fc_lines = _fc_lines(fc) if fc else []
    payload = {"analysis": "", "news_digest": [], "trading_view": "", "risks": []}
    try:
        from . import notes as notes_mod
        raw = await call_claude(SYSTEM,
            f"오늘(KST {date}) USD/KRW: {collector.latest.get('rate')}원\n"
            f"위원회 예측:\n" + "\n".join(fc_lines) +
            "\n뉴스:\n" + "\n".join(f"- {n['title']}" for n in news_items) +
            "\n\n" + notes_mod.context_block())
        t = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.S)
        m = re.search(r"\{.*\}", t, flags=re.S)
        payload.update(json.loads(m.group(0) if m else t))
    except Exception as e:
        payload["analysis"] = f"Report generation failed: {str(e)[:150]}"
        collector.emit("orchestrator", f"브리프 분석 생성 실패: {str(e)[:80]}", "error", category="orchestrator")
    one = fc["horizons"]["1m"] if fc else None
    brief = {
        "date": date, "title": "원/달러 데일리 브리프",
        "headline": (f"1개월: {one['published_delta_krw']:+.1f}원 → {one['implied_rate']:.2f} "
                     f"({one['signal']}, conf {round(one['confidence']*100)}%)") if one else "(예측 없음)",
        "forecast_summary": " / ".join(fc_lines),
        "analysis": str(payload.get("analysis", ""))[:3000],
        "news_digest": [str(x)[:300] for x in (payload.get("news_digest") or [])][:6],
        "trading_view": str(payload.get("trading_view", ""))[:600],
        "risks": [str(x)[:200] for x in (payload.get("risks") or [])][:5],
        "sources": [n["link"] for n in news_items[:5]],
        "fc_lines": fc_lines,
    }
    briefs[date] = brief
    _save()
    sent = await _telegram(brief)
    collector.emit("orchestrator", f"데일리 브리프 완료 · 텔레그램 {'전송' if sent else '미설정'}",
                   "ok", category="orchestrator")
    return {"ok": True, "brief": brief, "telegram_sent": sent}


async def _telegram(b: dict) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return False
    text = (f"💱 {b['title']} · {b['date']}\n{b['headline']}\n\n"
            f"📊 {b['forecast_summary']}\n\n🔎 {b['analysis']}\n\n"
            + ("📰 " + "\n· ".join(b["news_digest"]) + "\n\n" if b["news_digest"] else "")
            + (f"🎯 {b['trading_view']}\n" if b["trading_view"] else "")
            + ("⚠️ " + " / ".join(b["risks"]) if b["risks"] else ""))
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(f"https://api.telegram.org/bot{token}/sendMessage",
                                  json={"chat_id": chat, "text": text[:4000]})
            r.raise_for_status()
        return True
    except Exception as e:
        collector.emit("orchestrator", f"텔레그램 전송 실패: {str(e)[:80]}", "error", category="orchestrator")
        return False
