import anthropic
from backend.config import settings


async def justify_change(
    new_delta: float,
    prev_delta: float,
    event: dict | None,
    agent_results: list[dict],
) -> str:
    """Generate a one-line explanation for a forecast change."""
    change_bps = new_delta - prev_delta
    direction = "인하" if change_bps < 0 else "인상"

    # Find the top-contributing agents
    top_agents = sorted(agent_results, key=lambda r: abs(r["rate_path_delta_bps"]), reverse=True)[:3]
    agent_summary = ", ".join(
        f"{r['agent_name']}({r['rate_path_delta_bps']:+.0f}bps)"
        for r in top_agents
    )

    if event:
        return f"{event['label']} — {abs(change_bps):.0f} bps {direction} 조정 (주요 드라이버: {agent_summary})"

    # Ask Claude for a concise justification
    import asyncio
    prompt = f"""The Fed rate forecast changed by {change_bps:+.0f} bps (from {prev_delta:+.0f} to {new_delta:+.0f}).
Top contributing agents: {agent_summary}
Write ONE Korean sentence (under 60 characters) explaining the most likely reason for this change.
Output only the sentence, no punctuation other than necessary."""

    loop = asyncio.get_event_loop()
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    result = await loop.run_in_executor(
        None,
        lambda: client.messages.create(
            model=settings.MODEL_ID,
            max_tokens=80,
            messages=[{"role": "user", "content": prompt}],
        ).content[0].text.strip(),
    )
    return result
