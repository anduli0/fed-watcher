"""
Agent 10 — Consensus
Synthesises CME FedWatch market-implied rate probabilities against Wall Street
institutional consensus to identify whether markets are ahead of or behind Fed guidance.
"""

from backend.agents.base_agent import BaseAgent, AgentContext, AgentResult, OUTPUT_SCHEMA


class AgentConsensus(BaseAgent):
    agent_id = 10
    agent_name = "Consensus"
    weight = 1.5
    enable_thinking = True
    self_consistency_n = 2  # market consensus is high-stakes — sample twice

    def _system_prompt(self) -> str:
        return (
            "You are an expert in market microstructure and institutional consensus formation, "
            "specialising in Fed Funds rate pricing, interest rate derivatives, and Wall Street "
            "bank forecast aggregation.\n\n"
            "YOUR ANALYTICAL TOOLKIT:\n\n"
            "CME FEDWATCH INTERPRETATION:\n"
            "  - CME FedWatch probabilities are derived from 30-Day Fed Funds futures contracts. "
            "    They represent the market's probability-weighted expectation for the EFFR at each "
            "    FOMC meeting date.\n"
            "  - Key reading technique: compute the IMPLIED RATE PATH by taking probability-weighted "
            "    averages across meeting dates. Compare meeting-to-meeting deltas to identify "
            "    where the market prices the first cut/hike and how many moves are priced in total.\n"
            "  - Conviction signals: >75% probability for any single outcome = high conviction; "
            "    50-75% = moderate conviction; <50% = genuinely uncertain, market is split.\n"
            "  - Watch for BIMODAL distributions (e.g. 40% cut / 35% hold / 25% hike) — these "
            "    indicate event-driven uncertainty (upcoming CPI, NFP, or FOMC) rather than a "
            "    directional view.\n\n"
            "WALL STREET CONSENSUS RANGES (institutional priors — update from context):\n"
            "  - Major banks (JPMorgan, Goldman Sachs, BofA, Morgan Stanley, Citi, Wells Fargo, "
            "    Barclays, Deutsche Bank, UBS) publish quarterly rate forecasts.\n"
            "  - Typical consensus range: ±25-50 bps around median. When market pricing deviates "
            "    more than 50 bps from bank consensus median, historically one of them tends to "
            "    be wrong — and the market is more often right at 3-month horizons, while banks "
            "    are more reliable at 12-month horizons.\n"
            "  - 'Street consensus' vs 'market pricing' divergence > 50 bps = actionable signal.\n\n"
            "AHEAD / BEHIND FRAMEWORK:\n"
            "  - Market AHEAD of Fed: Market prices more cuts (or fewer hikes) than the Fed's "
            "    dot plot / public guidance. Common in easing cycles — market leads by 1-2 meetings.\n"
            "  - Market BEHIND Fed: Market prices fewer cuts (or more hikes) than guidance suggests. "
            "    Common when Fed pivots suddenly or data surprises sharply.\n"
            "  - ALIGNED: Market within 25 bps of Fed dot plot median — no alpha in positioning.\n\n"
            "Always output strictly valid JSON matching the schema provided."
        )

    def _user_message(self, ctx: AgentContext) -> str:
        if not ctx.cme_probabilities:
            cme_block = "NO CME FEDWATCH DATA PROVIDED — return signal='neutral', confidence=0.2."
        else:
            # Format the dict into readable text for the model
            lines = ["CME FedWatch Meeting Probabilities:"]
            for meeting_date, probs in ctx.cme_probabilities.items():
                lines.append(f"\n  Meeting: {meeting_date}")
                if isinstance(probs, dict):
                    for outcome, probability in probs.items():
                        # Support both float (0.0-1.0) and percentage strings
                        if isinstance(probability, float) and probability <= 1.0:
                            pct = f"{probability * 100:.1f}%"
                        else:
                            pct = f"{probability}"
                        lines.append(f"    {outcome}: {pct}")
                else:
                    lines.append(f"    {probs}")
            cme_block = "\n".join(lines)

        instructions = (
            "Analyse the CME FedWatch market-implied probabilities below and synthesise a consensus assessment.\n\n"
            "REQUIRED STEPS:\n"
            "1. RATE PATH EXTRACTION: From the FedWatch probabilities, compute the probability-weighted "
            "   implied rate for each meeting date. Identify: (a) the next expected policy move and "
            "   its meeting date, (b) total number of cuts/hikes priced over 12 months, "
            "   (c) the terminal rate implied by the probability distribution.\n"
            "2. CONVICTION ASSESSMENT: For each meeting, classify market conviction as "
            "   high (>75%), moderate (50-75%), or low/split (<50%). Note any bimodal distributions.\n"
            "3. WALL STREET COMPARISON: Based on your knowledge of current major-bank consensus "
            "   forecasts, compare the market-implied path to institutional consensus. "
            "   State the approximate divergence in basis points and its direction.\n"
            "4. AHEAD / BEHIND / ALIGNED: Classify the market's position relative to Fed guidance "
            "   (dot plot / recent FOMC communications). Quantify the divergence.\n"
            "5. SIGNAL EXTRACTION: Determine whether the consensus picture is net hawkish, neutral, "
            "   or dovish for the 12-month policy rate outlook. A market pricing more cuts than "
            "   guidance = dovish signal (negative delta); fewer cuts / more hikes = hawkish.\n"
            "6. RATE PATH DELTA: Express the net market-implied adjustment vs the current rate "
            "   in basis points (negative = net cuts priced). Typical range: -150 to +75 bps.\n\n"
            f"{OUTPUT_SCHEMA}\n\n"
            "--- CME FEDWATCH DATA ---\n"
            f"{cme_block}"
        )
        return instructions


agent = AgentConsensus()
