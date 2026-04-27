"""
In-memory activity ring buffer — logs real events from scraper, agents, orchestrator.
Frontend polls /api/activity to display actual activity, not simulated messages.

Thread-safety note: asyncio is single-threaded; no lock needed for the deque.
"""
import time
from collections import deque
from dataclasses import dataclass

MAX_EVENTS = 80


@dataclass
class ActivityEvent:
    id: int
    ts: float
    source: str   # collector|agent|orchestrator|system
    agent: str
    message: str
    color: str = "#C9A84C"
    status: str = "info"  # info|ok|warn|error


_buf: deque[ActivityEvent] = deque(maxlen=MAX_EVENTS)
_counter = 0


def emit(source: str, agent: str, message: str, color: str = "#C9A84C", status: str = "info"):
    global _counter
    _counter += 1
    _buf.append(ActivityEvent(
        id=_counter, ts=time.time(),
        source=source, agent=agent,
        message=message, color=color, status=status,
    ))


def get_events_since(after_id: int = 0, limit: int = 20) -> list[ActivityEvent]:
    return [e for e in _buf if e.id > after_id][-limit:]


def get_latest(limit: int = 15) -> list[ActivityEvent]:
    return list(_buf)[-limit:]


# ── Typed emitters ────────────────────────────────────────────────────────────

def collecting(source_name: str, url: str = ""):
    suffix = f" ({url[:50]})" if url else ""
    emit("collector", source_name, f"Fetching {source_name}{suffix}…", "#4A90D9", "info")


def collected(source_name: str, count: int, unit: str = "items"):
    emit("collector", source_name, f"{source_name} → {count} {unit} received", "#38A169", "ok")


def collect_failed(source_name: str, reason: str):
    emit("collector", source_name, f"{source_name} failed: {reason[:60]}", "#E53E3E", "error")


def agent_start(agent_name: str, round_num: int = 1):
    label = f" [R{round_num}]" if round_num > 1 else ""
    emit("agent", agent_name, f"{agent_name}{label} analyzing…", "#9F7AEA", "info")


def agent_done(agent_name: str, signal: str, delta_12m: float, confidence: float, revised: bool = False):
    arrow = "▼" if delta_12m < 0 else "▲" if delta_12m > 0 else "—"
    color = "#38A169" if signal == "dovish" else "#E53E3E" if signal == "hawkish" else "#C9A84C"
    rev_tag = " (revised)" if revised else ""
    emit("agent", agent_name,
         f"{agent_name} → {signal.upper()} {arrow}{abs(delta_12m):.0f}bps · conf {confidence:.0%}{rev_tag}",
         color, "ok")


def orchestrator_event(message: str):
    emit("orchestrator", "Chief", message, "#C9A84C", "info")


def system_event(message: str):
    emit("system", "System", message, "#4A6080", "info")
