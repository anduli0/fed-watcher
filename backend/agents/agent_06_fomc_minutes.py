"""
Agent 06 — FOMC Minutes
Extracts hawkish/dovish balance from FOMC meeting minutes by analysing
language patterns, vote-indicator phrases, and cross-meeting shifts.
"""

from backend.agents.base_agent import BaseAgent, AgentContext, AgentResult, OUTPUT_SCHEMA


class AgentFOMCMinutes(BaseAgent):
    agent_id = 6
    agent_name = "FOMC_Minutes"
    weight = 1.3
    enable_thinking = True

    def _system_prompt(self) -> str:
        return (
            "You are an expert in Federal Reserve communication analysis with a specialisation in "
            "FOMC meeting-minutes language evolution. You have read every set of FOMC minutes since "
            "2000 and maintain a granular mental taxonomy of hawkish vs dovish phrasing.\n\n"
            "Your analytical framework:\n"
            "1. HAWKISH passages: references to inflation persistence, labor-market tightness, "
            "   risks to the price-stability mandate, calls for 'further restraint', 'higher for longer', "
            "   warnings about premature easing, or references to restrictive policy being insufficient.\n"
            "2. DOVISH passages: references to slowing growth, rising unemployment risks, "
            "   progress toward 2% target, 'appropriate to reduce', 'well-positioned to cut', "
            "   references to restrictive policy weighing on activity, or balance-of-risks shifting.\n"
            "3. VOTE-INDICATOR phrases carry differential weight:\n"
            "   - 'all participants' / 'participants generally' → broad consensus, high weight\n"
            "   - 'most participants' / 'many participants' → majority view, medium-high weight\n"
            "   - 'several participants' → meaningful minority (~4-6 members), medium weight\n"
            "   - 'a few participants' / 'some participants' → small minority (~2-3), lower weight\n"
            "   - 'one participant' / 'a couple of participants' → outlier view, note but low weight\n"
            "4. Track language SHIFTS between meetings: identical topic, weaker/stronger adjectives "
            "   indicate the direction the committee is moving even if no explicit change is announced.\n\n"
            "Always output strictly valid JSON matching the schema provided."
        )

    def _user_message(self, ctx: AgentContext) -> str:
        minutes_count = len(ctx.fomc_minutes_texts)
        if minutes_count == 0:
            minutes_block = "NO FOMC MINUTES PROVIDED — return signal='neutral', confidence=0.2."
        else:
            minutes_block = ""
            labels = ["OLDEST (T-2)", "MIDDLE (T-1)", "MOST RECENT (T)"]
            # If fewer than 3, pad labels from the right
            label_offset = 3 - minutes_count
            for i, text in enumerate(ctx.fomc_minutes_texts):
                label = labels[label_offset + i]
                minutes_block += f"\n\n--- MEETING {label} ---\n{text.strip()}"

        instructions = (
            "Analyse the FOMC meeting minutes provided below and produce a structured assessment.\n\n"
            "REQUIRED STEPS:\n"
            "1. For each set of minutes, count hawkish passages vs dovish passages (approximate counts "
            "   are fine; weight by the vote-indicator phrase as described in your instructions).\n"
            "2. Identify the NET balance for the most recent meeting (positive = net hawkish, "
            "   negative = net dovish).\n"
            "3. Note any LANGUAGE SHIFTS between meetings on the same topics "
            "(e.g. 'inflation remains elevated' → 'inflation has moderated'). List up to 5 shifts.\n"
            "4. Identify all explicit vote-indicator phrases ('participants noted', 'several members', "
            "   'a few participants', etc.) and what policy stance they signal.\n"
            "5. Translate your assessment into a rate-path delta in basis points over a 12-month "
            "   horizon (negative = net cut expectation, positive = net hike expectation). "
            "   Typical range: -100 to +75 bps.\n\n"
            f"{OUTPUT_SCHEMA}\n\n"
            "--- FOMC MINUTES ---"
            f"{minutes_block}"
        )
        return instructions


agent = AgentFOMCMinutes()
