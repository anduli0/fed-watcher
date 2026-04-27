"""
Agent 09 — Regional Fed Presidents
Maps current stances of all 12 Regional Federal Reserve Bank presidents,
counts hawks vs doves, and assesses dissent probability at the next FOMC meeting.
"""

from backend.agents.base_agent import BaseAgent, AgentContext, AgentResult, OUTPUT_SCHEMA


class AgentRegional(BaseAgent):
    agent_id = 9
    agent_name = "Regional"
    weight = 1.0

    def _system_prompt(self) -> str:
        return (
            "You are an expert on FOMC composition and the policy preferences of the 12 Regional "
            "Federal Reserve Banks. You track each president's public speeches, interview comments, "
            "and voting record to maintain a current read on their stance.\n\n"
            "REGIONAL BANK PROFILES — traditional hawk/dove tendencies (note: individuals can shift; "
            "these are institutional priors, not rigid labels):\n\n"
            "  HAWKISH-LEANING BANKS (historically):\n"
            "  - Kansas City Fed (10th District): Historically among the most hawkish. "
            "    Strong agricultural/energy economy; concerned about inflation expectations.\n"
            "  - St. Louis Fed (8th District): Variable — had a monetarist tradition under Bullard "
            "    (data-dependent, sometimes contrarian hawk). Watch current president's posture.\n"
            "  - Dallas Fed (11th District): Oil-patch economy; historically inflation-sensitive. "
            "    Tends toward hawkish readings on energy price pass-through.\n"
            "  - Cleveland Fed (4th District): Manufacturing belt; inflation expectations focus. "
            "    Mester era was consistently hawkish — monitor new president's calibration.\n\n"
            "  NEUTRAL / CENTRIST BANKS:\n"
            "  - Chicago Fed (7th District): Large industrial Midwest economy; tends to track "
            "    the national consensus, occasionally pivots.\n"
            "  - Richmond Fed (5th District): Mid-Atlantic financial center; follows Board signals "
            "    closely. Moderate inflation focus.\n"
            "  - Atlanta Fed (6th District): GDPNow model home; data-first approach, broadly centrist.\n"
            "  - Minneapolis Fed (9th District): Under Kashkari — dovish on labour market, "
            "    but has adapted; watches financial stability risks.\n\n"
            "  DOVISH-LEANING BANKS (historically):\n"
            "  - San Francisco Fed (12th District): West Coast tech economy; historically sensitive "
            "    to labour market slack. Board Chair's former bank — often aligns with consensus.\n"
            "  - Boston Fed (1st District): Academic tradition; tends toward research-driven, "
            "    balanced risk approach. Occasionally dovish on employment mandate.\n"
            "  - New York Fed (2nd District): Permanent FOMC voter; Wall Street adjacent. "
            "    Implements policy; closely tracks Chair/Board signalling. Usually consensus.\n"
            "  - Philadelphia Fed (3rd District): Centrist-to-dovish; financial sector focus. "
            "    Watches credit conditions and financial stability.\n\n"
            "VOTING ROTATION NOTE:\n"
            "Only 5 of the 12 regional presidents vote at any given FOMC meeting on a rotating basis "
            "(New York always votes; 4 others rotate annually). Non-voters can still dissent in spirit "
            "through public speeches. Identify which banks are currently voting members.\n\n"
            "DISSENT MECHANICS:\n"
            "Formal dissents are rare (typically 0-2 per year). An implied dissent threshold: "
            "if a current voting member's public statements diverge >25 bps from the consensus "
            "path, dissent probability rises meaningfully. Two or more such members = high alert.\n\n"
            "Always output strictly valid JSON matching the schema provided."
        )

    def _user_message(self, ctx: AgentContext) -> str:
        if not ctx.regional_stances_text.strip():
            stances_block = (
                "NO REGIONAL STANCE DATA PROVIDED — return signal='neutral', confidence=0.2."
            )
        else:
            stances_block = ctx.regional_stances_text.strip()

        instructions = (
            "Analyse the regional Fed president stance data below and produce a structured assessment.\n\n"
            "REQUIRED STEPS:\n"
            "1. STANCE MAP: For each president mentioned, classify their current stance as "
            "   hawkish / leaning-hawkish / neutral / leaning-dovish / dovish. "
            "   Note the bank, whether they are a current voting member, and the key quote or "
            "   speech that supports the classification.\n"
            "2. HAWK/DOVE COUNT: Tally total hawks (hawkish + leaning-hawkish) vs total doves "
            "   (dovish + leaning-dovish) vs neutral, separately for voters and non-voters.\n"
            "3. CONSENSUS vs BOARD: Assess whether the regional president bloc is aligned with "
            "   or diverging from the Board of Governors' apparent stance.\n"
            "4. DISSENT PROBABILITY: For the next scheduled FOMC meeting, estimate the probability "
            "   of at least one formal dissent (0–100%). Identify the most likely dissenter(s) "
            "   and the direction of their likely dissent (prefer cut / prefer hike).\n"
            "5. RATE PATH DELTA: Translate the regional bloc's net stance into a 12-month rate-path "
            "   delta in basis points. Typical range: -75 to +75 bps.\n\n"
            f"{OUTPUT_SCHEMA}\n\n"
            "--- REGIONAL FED PRESIDENT STANCES ---\n"
            f"{stances_block}"
        )
        return instructions


agent = AgentRegional()
