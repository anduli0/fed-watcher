import { AllHorizons, HorizonForecast } from "@/lib/api";

type Lang = "en" | "ko";

const MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export const LONG_KINDS = ["5y", "10y", "30y"] as const;

export function byKey(all: AllHorizons | null | undefined, key: string | null | undefined): HorizonForecast | null {
  if (!all || !key) return null;
  return all.items.find(i => i.horizon === key) ?? null;
}

export function primaryOf(all: AllHorizons | null | undefined): HorizonForecast | null {
  return byKey(all, all?.primary);
}

export function fomcItems(all: AllHorizons | null | undefined): HorizonForecast[] {
  return all?.items.filter(i => i.kind === "fomc") ?? [];
}

export function longItems(all: AllHorizons | null | undefined): HorizonForecast[] {
  return all?.items.filter(i => (LONG_KINDS as readonly string[]).includes(i.kind)) ?? [];
}

export function nextMeeting(all: AllHorizons | null | undefined): HorizonForecast | null {
  return fomcItems(all)[0] ?? null;
}

/** Items shown as the headline cards: next FOMC · headline (~1Y) · 5Y · 10Y · 30Y. */
export function highlightItems(all: AllHorizons | null | undefined): HorizonForecast[] {
  const out: HorizonForecast[] = [];
  for (const fc of [nextMeeting(all), primaryOf(all), ...longItems(all)]) {
    if (fc && !out.some(o => o.horizon === fc.horizon)) out.push(fc);
  }
  return out;
}

function parts(fc: HorizonForecast): { y: number; m: number; d: number } {
  const [y, m, d] = (fc.meeting_date || "").split("-").map(Number);
  return { y: y || 0, m: m || 0, d: d || 0 };
}

/** Compact label for chips / axes: "Today" · "Dec ’26" / "26.12" · "5Y" / "5년". */
export function shortLabel(fc: HorizonForecast, lang: Lang): string {
  if (fc.kind === "today") return lang === "ko" ? "오늘" : "Today";
  if (fc.kind !== "fomc") {
    const yrs = fc.kind.replace("y", "");
    return lang === "ko" ? `${yrs}년` : `${yrs}Y`;
  }
  const { y, m } = parts(fc);
  return lang === "ko" ? `${String(y).slice(2)}.${m}` : `${MONTHS_EN[m - 1] ?? "?"} ’${String(y).slice(2)}`;
}

/** Full label: "2026년 12월 9일 FOMC" / "Dec 9, 2026 FOMC"; long run adds the years-ahead tag. */
export function longLabel(fc: HorizonForecast, lang: Lang): string {
  if (fc.kind === "today") return lang === "ko" ? "현행 기준금리" : "current rate";
  const { y, m, d } = parts(fc);
  const date = lang === "ko" ? `${y}년 ${m}월 ${d}일 FOMC` : `${MONTHS_EN[m - 1] ?? "?"} ${d}, ${y} FOMC`;
  if (fc.kind === "fomc") return date;
  const yrs = fc.kind.replace("y", "");
  return lang === "ko" ? `${yrs}년 후 · ${date}` : `${yrs}Y ahead · ${date}`;
}

/** Role tag shown next to a label (next meeting / headline / long run). */
export function roleTag(fc: HorizonForecast, all: AllHorizons | null | undefined, lang: Lang): string | null {
  if (fc.kind === "today") return null;
  if (fc.is_primary || fc.horizon === all?.primary) return lang === "ko" ? "헤드라인 · 약 1년" : "headline · ~1Y";
  if (nextMeeting(all)?.horizon === fc.horizon) return lang === "ko" ? "다음 FOMC" : "next FOMC";
  if (fc.kind !== "fomc") return lang === "ko" ? "장기" : "long run";
  return null;
}

/** Days-until text: "D-41" or "41d". */
export function countdown(fc: HorizonForecast, lang: Lang): string | null {
  if (fc.days_to_meeting == null || fc.kind === "today") return null;
  if (fc.days_to_meeting > 730) {
    const yrs = (fc.days_to_meeting / 365.25).toFixed(1);
    return lang === "ko" ? `${yrs}년 후` : `in ${yrs}y`;
  }
  return lang === "ko" ? `D-${fc.days_to_meeting}` : `in ${fc.days_to_meeting}d`;
}
