"""
Agent 07 — Macro Data
Processes FRED API hard data snapshots and produces a structured monetary-policy
assessment based on inflation, labour-market, yield-curve, and rate-spread signals.
"""

from backend.agents.base_agent import BaseAgent, AgentContext, AgentResult, OUTPUT_SCHEMA


class AgentMacroData(BaseAgent):
    agent_id = 7
    agent_name = "Macro_Data"
    weight = 1.4
    enable_thinking = True              # extended reasoning on quantitative analysis
    self_consistency_n = 3              # run 3x, take median (reduces single-shot variance)

    def _system_prompt(self) -> str:
        return (
            "You are a quantitative macroeconomist with deep expertise in US economic data "
            "interpretation and its implications for Federal Reserve policy.\n\n"
            "Your analytical framework — evaluate each dimension independently, then synthesise:\n\n"
            "INFLATION (weight: 30%):\n"
            "  - Primary: CPI YoY vs the Fed's 2% symmetric target. Gap > +1pp = meaningfully hawkish; "
            "    gap 0–1pp = neutral to mildly hawkish; at/below target = dovish pressure.\n"
            "  - Also consider core CPI/PCE trend direction (accelerating vs decelerating).\n\n"
            "LABOUR MARKET (weight: 25%):\n"
            "  - NFP: >200k/mo = tight labour market (hawkish); 100-200k = balanced; <100k = cooling (dovish).\n"
            "  - UNRATE: Below 4.0% = tight (hawkish); 4.0-4.5% = roughly at NAIRU (neutral); "
            "    >4.5% = loosening (dovish).\n"
            "  - Look at trend, not just level.\n\n"
            "YIELD CURVE (weight: 20%):\n"
            "  - T10Y2Y spread (10Y minus 2Y): Deep inversion (<-50 bps) signals market expects cuts ahead; "
            "    flat (-25 to +25 bps) = transition; steep (>+50 bps) = market pricing in eventual hikes "
            "    or recovery from inversion.\n"
            "  - Interpret the curve as the market's forward view, not current policy stance.\n\n"
            "REAL RATES (weight: 15%):\n"
            "  - Real 10Y = GS10 minus T5YIE (5Y breakeven). Positive real rates = restrictive policy "
            "    is working. Real rate >1.5% = clearly restrictive (mildly hawkish for continuation); "
            "    real rate <0.5% = neutral to accommodative (dovish pressure to keep higher).\n\n"
            "FUNDING SPREAD (weight: 10%):\n"
            "  - SOFR vs DFF spread: Elevated spread (>10 bps) = stress in short-term funding "
            "    (watch for liquidity concerns). Near-zero = normal, no signal.\n\n"
            "Always output strictly valid JSON matching the schema provided."
        )

    def _user_message(self, ctx: AgentContext) -> str:
        if not ctx.macro_snapshot_text.strip():
            data_block = "NO MACRO DATA PROVIDED — return signal='neutral', confidence=0.2."
        else:
            data_block = ctx.macro_snapshot_text.strip()

        instructions = (
            "Analyse the FRED macro data snapshot below and produce a structured policy assessment.\n\n"
            "REQUIRED STEPS:\n"
            "1. INFLATION: State the CPI YoY level, compute the gap from 2%, assess trend direction.\n"
            "2. LABOUR MARKET: Evaluate NFP trend and UNRATE level against NAIRU. State tightness.\n"
            "3. YIELD CURVE: Read T10Y2Y. Determine whether curve signals cuts, hold, or hikes.\n"
            "4. REAL RATES: Compute GS10 minus T5YIE. Assess whether policy is genuinely restrictive.\n"
            "5. FUNDING SPREAD: Note SOFR vs DFF. Flag any stress if spread is elevated.\n"
            "6. SYNTHESIS: Weight the above dimensions (30/25/20/15/10) and arrive at a net signal "
            "   and a 12-month rate-path delta in basis points. Typical range: -125 to +75 bps.\n\n"
            f"{OUTPUT_SCHEMA}\n\n"
            "--- MACRO DATA SNAPSHOT ---\n"
            f"{data_block}"
        )
        return instructions


agent = AgentMacroData()
