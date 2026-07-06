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

SYSTEM = """당신은 외환 리서치 데스크의 수석 애널리스트입니다. 위원회 예측·시장 데이터·뉴스·구조
노트를 종합해 기관 투자자에게 배포할 수준의 원/달러 데일리 리포트를 한국어로 작성합니다.
단순 요약이 아니라 해석과 분석이 담긴 종합 리포트여야 합니다.

작성 원칙:
- market_summary: 스팟 흐름(전일 대비)과 주변 지표(달러인덱스·미 10년물·엔/달러·코스피)가
  말해주는 오늘의 시장 국면을 서술적으로 해석 (숫자 나열 금지, 의미 중심 3~5문장).
- analysis: 자금이동 서술에 치우치지 말고 4개 이론 축을 균형 있게, 각 축마다 오늘의 데이터·뉴스와
  연결해 심층 분석 (축별 2~3문장, 총 8~12문장. 문단 구분은 줄바꿈):
  ① 경상수지·환류 구조 — 흑자 헤드라인이 아닌 실제 달러 환류로 평가(BOK 2026-15; 삼성·하이닉스
     미국 재투자=환류 제한, 국내 메가 프로젝트=부분 상쇄) ② 이자율평가(한미 금리차·캐리)
  ③ 통화량·유동성 ④ 수급·포지셔닝(개입·역외·외국인 자금).
- committee_view: 위원회 예측 수치를 해석 — 왜 이 방향·크기인지, 합의도와 신뢰도를 어떻게 읽어야
  하는지 3~5문장.
- news_analysis: 스크랩된 뉴스를 테마별로 2~4개 그룹으로 묶어, 각 테마의 내용을 설명(summary)하고
  환율에 갖는 함의(implication)를 분석. 개별 헤드라인 나열이 아니라 종합 해설.
- scenarios: 상방/기본/하방 3개 시나리오 — 각각 확률, 경로 서술, 촉발 조건.
- trading_view: 구체적 레벨과 시나리오별 대응이 담긴 전술 3~5문장.
- risks: 각 리스크에 근거를 붙여 3~5개.

JSON만 출력:
{"market_summary":"...","analysis":"...","committee_view":"...",
"news_analysis":[{"theme":"테마명","summary":"종합 설명 2~4문장","implication":"환율 함의 1~2문장"}],
"news_digest":["핵심 뉴스 한 문장 요약 3~6개"],
"scenarios":[{"name":"상방|기본|하방","prob":"확률%","path":"경로 서술","trigger":"촉발 조건"}],
"trading_view":"...","risks":["리스크(근거 포함)"]}"""


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


def _market_block() -> str:
    lt = collector.latest or {}
    lines = [f"USD/KRW 스팟: {lt.get('rate')}원"
             + (f" (전일 대비 {lt.get('change'):+.2f}원, {lt.get('change_pct'):+.3f}%)"
                if lt.get('change') is not None else "")]
    for v in (collector.context or {}).values():
        try:
            lines.append(f"{v['label']}: {v['price']}"
                         + (f" ({v['change_pct']:+.2f}%)" if v.get('change_pct') is not None else ""))
        except Exception:
            continue
    return "\n".join(lines)


async def generate(trigger: str = "manual") -> dict:
    from . import news as news_mod
    fc = engine.S.get("forecast")
    ev = engine.S.get("eval") or {}
    date = datetime.now(KST).date().isoformat()
    collector.emit("orchestrator", f"데일리 브리프 생성 시작 ({trigger})", "info", category="orchestrator")
    news_items = (await news_mod.refresh())[:12]
    fc_lines = _fc_lines(fc) if fc else []
    payload = {"analysis": "", "news_digest": [], "trading_view": "", "risks": []}
    try:
        from . import notes as notes_mod
        raw = await call_claude(SYSTEM,
            f"오늘: KST {date}\n[시장 데이터]\n{_market_block()}\n\n"
            f"[위원회 예측]\n" + "\n".join(fc_lines) +
            (f"\n합의 평가: rating={ev.get('rating')}, 평균 신뢰도={ev.get('mean_confidence')}, "
             f"합의도={ev.get('agreement')}, 다수 신호={ev.get('majority_signal')}\n" if ev else "\n") +
            "\n[스크랩된 뉴스 (중요도순)]\n"
            + "\n".join(f"- [{n.get('score', 0)}] ({n.get('source', '')}) {n['title']}" for n in news_items)
            + "\n\n" + notes_mod.context_block())
        t = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.S)
        m = re.search(r"\{.*\}", t, flags=re.S)
        payload.update(json.loads(m.group(0) if m else t))
    except Exception as e:
        payload["analysis"] = f"Report generation failed: {str(e)[:150]}"
        collector.emit("orchestrator", f"브리프 분석 생성 실패: {str(e)[:80]}", "error", category="orchestrator")
    one = fc["horizons"]["1m"] if fc else None

    def _clean_themes(items):
        out = []
        for x in (items or [])[:5]:
            if not isinstance(x, dict):
                continue
            out.append({"theme": str(x.get("theme", ""))[:100],
                        "summary": str(x.get("summary", ""))[:1200],
                        "implication": str(x.get("implication", ""))[:500]})
        return out

    def _clean_scenarios(items):
        out = []
        for x in (items or [])[:4]:
            if not isinstance(x, dict):
                continue
            out.append({"name": str(x.get("name", ""))[:40], "prob": str(x.get("prob", ""))[:20],
                        "path": str(x.get("path", ""))[:500], "trigger": str(x.get("trigger", ""))[:300]})
        return out

    brief = {
        "date": date, "title": "원/달러 데일리 리포트",
        "headline": (f"1개월: {one['published_delta_krw']:+.1f}원 → {one['implied_rate']:.2f} "
                     f"({one['signal']}, conf {round(one['confidence']*100)}%)") if one else "(예측 없음)",
        "forecast_summary": " / ".join(fc_lines),
        "market_summary": str(payload.get("market_summary", ""))[:2000],
        "analysis": str(payload.get("analysis", ""))[:6000],
        "committee_view": str(payload.get("committee_view", ""))[:2000],
        "news_analysis": _clean_themes(payload.get("news_analysis")),
        "news_digest": [str(x)[:300] for x in (payload.get("news_digest") or [])][:6],
        "scenarios": _clean_scenarios(payload.get("scenarios")),
        "trading_view": str(payload.get("trading_view", ""))[:1500],
        "risks": [str(x)[:300] for x in (payload.get("risks") or [])][:5],
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
            + (f"🌐 {b['market_summary']}\n\n" if b.get("market_summary") else "")
            + f"📊 {b['forecast_summary']}\n\n"
            + (f"🧭 {b['committee_view']}\n\n" if b.get("committee_view") else "")
            + f"🔎 {b['analysis']}\n\n"
            + ("📰 " + "\n".join(f"· {t['theme']}: {t['implication'] or t['summary']}"
                                 for t in b.get("news_analysis") or []) + "\n\n"
               if b.get("news_analysis") else
               ("📰 " + "\n· ".join(b["news_digest"]) + "\n\n" if b["news_digest"] else ""))
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
