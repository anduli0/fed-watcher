"""Telegram delivery — pushes (1) a synthesized daily-brief summary and (2) the
rate-path derivation report to the owner's chat when they update. Reuses the
personal bot. No-op (logged) if unconfigured. Never raises into the caller."""
from __future__ import annotations
import asyncio
import json
import logging
import hashlib
import re
import html as _html
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select, desc, and_

from backend.config import settings
from backend.database.init_db import AsyncSessionLocal
from backend.database.models import DailyBriefing, HORIZONS
from backend.database import crud

logger = logging.getLogger("fed_watcher.telegram")

MAX_LEN = 3800   # Telegram hard limit 4096; leave headroom
_STATE_FILE = Path(__file__).resolve().parent.parent / ".telegram_state.json"

_SIG_KO = {"hawkish": "매파", "dovish": "비둘기", "neutral": "중립"}
_H_KO = {"today": "오늘", "3m": "3개월", "6m": "6개월", "12m": "1년", "3y": "3년", "10y": "10년"}


# ── plumbing ────────────────────────────────────────────────────────────────

def _now_kst() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%m/%d %H:%M")


def _today_kst() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()


def _load_state() -> dict:
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    try:
        _STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.warning("Could not save telegram state: %s", e)


def _chat_ids() -> list[str]:
    return [c.strip() for c in (settings.TELEGRAM_CHAT_ID or "").split(",") if c.strip()]


def _chunks(text: str) -> list[str]:
    if len(text) <= MAX_LEN:
        return [text]
    out, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > MAX_LEN:
            out.append(cur)
            cur = ""
        cur += line + "\n"
    if cur.strip():
        out.append(cur)
    return out


def _esc(s) -> str:
    return _html.escape(str(s or ""))


def _strip_md(s: str) -> str:
    return re.sub(r"[#*`>_]", "", s or "")


def _md_to_telegram(md: str, max_len: int = 2600) -> str:
    """Turn an LLM markdown report into phone-friendly plain text: drop tables,
    turn headings into '▸ …' lines, normalise bullets, collapse blank runs. Kept
    readable in a chat bubble — no pipes, no markdown punctuation."""
    out: list[str] = []
    for raw in (md or "").split("\n"):
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            if out and out[-1] != "":
                out.append("")
            continue
        # skip markdown table rows / separators
        if set(stripped) <= set("|-: ") or stripped.count("|") >= 2:
            continue
        # headings → ▸ label
        m = re.match(r"^#{1,6}\s*(.+)$", stripped)
        if m:
            out.append(f"▸ {re.sub(r'[*`_]', '', m.group(1)).strip()}")
            continue
        # bullets → ·
        b = re.match(r"^[-*+]\s+(.*)$", stripped)
        if b:
            out.append(f"· {re.sub(r'[*`_>]', '', b.group(1)).strip()}")
            continue
        out.append(re.sub(r"[*`_>]", "", stripped))
    text = "\n".join(out).strip()
    if len(text) > max_len:
        text = text[:max_len].rsplit("\n", 1)[0].rstrip() + "\n…"
    return text


async def send_telegram(text: str, parse_mode: str = "HTML") -> bool:
    token = settings.TELEGRAM_BOT_TOKEN
    chats = _chat_ids()
    if not token or not chats:
        logger.info("Telegram skipped (TELEGRAM_BOT_TOKEN/CHAT_ID not set)")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    ok_all = True
    async with httpx.AsyncClient(timeout=20) as client:
        for chat_id in chats:
            for chunk in _chunks(text):
                sent = False
                for attempt in range(3):
                    try:
                        r = await client.post(url, json={
                            "chat_id": chat_id, "text": chunk,
                            "parse_mode": parse_mode, "disable_web_page_preview": True,
                        })
                        if r.status_code == 200:
                            sent = True
                            break
                        logger.warning("Telegram send failed %s: %s", r.status_code, r.text[:200])
                        if 400 <= r.status_code < 500:
                            break  # bad request — retrying won't help
                    except Exception as e:
                        logger.warning("Telegram send error (try %d): %r", attempt + 1, e)
                    await asyncio.sleep(1.5 * (attempt + 1))
                ok_all = ok_all and sent
    logger.info("Telegram delivery %s (%d chat)", "ok" if ok_all else "partial-fail", len(chats))
    return ok_all


async def _rate_call_line(db) -> str:
    """One-line current rate-path call across the 4 horizons."""
    parts = []
    for h in HORIZONS:
        fc = await crud.get_latest_horizon_forecast(db, h)
        if not fc:
            continue
        d = fc.published_delta or 0
        sig = "hawkish" if d >= 25 else "dovish" if d <= -25 else "neutral"
        sign = "+" if d > 0 else ""
        parts.append(f"{_H_KO[h]} {sign}{d:.0f}bps {_SIG_KO[sig]}")
    return " · ".join(parts)


# ── public: daily brief summary ───────────────────────────────────────────────

