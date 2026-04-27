"""
Agent 04 — Academic
Calculates the Taylor Rule implied rate, compares it to the current Fed Funds Rate,
and interprets whether current policy is restrictive, neutral, or accommodative.
"""

from backend.agents.base_agent import BaseAgent, AgentContext, AgentResult, OUTPUT_SCHEMA


_TAYLOR_RULE_REFERENCE = """
### TAYLOR RULE FRAMEWORK

FORMULA
  r* = r_neutral + π + 0.5 × (π − π*) + 0.5 × y_gap

  Where:
    r*        = Taylor Rule implied Fed Funds Rate (%)
    r_neutral = Long-run neutral real rate = 2.5%  (Laubach-Williams / Fed median estimate)
    π         = Current inflation rate (%)         — use PCE YoY as primary; CPI YoY as secondary
    π*        = Fed's inflation target             = 2.0%
    y_gap     = Output gap (%)                     — approximate as: (real GDP growth − potential GDP growth)
                                                     or use unemployment gap: −(u − u*) × Okun coefficient 2.0
                                                     where u* = 4.0% NAIRU

INTERPRETATION OF POLICY STANCE
  (current Fed Funds Rate) vs. r*:
    FFR >> r*  → Policy is RESTRICTIVE  → hawkish signal, rate cuts are implied
    FFR ≈ r*   → Policy is NEUTRAL      → neutral signal
    FFR << r*  → Policy is ACCOMMODATIVE → dovish/behind-the-curve signal, rate hikes implied

VARIANT RULES (for sensitivity check)
  - Balanced approach rule:    r* = 2.5 + π + 0.5(π − 2.0) + 1.0 × y_gap
  - Inertial Taylor rule:      r*_t = 0.85 × r*_{t-1} + 0.15 × Taylor_rule_t  (smoothed)
  - Prescriptive lower bound:  max(r*, 0) to respect effective lower bound

NOTES
  - When PCE and CPI diverge by more than 0.5pp, report both and note the policy ambiguity.
  - The output gap is difficult to measure in real time; flag uncertainty explicitly.
  - A Taylor Rule result is a mechanical benchmark, not a forecast — always contextualize with
    Fed's stated reaction function and current forward guidance.
"""


class AgentAcademic(BaseAgent):
    agent_id = 4
    agent_name = "Academic"
    weight = 1.1

    def _system_prompt(self) -> str:
        return (
            "You are a monetary economist and academic policy analyst with deep expertise in the "
            "Taylor Rule, neutral rate estimation, and Federal Reserve reaction functions.\n\n"
            "Your task is to mechanically apply the Taylor Rule to the provided macro data, "
            "interpret the result relative to the current Fed Funds Rate, and produce a rigorous "
            "assessment of whether current monetary policy is restrictive, neutral, or accommodative.\n\n"
            "Always show your arithmetic step-by-step before stating the conclusion. "
            "If CPI and PCE diverge, compute the rule under both and note the range. "
            "If the output gap is not directly provided, estimate it from available data "
            "(GDP growth vs. trend, or unemployment gap) and state your assumption explicitly.\n\n"
            + _TAYLOR_RULE_REFERENCE
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
            "### Current Macro Snapshot (CPI / PCE / GDP / Unemployment Data)\n\n"
            + ctx.macro_snapshot_text.strip()
            + "\n\n"
            "Instructions:\n"
            "1. Extract the relevant values: current PCE YoY, CPI YoY, real GDP growth, "
            "   unemployment rate, and current Fed Funds Rate (upper bound).\n"
            "2. Estimate the output gap from the available data; state your assumption.\n"
            "3. Plug the values into the Taylor Rule formula: "
            "   r* = 2.5 + π + 0.5 × (π − 2.0) + 0.5 × y_gap\n"
            "4. Compare r* to the current Fed Funds Rate.\n"
            "5. Interpret the gap: is policy restrictive, neutral, or accommodative? "
            "   How many bps of adjustment does the rule imply over 12 months?\n"
            "6. Run the balanced-approach variant as a sensitivity check.\n"
            "Respond strictly in the required JSON format."
        )


agent = AgentAcademic()
