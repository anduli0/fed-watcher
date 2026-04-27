"""
Agent 02 — NLP
Sentiment analysis of Fed speeches using speaker-weighted hawkish/dovish scoring.
Speaker hierarchy: Chair > Vice Chair > Governors > Regional Presidents.
"""

from backend.agents.base_agent import BaseAgent, AgentContext, AgentResult, OUTPUT_SCHEMA


class AgentNLP(BaseAgent):
    agent_id = 2
    agent_name = "NLP"
    weight = 1.2

    def _system_prompt(self) -> str:
        return (
            "You are an expert NLP analyst specializing in central bank communication, "
            "with deep experience parsing Federal Reserve speeches, testimonies, and press "
            "conference transcripts for monetary policy signals.\n\n"
            "### TASK\n"
            "Perform a structured hawkish/dovish sentiment analysis on the provided Fed speech "
            "corpus. Your analysis must:\n\n"
            "1. PHRASE SCORING — Identify and score key phrases:\n"
            "   Hawkish phrases (positive score): 'remains elevated', 'vigilant', 'not yet confident', "
            "   'further progress needed', 'data dependent', 'prepared to act', 'restrictive stance', "
            "   'above target', 'labor market tight', 'inflation risks', 'higher for longer'.\n"
            "   Dovish phrases (negative score): 'making progress', 'easing', 'well-anchored', "
            "   'cooling', 'balanced risks', 'moving in right direction', 'gradual', 'flexible', "
            "   'below potential', 'labor market softening', 'disinflation'.\n\n"
            "2. SPEAKER WEIGHTING — Apply the following authority weights when aggregating:\n"
            "   - Fed Chair:           weight = 3.0\n"
            "   - Fed Vice Chair:      weight = 2.0\n"
            "   - Board of Governors:  weight = 1.5\n"
            "   - Regional Presidents: weight = 1.0\n"
            "   If speaker identity is unclear, default to weight = 1.0.\n\n"
            "3. AGGREGATE SIGNAL — Compute a weighted net hawkish score across all speakers "
            "   and map to: hawkish (score > +5), neutral (-5 to +5), or dovish (score < -5).\n\n"
            "4. RATE PATH IMPLICATION — Translate the aggregate signal to an estimated 12-month "
            "   rate path delta in basis points (positive = net hikes, negative = net cuts).\n\n"
            + OUTPUT_SCHEMA
        )

    def _user_message(self, ctx: AgentContext) -> str:
        if not ctx.speeches_text:
            return (
                "[NO DATA] No speech text was provided. "
                "Return signal=neutral, rate_path_delta_bps=0, confidence=0.1, "
                "and note the absence of input in reasoning."
            )
        return (
            "### Fed Speech Corpus for NLP Sentiment Analysis\n\n"
            + ctx.speeches_text.strip()
            + "\n\n"
            "Using the speaker-weighted hawkish/dovish phrase scoring methodology in your system "
            "prompt, analyze the corpus above. Identify the most impactful phrases, apply speaker "
            "weights, compute the aggregate net hawkish score, and produce the final "
            "hawkish/neutral/dovish signal with 12-month rate path delta in bps and a confidence "
            "score between 0.0 and 1.0. Respond strictly in the required JSON format."
        )


agent = AgentNLP()
