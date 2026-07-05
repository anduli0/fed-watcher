"""
연구·정책 지식층 — 위원회 전체(에이전트·그룹·수석)와 데일리 브리프의 입력에
상시 포함되는 구조적 컨텍스트. 소유자가 /api/notes 로 추가할 수 있다.
"""
import json
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger("krw_watcher.notes")
KST = ZoneInfo("Asia/Seoul")
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
STORE = os.path.join(DATA_DIR, "notes.json")

# 기본 지식 (소유자 제공 + 공식 연구)
DEFAULT_NOTES: list[dict] = [
    {
        "id": "bok-2026-15",
        "date": "2026-06-18",
        "title": "BOK 이슈노트 2026-15 「해외투자와 투자소득이 환율에 미치는 영향」",
        "body": ("핵심: 투자소득수지 흑자 '규모'가 아니라 소득이 실제 국내로 송금·환전되어 "
                 "외환시장에 공급되는지(환류)가 환율에 중요. 정량 결과 — 해외투자가 평균 대비 "
                 "+3% 증가 충격 시 원/달러 +0.7% 상승(특히 해외증권투자에서 뚜렷), 투자소득 "
                 "+8% 증가 충격 시 -0.4% 하락(효과는 충격 초기에 집중). 해외 유보·재투자되면 "
                 "달러 공급으로 이어지지 않음. 한국의 해외직접투자 소득 중 재투자 비중 평균 40% "
                 "(일본 46%, 독일 28%, 대만 18%). 해외증권투자 2024년 670억→2025년 1,403억 달러 "
                 "(GDP 대비 3.6%→7.5%). IMF 전망: 경상수지 중 본원소득수지 비중 2025년 23%→"
                 "2030년 42%. 시사점: 경상수지/소득수지 흑자를 원화 강세 요인으로 기계적으로 "
                 "해석하지 말 것 — 배당 환류·현지유보 비중·환헤지 행태까지 봐야 함."),
    },
    {
        "id": "chaebol-reinvest",
        "date": "2026-07-05",
        "title": "삼성전자·SK하이닉스 흑자 미국 재투자 계획 (소유자 제공)",
        "body": ("경상수지 흑자의 큰 부분을 차지하는 삼성전자·SK하이닉스의 흑자가 대부분 미국에 "
                 "재투자될 계획 → BOK 노트의 논리대로 흑자에도 불구하고 실제 달러 환류·공급이 "
                 "제한되어 원화 강세 요인이 약화됨(구조적 원화약세 압력). 다만 최근 양사의 국내 "
                 "메가 프로젝트(대규모 국내 설비투자)는 국내 자금 수요·환류를 늘려 이 위험을 "
                 "부분적으로 낮추는 상쇄 요인. → 경상수지 흑자 헤드라인만으로 원화 강세를 "
                 "예측하지 말고, 환류율 관점에서 할인하여 평가할 것."),
    },
]


def load() -> list[dict]:
    try:
        with open(STORE, encoding="utf-8") as f:
            extra = json.load(f)
    except FileNotFoundError:
        extra = []
    except Exception as e:
        logger.warning("notes load failed: %s", e)
        extra = []
    seen = {n["id"] for n in DEFAULT_NOTES}
    return DEFAULT_NOTES + [n for n in extra if n.get("id") not in seen]


def add(title: str, body: str) -> dict:
    notes = []
    try:
        with open(STORE, encoding="utf-8") as f:
            notes = json.load(f)
    except Exception:
        pass
    rec = {"id": f"user-{len(notes)+1}", "date": datetime.now(KST).date().isoformat(),
           "title": title[:200], "body": body[:3000]}
    notes.append(rec)
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(STORE, "w", encoding="utf-8") as f:
            json.dump(notes, f, ensure_ascii=False)
    except Exception as e:
        logger.warning("notes save failed: %s", e)
    return rec


def context_block() -> str:
    lines = []
    for n in load():
        lines.append(f"▪ [{n['date']}] {n['title']}\n  {n['body']}")
    return "구조적 컨텍스트(연구·정책 노트 — 예측 시 반드시 반영):\n" + "\n".join(lines)
