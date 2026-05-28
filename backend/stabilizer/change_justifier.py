from backend.claude_cli import call_claude


async def justify_change(
    new_delta: float,
    prev_delta: float,
    event: dict | None,
    agent_results: list[dict],
) -> str:
    """Generate a one-line explanation for a forecast change."""
    change_bps = new_delta - prev_delta
    direction = "인하" if change_bps < 0 else "인상"

    top_agents = sorted(agent_results, key=lambda r: abs(r["rate_path_delta_bps"]), reverse=True)[:3]
    agent_summary = ", ".join(
        f"{r['agent_name']}({r['rate_path_delta_bps']:+.0f}bps)"
        for r in top_agents
    )

    if event:
        return f"{event['label']} — {abs(change_bps):.0f} bps {direction} 조정 (주요 드라이버: {agent_summary})"

    prompt = f"""The Fed rate forecast changed by {change_bps:+.0f} bps (from {prev_delta:+.0f} to {new_delta:+.0f}).
Top contributing agents: {agent_summary}
Write ONE Korean sentence (under 60 characters) explaining the most likely reason for this change.
Output only the sentence, no punctuation other than necessary."""

    result = await call_claude(
        "You write concise Korean financial sentences. Output only the sentence requested.",
        prompt,
        timeout=30.0,
    )
    return result.strip()
