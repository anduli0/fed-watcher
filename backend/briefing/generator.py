"""
LLM briefing generation using the Claude CLI.
Generates both EN and KO versions from the same article set.
"""
from __future__ import annotations
import json
import logging
from typing import Literal

from backend.briefing.fetcher import ArticleData
from backend.claude_cli import call_claude
from backend.config import settings

logger = logging.getLogger("fed_watcher.briefing.generator")

LangCode = Literal["en", "ko"]

# Output schema the LLM must return
OUTPUT_SCHEMA = {
    "title": "string — 1-line briefing title",
    "marketImpactHeadline": "string — 1-sentence market impact summary",
    "executiveSummary": ["string — bullet 1", "string — bullet 2", "... 5-7 bullets"],
    "sections": [
        {
            "heading": "string — section heading",
            "body": "string — 1-3 short paragraphs, synthesized prose",
            "sourceIds": ["src_id_1", "src_id_2"],
        }
    ],
    "whatChangedSinceYesterday": ["string — 3-5 bullets on shifts vs prior day"],
    "fedWatcherRatePathSignal": "string — 1-3 paragraphs on rate path implications",
    "watchNext": ["string — 3-5 upcoming events or data releases to monitor"],
    "disclaimer": "string — standard disclaimer",
}

SECTION_HEADINGS = {
    "en": [
        "U.S. Treasury Yields & Bond Market",
        "Federal Reserve & Monetary Policy",
        "Fiscal Policy & Treasury Issuance",
        "Financial Markets & Risk Sentiment",
        "Industry & Corporate Developments",
        "Equities & Sector Rotation",
        "Key Risks to Monitor",
    ],
    "ko": [
        "미국 국채 금리 · 채권 시장",
        "연준 · 통화 정책",
        "재정 정책 · 국채 발행",
        "금융 시장 · 위험 선호",
        "산업 · 기업 동향",
        "주식 · 섹터 로테이션",
        "주요 리스크",
    ],
}

SYSTEM_PROMPT = """You are the editorial engine for FED-WATCHER, a macroeconomic rate-path intelligence dashboard.
Your task: write a daily macro-financial news briefing based ONLY on the provided source articles.
Your audience: sophisticated macro readers who follow the Fed, Treasury market, macro data, and financial markets — but do not want to read dozens of articles.

Editorial standards:
- SYNTHESIZE and COMPRESS. Do not produce an article-by-article dump.
- Every factual claim must be traceable to at least one source article.
- Distinguish confirmed facts from market interpretation. Label interpretations clearly.
- Do NOT hallucinate facts, statistics, or official statements.
- Do NOT give investment advice. Avoid phrases like "you should buy/sell".
- Focus on implications for: U.S. rates, inflation, growth, liquidity, risk sentiment, financial conditions.
- Mention uncertainty where it exists.
- Be concise but substantive. Prefer precise over vague language."""


def _format_articles_for_prompt(articles: list[ArticleData]) -> str:
    """Format article list as numbered text block for the LLM prompt."""
    lines = []
    for i, art in enumerate(articles, 1):
        pub_str = ""
        if art["published_at"]:
            pub_str = art["published_at"].strftime("%Y-%m-%d %H:%M UTC")
        lines.append(
            f'[{i}] {art["source_id"]}\n'
            f'Title: {art["title"]}\n'
            f'Source: {art["source_name"]}\n'
            f'Published: {pub_str}\n'
            f'Tags: {", ".join(art["topic_tags"])}\n'
            f'Excerpt: {art["snippet"]}\n'
            f'URL: {art["url"]}\n'
        )
    return "\n".join(lines)


