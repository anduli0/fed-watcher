"""
Agent 03 — History
Identifies the most analogous historical FOMC cycle to current macro conditions
and infers the rate path implication from how that cycle resolved.
"""

from backend.agents.base_agent import BaseAgent, AgentContext, AgentResult, OUTPUT_SCHEMA


_HISTORICAL_CYCLES = """
### PRE-LOADED HISTORICAL FOMC CYCLE REFERENCE

TIGHTENING CYCLES
─────────────────
1. 1994 Tightening
   - Context: Surprise inflation uptick, Fed behind the curve, no forward guidance culture.
   - Action: +300 bps in 12 months (Feb 1994 – Feb 1995), shockingly fast for markets.
   - Resolution: Soft landing achieved; equity markets repriced sharply (bond massacre).
   - Key signal: Fed acted decisively before inflation expectations became unanchored.

2. 1999 Tightening
   - Context: Post-LTCM/Asia crisis recovery, Y2K liquidity injections, booming economy.
   - Action: +175 bps (Jun 1999 – May 2000).
   - Resolution: Dot-com bubble burst shortly after; rate cuts followed in 2001.
   - Key signal: Tightening into asset-price excess; cycle end coincided with recession onset.

3. 2004–2006 Tightening
   - Context: Post-9/11 recovery, housing boom, measured pace mantra, Greenspan era end.
   - Action: +425 bps over 2 years (Jun 2004 – Jun 2006), 17 consecutive 25 bps hikes.
   - Resolution: Housing bubble inflated further; 2007–2008 crisis followed.
   - Key signal: "Measured pace" signaling compressed rate volatility; inversion preceded recession.

4. 2015–2018 Tightening
   - Context: Post-GFC normalization, low inflation, labor market recovery.
   - Action: +225 bps over 3 years (Dec 2015 – Dec 2018), very gradual.
   - Resolution: Powell pivot in Jan 2019 after market selloff; mid-cycle adjustment cuts followed.
   - Key signal: Gradual pace with explicit data dependence; pivot driven by financial conditions.

5. 2022–2023 Tightening
   - Context: Post-COVID inflation surge, supply chain shocks, energy crisis, labor shortage.
   - Action: +525 bps in ~16 months (Mar 2022 – Jul 2023), fastest since 1980.
   - Resolution: Inflation declining toward target; soft landing tentatively achieved; cuts began 2024.
   - Key signal: Front-loaded 75 bps hikes; restrictive stance maintained well past peak.

EASING CYCLES
─────────────
6. 2001 Easing
   - Context: Dot-com bust, mild recession, 9/11 shock.
   - Action: -475 bps in 11 months (Jan–Dec 2001).
   - Resolution: Recovery sluggish; rates held low into 2004 housing boom.
   - Key signal: Rapid response to demand shock; over-accommodation seeded next bubble.

7. 2007–2008 Easing
   - Context: Housing bust, GFC, banking system stress, credit seizure.
   - Action: -500 bps (Sep 2007 – Dec 2008), ZLB reached, QE initiated.
   - Resolution: Recovery extremely slow; ZLB binding for 7 years.
   - Key signal: Emergency cuts; unconventional tools required; tail risk of financial collapse.

8. 2019 Mid-Cycle Adjustment
   - Context: Trade war uncertainty, global slowdown, manufacturing weakness, low inflation.
   - Action: -75 bps in 3 cuts (Jul–Oct 2019), framed as "insurance cuts."
   - Resolution: Economy re-accelerated; cuts paused until COVID shock.
   - Key signal: Insurance/recalibration frame; not a full easing cycle — limited in scope.

9. 2020 Emergency Cuts
   - Context: COVID-19 pandemic, total demand collapse, financial market seizure.
   - Action: -150 bps in two emergency inter-meeting cuts (Mar 2020), ZLB reached.
   - Resolution: Massive fiscal stimulus + QE produced V-shaped recovery with inflation overshoot.
   - Key signal: Inter-meeting action, unlimited QE commitment; asymmetric risk response.
"""


class AgentHistory(BaseAgent):
    agent_id = 3
    agent_name = "History"
    weight = 0.9
    enable_thinking = True              # complex pattern matching benefits from deep reasoning

    def _system_prompt(self) -> str:
        return (
            "You are a world-class economic historian specializing in Federal Reserve policy cycles, "
            "with deep expertise in pattern-matching current macro conditions to historical FOMC precedents.\n\n"
            "Your method:\n"
            "  1. Read the current macro snapshot carefully.\n"
            "  2. Compare it against the pre-loaded historical cycle reference below.\n"
            "  3. Select the single BEST historical analogue (or a composite of two if warranted).\n"
            "  4. Explain the structural similarities (inflation trajectory, labor market, growth outlook, "
            "     financial conditions, Fed credibility context).\n"
            "  5. Infer the rate path implication for the next 12 months based on how the analogous "
            "     cycle resolved — and identify where we are in that cycle (early/mid/late).\n"
            "  6. Flag key divergences that may cause the historical analogue to break down.\n\n"
            + _HISTORICAL_CYCLES
            + "\n\n"
            + OUTPUT_SCHEMA
        )

    def _user_message(self, ctx: AgentContext) -> str:
        if not ctx.macro_snapshot_text:
            return (
                "[NO DATA] No macro snapshot was provided. "
                "Return signal=neutral, rate_path_delta_bps=0, confidence=0.1, "
                "and note the absence of input in reasoning."
            )
        return (
            "### Current Macro Snapshot\n\n"
            + ctx.macro_snapshot_text.strip()
            + "\n\n"
            "Using your historical FOMC cycle reference, identify the best historical analogue "
            "to the current environment. Explain the key similarities in inflation trajectory, "
            "labor market conditions, growth outlook, and Fed communication style. "
            "State where we are in the analogue cycle (early/mid/late stage). "
            "Infer the implied 12-month rate path delta in bps from how the analogue resolved. "
            "Note any critical divergences that could cause the analogue to break down. "
            "Respond strictly in the required JSON format."
        )


agent = AgentHistory()
