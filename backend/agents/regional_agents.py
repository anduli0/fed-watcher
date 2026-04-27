"""
12 separate Regional Fed agents — one per Federal Reserve Bank.
Each agent specializes in their bank's institutional priors and current president.
"""
from backend.agents.base_agent import BaseAgent, AgentContext, OUTPUT_SCHEMA

REGIONAL_FEDS = [
    {
        "id": 101, "name": "Boston_Fed", "bank": "Boston", "president": "Susan Collins",
        "priors": "Centrist; balances employment and inflation mandates equally; data-dependent; tends toward consensus voting; modest hawkish lean during high inflation periods.",
        "vote_year_pattern": "Rotates voting alongside Cleveland, Richmond, San Francisco",
    },
    {
        "id": 102, "name": "NewYork_Fed", "bank": "New York", "president": "John Williams",
        "priors": "Permanent FOMC voter and Vice Chair. Centrist anchor of the committee. Strong focus on financial conditions, neutral rate (r*) research originator. Highly influential on long-run rate views. Rarely dissents.",
        "vote_year_pattern": "Permanent voter — every meeting",
    },
    {
        "id": 103, "name": "Philadelphia_Fed", "bank": "Philadelphia", "president": "Anna Paulson",
        "priors": "Slightly hawkish historically. Watches services inflation, supply chain dynamics. Empirical and academic-leaning. Moderate dovish potential when labor weakens.",
        "vote_year_pattern": "Rotates with Boston, Cleveland, Richmond",
    },
    {
        "id": 104, "name": "Cleveland_Fed", "bank": "Cleveland", "president": "Beth Hammack",
        "priors": "Former Goldman Sachs executive (markets background). Perceived hawkish bias on inflation. Risk-management framework focused on financial stability. Dissent-prone if inflation shows resistance.",
        "vote_year_pattern": "Rotates with Boston, Philadelphia, Richmond",
    },
    {
        "id": 105, "name": "Richmond_Fed", "bank": "Richmond", "president": "Tom Barkin",
        "priors": "Centrist-hawkish. Focused on supply-side constraints and sticky services inflation. Methodical, business-survey-driven approach. Often emphasizes longer-run risks of premature easing.",
        "vote_year_pattern": "Rotates with Boston, Cleveland, Philadelphia",
    },
    {
        "id": 106, "name": "Atlanta_Fed", "bank": "Atlanta", "president": "Raphael Bostic",
        "priors": "Centrist-hawkish on inflation, dovish on labor mandate. Emphasizes regional GDP heterogeneity. Cautious on cuts unless 2% target firmly in sight. Voted dissent in past cycles.",
        "vote_year_pattern": "Rotates with Chicago, St. Louis, Dallas, San Francisco",
    },
    {
        "id": 107, "name": "Chicago_Fed", "bank": "Chicago", "president": "Austan Goolsbee",
        "priors": "Most prominent dove on the FOMC. Academic economist (U.Chicago). Strong focus on labor market slack, growth risks. Vocal advocate for cuts when inflation trends toward target. Uses 'golden path' framing.",
        "vote_year_pattern": "Rotates with Atlanta, St. Louis, Dallas",
    },
    {
        "id": 108, "name": "StLouis_Fed", "bank": "St. Louis", "president": "Alberto Musalem",
        "priors": "New (since 2024). Former Tudor portfolio manager. Markets-oriented. Perceived hawkish bias. Emphasizes inflation persistence risks and policy patience.",
        "vote_year_pattern": "Rotates with Atlanta, Chicago, Dallas",
    },
    {
        "id": 109, "name": "Minneapolis_Fed", "bank": "Minneapolis", "president": "Neel Kashkari",
        "priors": "Notable polarity shift: was the FOMC's biggest dove (2014–2017), then became a major hawk (2022–2023). Reactive to incoming data. Volatile but data-rigorous. High public profile.",
        "vote_year_pattern": "Rotates with Kansas City",
    },
    {
        "id": 110, "name": "KansasCity_Fed", "bank": "Kansas City", "president": "Jeff Schmid",
        "priors": "Hawkish institutional bias (Esther George legacy). Mid-American conservative orientation. Skeptical of unconventional policy. Tends to dissent toward tighter policy.",
        "vote_year_pattern": "Rotates with Minneapolis",
    },
    {
        "id": 111, "name": "Dallas_Fed", "bank": "Dallas", "president": "Lorie Logan",
        "priors": "Hawkish, especially on financial-conditions-driven easing. Former NY Fed market operations head. Focuses on Treasury market functioning, term premium dynamics, balance sheet runoff (QT).",
        "vote_year_pattern": "Rotates with Atlanta, Chicago, St. Louis",
    },
    {
        "id": 112, "name": "SanFrancisco_Fed", "bank": "San Francisco", "president": "Mary Daly",
        "priors": "Centrist with dovish lean on labor concerns. Focus on labor market dynamics, asymmetric mandate weighting. Tech-sector regional exposure. Generally consensus-aligned.",
        "vote_year_pattern": "Rotates with Boston, Cleveland, Richmond",
    },
]


class RegionalFedAgent(BaseAgent):
    weight: float = 0.35  # Lower weight per agent since 12 of them; total bloc ~4.2

    def __init__(self, config: dict):
        super().__init__()
        self.agent_id = config["id"]
        self.agent_name = config["name"]
        self.bank = config["bank"]
        self.president = config["president"]
        self.priors = config["priors"]
        self.vote_pattern = config["vote_year_pattern"]

    def _system_prompt(self) -> str:
        return f"""You are a specialist analyst tracking the {self.bank} Federal Reserve Bank.

President: {self.president}
Voting rotation: {self.vote_pattern}

Institutional priors (your baseline framework):
{self.priors}

Your job:
1. Identify {self.president}'s current stance based on recent speeches and bank communications.
2. Project the rate path that {self.president} would individually advocate at the FOMC.
3. Weight your output toward THIS bank's perspective — NOT the FOMC consensus. Other agents handle consensus.
4. If your bank's president has a contrarian view from current Fed policy, reflect that — your value is the dissenting/dissident signal.

Confidence calibration:
- 6m: high if recent speeches available; moderate otherwise
- 12m: moderate (reflects stance over typical voting cycle)
- 3y: low (hard to predict succession or stance evolution)
- 10y: very low (defer to Academic agent on r*)
"""

    def _user_message(self, ctx: AgentContext) -> str:
        return f"""Analyze the {self.bank} Fed's stance based on:

REGIONAL FED COMMUNICATIONS (12 banks scraped):
{ctx.regional_stances_text}

MACRO CONTEXT:
{ctx.macro_snapshot_text}

RECENT SPEECHES (cross-reference any from {self.president}):
{ctx.speeches_text[:3000]}

Project {self.president}'s individually preferred rate path at the next FOMC meeting and beyond.
Reflect their bank-specific priors and any recent communications that signal stance shifts.

{OUTPUT_SCHEMA}"""


# Module-level instances — orchestrator imports REGIONAL_AGENTS
REGIONAL_AGENTS: list[RegionalFedAgent] = [RegionalFedAgent(cfg) for cfg in REGIONAL_FEDS]