def _build_user_prompt(articles: list[ArticleData], lang: LangCode) -> str:
    lang_instruction = (
        "Write the ENTIRE briefing in polished ENGLISH suitable for an English-speaking macro-financial reader. "
        "All section headings, labels, bullets, and prose must be in English."
        if lang == "en" else
        "Write the ENTIRE briefing in polished KOREAN (한국어) suitable for a Korean macro-financial reader. "
        "Use natural Korean financial-market and macroeconomic prose — NOT literal translation. "
        "All section headings, labels, bullets, and prose must be in Korean (한국어)."
    )

    sections_list = "\n".join(f"- {h}" for h in SECTION_HEADINGS[lang])

    schema_str = json.dumps(OUTPUT_SCHEMA, ensure_ascii=False, indent=2)

    articles_block = _format_articles_for_prompt(articles)

    length_guide = (
        "Target length: 800–1,200 words total. Each section body: 1-2 short paragraphs (60-120 words each)."
        if lang == "en" else
        "목표 분량: 전체 800–1,200단어. 각 섹션 본문: 단락 1-2개 (각 60-120자 수준)."
    )

    return f"""LANGUAGE: {lang_instruction}

{length_guide}

REQUIRED SECTIONS (use these headings in your response):
{sections_list}

OUTPUT FORMAT — respond with ONLY valid JSON matching this schema (no prose before or after):
{schema_str}

Rules for each field:
- "title": 1 line, like a newspaper headline for this date
- "marketImpactHeadline": 1 sentence, most important macro development
- "executiveSummary": 5-7 bullets, the non-negotiable takeaways
- "sections": exactly 7 sections matching the headings above, in order
  - "body": synthesized prose (1-3 paragraphs), NOT a list of article summaries
  - "sourceIds": article IDs like "fed_press", "calculated_risk" used in that section
- "whatChangedSinceYesterday": 3-5 bullets on shifts vs the prior day's narrative
- "fedWatcherRatePathSignal": how today's news flow may affect Fed rate expectations (1-3 paragraphs)
- "watchNext": 3-5 specific upcoming events, data releases, or Fed communications to watch
- "disclaimer": one-sentence standard disclaimer

SOURCE ARTICLES ({len(articles)} total):
{articles_block}

Generate the briefing now. Return ONLY the JSON object."""


async def generate_briefing(
    articles: list[ArticleData],
    lang: LangCode,
    model: str | None = None,
) -> dict:
    """
    Call Claude to generate a structured briefing in the given language.
    Returns the parsed JSON dict from the LLM.
    Raises ValueError if the output fails validation.
    """
    user_msg = _build_user_prompt(articles, lang)

    logger.info("Generating %s briefing with %d articles via claude CLI", lang.upper(), len(articles))

    raw = await call_claude(SYSTEM_PROMPT, user_msg, timeout=180.0)

    # Extract JSON (robust: handle any preamble, truncation, or special chars)
    import re

    # Find JSON object start
    start = raw.find("{")
    if start == -1:
        raise ValueError(f"LLM returned no JSON for lang={lang}. Raw: {raw[:400]}")

    json_str = raw[start:]

    # Try direct parse first
    data = None
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        # Try to repair truncated JSON by finding the last complete section
        # Strip trailing incomplete content and close the object
        try:
            # Find the deepest balanced closing — try progressively shorter strings
            for end in range(len(json_str), len(json_str) // 2, -1):
                try:
                    data = json.loads(json_str[:end])
                    break
                except json.JSONDecodeError:
                    continue
        except Exception:
            pass

    if data is None:
        raise ValueError(f"LLM JSON parse error for lang={lang}. Raw start: {json_str[:500]}")

    # Validate required fields
    required = ["title", "marketImpactHeadline", "executiveSummary", "sections",
                "whatChangedSinceYesterday", "fedWatcherRatePathSignal", "watchNext"]
    for field in required:
        if field not in data:
            raise ValueError(f"LLM output missing required field: {field}")

    if not data.get("sections"):
        raise ValueError("LLM output has empty sections")

    logger.info("Generated %s briefing: %d sections, title='%s'",
                lang.upper(), len(data["sections"]), data.get("title", "?")[:60])
    return data
