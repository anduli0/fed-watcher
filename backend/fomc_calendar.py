"""FOMC-meeting-based forecast horizons.

Every cycle forecasts the policy rate *after each FOMC decision* rather than at
fixed calendar offsets:

  * every scheduled FOMC meeting within the next 3 years  → key = decision date (ISO)
  * the meeting nearest 5 / 10 / 30 years ahead            → keys "5y" / "10y" / "30y"

The Fed publishes its calendar roughly two years ahead; later years are
projected from the standard 8-meeting pattern and flagged `projected`.
Override/extend with FOMC_CALENDAR_EXTRA="2028-01-26,2028-03-15,..." (ISO
decision dates; replaces the projection for any year it covers).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, timedelta

# Official schedules (second/decision day). Source: federalreserve.gov FOMC calendars.
KNOWN_MEETINGS: dict[int, list[str]] = {
    2024: ["2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12",
           "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18"],
    2025: ["2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
           "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10"],
    2026: ["2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
           "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09"],
    2027: ["2027-01-27", "2027-03-17", "2027-04-28", "2027-06-09",
           "2027-07-28", "2027-09-15", "2027-10-27", "2027-12-08"],
}

# Typical (month, day) anchors; each is snapped to the nearest Wednesday.
_PATTERN = [(1, 28), (3, 18), (4, 29), (6, 17), (7, 29), (9, 16), (10, 28), (12, 9)]

LONG_RUN_YEARS = (5, 10, 30)
WINDOW_YEARS = 3
PRIMARY_MONTHS = 12          # headline call = meeting nearest this many months ahead


@dataclass(frozen=True)
class HorizonSpec:
    key: str                 # "2026-12-09" | "5y" | "10y" | "30y"
    meeting_date: date
    kind: str                # "fomc" | "5y" | "10y" | "30y"
    projected: bool          # True when the date comes from the pattern, not the Fed
    months_ahead: float

    @property
    def is_fomc(self) -> bool:
        return self.kind == "fomc"

    def label(self, lang: str = "en") -> str:
        d = self.meeting_date
        if self.is_fomc:
            return f"{d.year}년 {d.month}월 FOMC" if lang == "ko" else d.strftime("%b %Y FOMC")
        yrs = self.kind[:-1]
        if lang == "ko":
            return f"{yrs}년 후 ({d.year}년 {d.month}월 FOMC)"
        return f"{yrs}Y ahead ({d.strftime('%b %Y')} FOMC)"


def _nearest_wednesday(d: date) -> date:
    shift = (2 - d.weekday()) % 7          # 2 = Wednesday
    if shift > 3:
        shift -= 7
    return d + timedelta(days=shift)


def _extra_overrides() -> dict[int, list[str]]:
    raw = os.getenv("FOMC_CALENDAR_EXTRA", "").strip()
    out: dict[int, list[str]] = {}
    for tok in raw.split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            d = date.fromisoformat(tok)
        except ValueError:
            continue
        out.setdefault(d.year, []).append(d.isoformat())
    return out


def meetings_for_year(year: int) -> list[tuple[date, bool]]:
    """[(decision_date, projected)] for a calendar year."""
    extra = _extra_overrides()
    if year in extra:
        return [(date.fromisoformat(s), False) for s in sorted(extra[year])]
    if year in KNOWN_MEETINGS:
        return [(date.fromisoformat(s), False) for s in KNOWN_MEETINGS[year]]
    return [(_nearest_wednesday(date(year, m, d)), True) for m, d in _PATTERN]


def all_meetings(start: date, end: date) -> list[tuple[date, bool]]:
    out = []
    for y in range(start.year, end.year + 1):
        out.extend(m for m in meetings_for_year(y) if start <= m[0] <= end)
    return out


def _months_ahead(today: date, d: date) -> float:
    return round((d - today).days / 30.4375, 1)


def _add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:                      # Feb 29
        return d.replace(year=d.year + years, day=28)


def fomc_horizons(today: date | None = None) -> list[HorizonSpec]:
    """Ordered horizon set for `today`: all meetings within 3y, then 5y/10y/30y."""
    today = today or date.today()
    window_end = _add_years(today, WINDOW_YEARS)
    specs = [
        HorizonSpec(key=d.isoformat(), meeting_date=d, kind="fomc",
                    projected=proj, months_ahead=_months_ahead(today, d))
        for d, proj in all_meetings(today, window_end)
    ]
    for yrs in LONG_RUN_YEARS:
        target = _add_years(today, yrs)
        cands = all_meetings(target - timedelta(days=120), target + timedelta(days=120))
        d, proj = min(cands, key=lambda m: abs((m[0] - target).days))
        specs.append(HorizonSpec(key=f"{yrs}y", meeting_date=d, kind=f"{yrs}y",
                                 projected=proj, months_ahead=_months_ahead(today, d)))
    return specs


def nearest_key(specs: list[HorizonSpec], months: float, fomc_only: bool = True) -> str | None:
    """Key of the horizon whose meeting is nearest `months` ahead."""
    pool = [s for s in specs if (s.is_fomc or not fomc_only)]
    if not pool:
        return None
    return min(pool, key=lambda s: abs(s.months_ahead - months)).key


def primary_key(specs: list[HorizonSpec]) -> str | None:
    return nearest_key(specs, PRIMARY_MONTHS)


def spec_by_key(specs: list[HorizonSpec]) -> dict[str, HorizonSpec]:
    return {s.key: s for s in specs}


def schedule_block(specs: list[HorizonSpec], primary: str | None, today: date) -> str:
    """Prompt block listing every key the agent must forecast."""
    lines = [
        f"\n\n### FORECAST HORIZONS — FOMC MEETING SCHEDULE (as of {today.isoformat()})",
        "Forecast the cumulative change in the fed funds target (bps vs TODAY's rate) "
        "that will be in effect AFTER each FOMC decision below. Use these exact keys.",
        "",
        "Every scheduled meeting within 3 years:",
    ]
    for i, s in enumerate(s for s in specs if s.is_fomc):
        tag = "  ← next meeting" if i == 0 else ""
        proj = " (projected date)" if s.projected else ""
        lines.append(f'  "{s.key}"  {s.meeting_date.strftime("%b %d %Y")}, '
                     f"+{s.months_ahead:.1f} mo{proj}{tag}")
    lines.append("")
    lines.append("Long run — the meeting nearest 5 / 10 / 30 years ahead:")
    for s in specs:
        if not s.is_fomc:
            lines.append(f'  "{s.key}"  ≈ {s.meeting_date.strftime("%b %Y")} FOMC '
                         f"(+{s.months_ahead / 12:.1f} yrs)")
    if primary:
        lines.append("")
        lines.append(f'Headline (primary) key: "{primary}" — the meeting nearest 12 months ahead.')
    lines.append(
        "\nPath rules: deltas are cumulative, so consecutive meetings normally differ by "
        "0 or ±25 bps (±50 in fast cycles, never >75). Hold = same delta as the previous "
        "meeting. Long-run keys should converge toward your neutral-rate view.\n"
    )
    return "\n".join(lines)
