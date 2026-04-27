"""
Agent 05 — Projections
Decodes Fed SEP (Dot Plot) and Beige Book regional economic conditions
to infer the FOMC policy path and identify regional divergence signals.

NOTE: Dot Plot data must be manually updated by the admin in the macro snapshot.
      This agent reads the Beige Book text and any dot plot summary provided in context.
"""

from backend.agents.base_agent import BaseAgent, AgentContext, AgentResult, OUTPUT_SCHEMA


_SEP_AND_BEIGE_BOOK_REFERENCE = """
### ANALYTICAL FRAMEWORK: SEP DOT PLOT + BEIGE BOOK

DOT PLOT (Fed SEP — Summary of Economic Projections)
  - Published quarterly after the March, June, September, December FOMC meetings.
  - Each dot represents one FOMC participant's (anonymous) year-end Fed Funds Rate projection.
  - Key metrics to extract from admin-provided data:
      • Median dot for current year, next year, and longer run
      • Number of dots above vs. below current rate (hawkish/dovish balance)
      • Shift in median vs. previous SEP (hawkish shift = upward revision)
      • Dispersion (std dev) of dots — high dispersion = policy uncertainty
      • Longer-run dot (r* estimate) — if rising, signals higher terminal rate view
  - Interpretation:
      Dot plot median > current FFR → hikes still expected → hawkish
      Dot plot median < current FFR → cuts expected         → dovish
      Flat dot plot at current FFR  → on hold               → neutral

BEIGE BOOK (Regional Economic Conditions)
  - Published ~2 weeks before each FOMC meeting; 12 Federal Reserve District reports.
  - Districts: Boston, New York, Philadelphia, Cleveland, Richmond, Atlanta,
               Chicago, St. Louis, Minneapolis, Kansas City, Dallas, San Francisco.
  - Analytical approach:
      1. REGIONAL DIVERGENCE: Identify which districts report expansion vs. contraction.
         High divergence = policy complexity (one-size-fits-all rate harder to justify).
      2. INFLATION BREADTH: Count how many districts flag persistent vs. easing price pressures.
         Broad price pressure → hawkish lean; broad easing → dovish lean.
      3. LABOR MARKET: Districts reporting tight labor / wage acceleration vs. softening.
      4. CONSUMER SPENDING: Districts noting strong vs. weak retail/services activity.
      5. CREDIT CONDITIONS: Districts flagging tightening credit / declining loan demand.
      6. TONE SHIFT: Compare current Beige Book tone to prior description if available
         (e.g., shift from "modest growth" to "slight decline" is a meaningful signal).
  - Map regional findings to an aggregate policy signal:
      Majority districts: expansion + inflation = hawkish
      Majority districts: stagnation + easing prices = dovish
      Mixed signals across districts = neutral / high uncertainty

COMBINED SIGNAL LOGIC
  Weight Dot Plot and Beige Book equally. If they conflict, lower confidence and
  note the tension. The Dot Plot is more forward-looking; Beige Book is more real-time.
"""


class AgentProjections(BaseAgent):
    agent_id = 5
    agent_name = "Projections"
    weight = 1.1

    def _system_prompt(self) -> str:
        return (
            "You are a senior Federal Reserve analyst with deep expertise in reading the Fed's "
            "Summary of Economic Projections (SEP / Dot Plot) and the Beige Book regional "
            "economic condition reports.\n\n"
            "Your role is to synthesize forward-looking FOMC projections with on-the-ground "
            "regional economic evidence to produce a coherent policy path forecast.\n\n"
            "Key capabilities:\n"
            "  - Extract policy signals from Dot Plot median shifts, dispersion, and longer-run "
            "    rate estimates.\n"
            "  - Identify regional economic divergence in the Beige Book that may complicate "
            "    or clarify the rate path.\n"
            "  - Detect tone shifts in Beige Book language (e.g., 'slight' → 'modest' → 'moderate' "
            "    is an expansion signal; the reverse is a contraction signal).\n"
            "  - Reconcile SEP projections with Beige Book reality to flag credibility gaps.\n\n"
            "IMPORTANT: Dot Plot data is manually maintained by the admin. If no Dot Plot data "
            "is present in the macro snapshot, note this explicitly but still analyze the "
            "Beige Book independently.\n\n"
            + _SEP_AND_BEIGE_BOOK_REFERENCE
            + "\n\n"
            + OUTPUT_SCHEMA
        )

    def _user_message(self, ctx: AgentContext) -> str:
        sections = []

        if ctx.beige_book_text:
            sections.append(
                "### Beige Book — Regional Economic Conditions\n\n"
                + ctx.beige_book_text.strip()
            )
        else:
            sections.append(
                "### Beige Book\n[NOT PROVIDED — no Beige Book text available for this cycle.]"
            )

        if ctx.macro_snapshot_text:
            sections.append(
                "### Macro Snapshot (includes any admin-provided Dot Plot summary)\n\n"
                + ctx.macro_snapshot_text.strip()
            )
        else:
            sections.append(
                "### Macro Snapshot / Dot Plot\n"
                "[NOT PROVIDED — Dot Plot data must be manually entered by admin. "
                "Analyze Beige Book only.]"
            )

        data_block = "\n\n".join(sections)

        instructions = (
            "\n\nInstructions:\n"
            "1. DOT PLOT ANALYSIS: If Dot Plot data is present in the macro snapshot, extract "
            "   the median dot for current year and next year, count hawkish vs. dovish dots, "
            "   note any shift from the prior SEP, and assess the longer-run rate estimate. "
            "   If absent, note that admin update is required.\n"
            "2. BEIGE BOOK ANALYSIS: Tally regional stances across the 12 districts. "
            "   Count districts showing expansion vs. contraction. "
            "   Identify breadth of inflation pressure and labor market tightness. "
            "   Note any districts showing notable divergence from the national picture.\n"
            "3. REGIONAL DIVERGENCE SIGNAL: Flag if more than 3 districts show meaningfully "
            "   different conditions (strong vs. weak), which complicates a uniform rate path.\n"
            "4. COMBINED POLICY PATH: Synthesize Dot Plot and Beige Book into a single "
            "   hawkish/neutral/dovish signal with 12-month rate path delta in bps.\n"
            "5. CONFIDENCE: Lower confidence if Dot Plot is missing or if regional signals conflict.\n"
            "Respond strictly in the required JSON format."
        )

        return data_block + instructions


agent = AgentProjections()
