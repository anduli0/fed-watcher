"""
Agent 01 — Behavioral
Analyzes Fed Chair body language/facial tension from press conference screenshots
or, when no image is available, falls back to transcript tone analysis (limited_mode).
"""

from backend.agents.base_agent import BaseAgent, AgentContext, AgentResult, OUTPUT_SCHEMA


class AgentBehavioral(BaseAgent):
    agent_id = 1
    agent_name = "Behavioral"
    weight = 0.8

    def _system_prompt(self) -> str:
        return (
            "You are a world-class expert in presidential and executive communication analysis, "
            "specializing in nonverbal signals, micro-expressions, vocal prosody, and rhetorical "
            "stress patterns of central bank officials.\n\n"
            "Your primary skill is reading Fed Chair press conferences at two levels:\n"
            "  1. VISUAL (preferred): facial tension, jaw set, brow furrow, eye contact avoidance, "
            "     posture shifts, and hand gestures that reveal cognitive load or emotional restraint.\n"
            "  2. TEXT FALLBACK (limited_mode): when no image is available you analyze transcript tone — "
            "     hedging language, sentence length under stress, repetition of forward-guidance phrases, "
            "     pause markers [laughter] / [pause], and deviation from prepared remarks.\n\n"
            "In either mode map your findings to monetary policy implications:\n"
            "  - Elevated nonverbal stress or defensive hedging → hawkish/uncertain signal\n"
            "  - Relaxed demeanor or confident forward-guidance → dovish/accommodative signal\n"
            "  - Neutral, scripted delivery → neutral signal\n\n"
            "Always acknowledge limited_mode explicitly in your reasoning when operating on text only.\n\n"
            + OUTPUT_SCHEMA
        )

    def _user_message(self, ctx: AgentContext) -> str:
        if ctx.speeches_text:
            limited_mode_note = (
                "[LIMITED MODE — no press conference image available. "
                "Analyze transcript tone only.]\n\n"
            )
            body = (
                limited_mode_note
                + "### Fed Chair Press Conference Transcript / Speech Text\n"
                + ctx.speeches_text.strip()
                + "\n\n"
                "Based on the text above, perform a tone-only behavioral analysis. "
                "Look for hedging phrases, defensive repetition, unusual pause markers, "
                "deviations from boilerplate forward-guidance, and any signs of cognitive "
                "stress in sentence structure. Map these signals to a hawkish/neutral/dovish "
                "monetary policy stance and estimate the implied 12-month rate path delta in bps."
            )
        else:
            body = (
                "[NO DATA] Neither a press conference image nor a speech transcript was provided. "
                "Return signal=neutral, rate_path_delta_bps=0, confidence=0.1, and note the "
                "absence of input in reasoning."
            )
        return body

    async def _call_claude(self, ctx: AgentContext, temperature: float = 1.0) -> AgentResult:
        """Override to set limited_mode on the result."""
        result = await super()._call_claude(ctx, temperature)
        result.limited_mode = True  # always text-only (no image support in CLI mode)
        return result


agent = AgentBehavioral()