async def notify_daily_brief(date_str: str | None = None) -> bool:
    """Send a synthesized daily-brief summary to Telegram. Idempotent per date."""
    date_str = date_str or _today_kst()
    try:
        state = _load_state()
        if state.get("last_brief_date") == date_str:
            return False  # already delivered today's brief
        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                select(DailyBriefing).where(and_(
                    DailyBriefing.briefing_date == date_str,
                    DailyBriefing.language == "ko",
                    DailyBriefing.status == "published",
                )).order_by(desc(DailyBriefing.id)).limit(1)
            )).scalar_one_or_none()
            if not row:
                return False
            exec_summary = json.loads(row.executive_summary_json) if row.executive_summary_json else []
            body = json.loads(row.body_json) if row.body_json else {}
            call = await _rate_call_line(db)

        what_changed = body.get("whatChangedSinceYesterday", []) or []
        watch_next = body.get("watchNext", []) or []

        lines = [f"📰 <b>Fed-Watcher 데일리 브리프</b> · {_esc(date_str)}", ""]
        head = row.market_impact_headline or row.title
        if head:
            lines.append(f"<b>{_esc(head)}</b>")
        if call:
            lines += ["", "💹 <b>현재 금리 경로</b>", _esc(call)]
        if exec_summary:
            lines += ["", "📌 <b>핵심 요약</b>"] + [f"· {_esc(s)}" for s in exec_summary[:4]]
        if what_changed:
            lines += ["", "🔄 <b>어제와 달라진 점</b>"] + [f"· {_esc(s)}" for s in what_changed[:3]]
        if watch_next:
            lines += ["", "👀 <b>주목</b>"] + [f"· {_esc(s)}" for s in watch_next[:3]]
        lines += ["", "<i>Fed-Watcher · 21 에이전트 · 자동 전송</i>"]

        ok = await send_telegram("\n".join(lines))
        if ok:
            state["last_brief_date"] = date_str
            _save_state(state)
        return ok
    except Exception as e:
        logger.warning("notify_daily_brief failed: %s", e)
        return False


# ── public: derivation report ─────────────────────────────────────────────────

async def notify_derivation_report(report_ko: str, changed: list[str] | None = None) -> bool:
    """Send the rate-path derivation report when it updates: whenever a horizon
    changed, or once per day for the first cycle. Dedupes identical text so an
    unchanged report is never re-sent."""
    changed = changed or []
    try:
        if not report_ko or not report_ko.strip():
            return False
        # Never push a failed/degraded generation to the user's phone.
        low = report_ko.strip().lower()
        if low.startswith("report generation failed") or len(report_ko.strip()) < 120:
            logger.info("Skipping Telegram report — generation failed or too short")
            return False
        today = _today_kst()
        digest = hashlib.sha256(report_ko.encode("utf-8")).hexdigest()[:16]
        state = _load_state()
        first_today = state.get("last_report_date") != today
        same_text = state.get("last_report_hash") == digest

        if not changed and not first_today:
            return False   # nothing changed and already delivered today
        if same_text and not changed:
            return False   # identical report, no material change

        async with AsyncSessionLocal() as db:
            call = await _rate_call_line(db)

        header = "🔔 업데이트" if changed else "🗓 일일 보고서"
        ch = ("  ·  변경: " + ", ".join(_H_KO.get(h, h) for h in changed)) if changed else ""
        lines = [
            "📊 <b>Fed-Watcher 금리예측 도출보고서</b>",
            f"{header}{ch}  ·  {_now_kst()} KST",
        ]
        if call:
            lines += ["", f"💹 <b>현재 금리 경로</b>", _esc(call)]
        lines += ["", _esc(_md_to_telegram(report_ko)).strip()]
        lines += ["", "<i>Fed-Watcher · 21 에이전트 · 자동 전송</i>"]

        ok = await send_telegram("\n".join(lines))
        if ok:
            state["last_report_date"] = today
            state["last_report_hash"] = digest
            _save_state(state)
        return ok
    except Exception as e:
        logger.warning("notify_derivation_report failed: %s", e)
        return False


# ── public: Treasury trading desk ─────────────────────────────────────────────

_DIR_EMOJI = {"long": "🟢", "short": "🔴", "neutral": "⚪"}
_DIR_KO = {"long": "롱", "short": "숏", "neutral": "관망"}


async def notify_trading_desk(changed: list[str] | None = None) -> bool:
    """Send the Treasury trading-desk positions (long/short per maturity) to Telegram.
    Same trigger as the derivation report: on a forecast change or the first cycle of
    the day. Dedupes identical content."""
    changed = changed or []
    try:
        from backend.routes.trading_routes import get_trading_desk
        async with AsyncSessionLocal() as db:
            desk = await get_trading_desk(equity=1_000_000.0, db=db)
        positions = desk.get("positions", [])
        if not positions:
            return False

        lines = [f"📈 <b>Fed-Watcher 국채 트레이딩</b> · {_esc(desk.get('as_of'))}"]
        if desk.get("fed_funds") is not None:
            lines.append(f"기준금리 {desk['fed_funds']:.2f}%")
        lines.append("")
        for p in positions:
            e = _DIR_EMOJI.get(p["direction"], "⚪")
            if p["direction"] == "neutral":
                lines.append(f"{e} <b>{p['label']}</b> 관망")
            else:
                cy, ty = p.get("current_yield"), p.get("target_yield")
                mv = p.get("futures_price_move_pct")
                yl = f"{cy:.2f}→{ty:.2f}%" if (cy is not None and ty is not None) else ""
                mvs = f" ({mv:+.1f}%)" if mv is not None else ""
                lines.append(
                    f"{e} <b>{p['label']}</b> {_DIR_KO[p['direction']]} · {yl} · "
                    f"{p['futures_symbol']} {p.get('futures_contracts', 0)}계약{mvs}"
                )
        lines += ["", "<i>비둘기=채권 롱 / 매파=숏 · 모델 산출, 투자조언 아님</i>"]
        msg = "\n".join(lines)

        today = _today_kst()
        digest = hashlib.sha256(msg.encode("utf-8")).hexdigest()[:16]
        state = _load_state()
        first_today = state.get("last_desk_date") != today
        if not changed and not first_today:
            return False
        if state.get("last_desk_hash") == digest and not changed:
            return False

        ok = await send_telegram(msg)
        if ok:
            state["last_desk_date"] = today
            state["last_desk_hash"] = digest
            _save_state(state)
        return ok
    except Exception as e:
        logger.warning("notify_trading_desk failed: %s", e)
        return False
