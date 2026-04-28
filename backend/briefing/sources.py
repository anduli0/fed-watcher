"""
Source registry for Daily Macro News Briefing.
All sources use publicly accessible RSS feeds — no paywalls, no login walls.
"""
from dataclasses import dataclass
from typing import Literal


@dataclass
class NewsSource:
    id: str
    name: str
    category: str                   # "official" | "analysis" | "news"
    feed_url: str
    access_type: Literal["rss"]
    enabled: bool
    reliability_weight: float       # 0.0–1.0
    topic_tags: list[str]
    max_items: int = 20


SOURCES: list[NewsSource] = [
    # ── Official U.S. Government Sources ─────────────────────────────────
    # These publish infrequently → 7-day lookback in fetcher
    NewsSource(
        id="fed_press",
        name="Federal Reserve Press Releases",
        category="official",
        feed_url="https://www.federalreserve.gov/feeds/press_all.xml",
        access_type="rss",
        enabled=True,
        reliability_weight=1.0,
        topic_tags=["fed", "monetary_policy"],
        max_items=10,
    ),
    NewsSource(
        id="fed_speeches",
        name="Federal Reserve Speeches",
        category="official",
        feed_url="https://www.federalreserve.gov/feeds/speeches.xml",
        access_type="rss",
        enabled=True,
        reliability_weight=1.0,
        topic_tags=["fed", "monetary_policy"],
        max_items=10,
    ),
    NewsSource(
        id="bls_latest",
        name="Bureau of Labor Statistics",
        category="official",
        feed_url="https://www.bls.gov/feed/bls_latest.rss",
        access_type="rss",
        enabled=True,
        reliability_weight=1.0,
        topic_tags=["labor_market", "inflation"],
        max_items=10,
    ),
    NewsSource(
        id="fred_blog",
        name="FRED Blog (St. Louis Fed)",
        category="official",
        feed_url="https://fredblog.stlouisfed.org/feed/",
        access_type="rss",
        enabled=True,
        reliability_weight=0.95,
        topic_tags=["monetary_policy", "macro_data"],
        max_items=10,
    ),

    # ── High-Quality Macro Analysis (blog-based, cloud-friendly) ─────────
    NewsSource(
        id="econbrowser",
        name="Econbrowser",
        category="analysis",
        feed_url="https://econbrowser.com/feed",
        access_type="rss",
        enabled=True,
        reliability_weight=0.9,
        topic_tags=["macro_data", "monetary_policy", "growth"],
        max_items=15,
    ),
    NewsSource(
        id="bruegel",
        name="Bruegel Economic Policy",
        category="analysis",
        feed_url="https://www.bruegel.org/feed",
        access_type="rss",
        enabled=True,
        reliability_weight=0.85,
        topic_tags=["monetary_policy", "fiscal_policy", "financial_markets"],
        max_items=10,
    ),
    NewsSource(
        id="brookings_econ",
        name="Brookings Institution",
        category="analysis",
        feed_url="https://www.brookings.edu/topic/economy-development/feed/",
        access_type="rss",
        enabled=True,
        reliability_weight=0.85,
        topic_tags=["fiscal_policy", "monetary_policy", "growth"],
        max_items=10,
    ),

    # ── Yahoo Finance RSS (very reliable from cloud, broad coverage) ──────
    NewsSource(
        id="yahoo_finance_top",
        name="Yahoo Finance Top Stories",
        category="news",
        feed_url="https://finance.yahoo.com/rss/topfinstories",
        access_type="rss",
        enabled=True,
        reliability_weight=0.75,
        topic_tags=["financial_markets", "equities", "risk_sentiment"],
        max_items=20,
    ),
    NewsSource(
        id="yahoo_econ",
        name="Yahoo Finance Economy",
        category="news",
        feed_url="https://finance.yahoo.com/rss/2.0/headline?s=%5EIRX&region=US&lang=en-US",
        access_type="rss",
        enabled=True,
        reliability_weight=0.7,
        topic_tags=["financial_markets", "bonds", "monetary_policy"],
        max_items=15,
    ),

    # ── NPR Economy (public radio, cloud-friendly) ────────────────────────
    NewsSource(
        id="npr_economy",
        name="NPR Economy",
        category="news",
        feed_url="https://feeds.npr.org/1017/rss.xml",
        access_type="rss",
        enabled=True,
        reliability_weight=0.75,
        topic_tags=["macro_data", "labor_market", "monetary_policy"],
        max_items=15,
    ),

    # ── VOA Business News (public, cloud-friendly) ────────────────────────
    NewsSource(
        id="voa_business",
        name="VOA Business News",
        category="news",
        feed_url="https://feeds.voanews.com/voaeconomy",
        access_type="rss",
        enabled=True,
        reliability_weight=0.65,
        topic_tags=["financial_markets", "risk_sentiment"],
        max_items=15,
    ),

    # ── The Conversation Economics (academic, cloud-friendly) ─────────────
    NewsSource(
        id="theconversation",
        name="The Conversation — Economics",
        category="analysis",
        feed_url="https://theconversation.com/us/topics/economics-67/articles.atom",
        access_type="rss",
        enabled=True,
        reliability_weight=0.7,
        topic_tags=["macro_data", "monetary_policy", "growth"],
        max_items=10,
    ),

    # ── Project Syndicate (Summers, Rogoff, Stiglitz etc.) ────────────────
    NewsSource(
        id="project_syndicate",
        name="Project Syndicate",
        category="analysis",
        feed_url="https://www.project-syndicate.org/rss",
        access_type="rss",
        enabled=True,
        reliability_weight=0.8,
        topic_tags=["monetary_policy", "fiscal_policy", "growth"],
        max_items=10,
    ),
]

ENABLED_SOURCES = [s for s in SOURCES if s.enabled]

# Macro relevance keywords (used for scoring)
MACRO_KEYWORDS: dict[str, float] = {
    # Fed / Monetary policy — highest weight
    "federal reserve": 3.0, "fomc": 3.0, "fed chair": 3.0, "powell": 2.5,
    "monetary policy": 3.0, "interest rate": 2.5, "rate hike": 3.0,
    "rate cut": 3.0, "fed funds": 3.0, "basis points": 2.0,
    "quantitative tightening": 2.5, "balance sheet": 2.0,
    "taper": 2.0, "qe": 2.0, "qt": 2.0, "beige book": 2.5,
    "fomc minutes": 3.0, "press conference": 2.0,
    # Treasury / Bonds — high weight
    "treasury": 2.5, "yield": 2.5, "bond": 2.0, "10-year": 2.5,
    "2-year": 2.0, "yield curve": 3.0, "inversion": 2.5,
    "debt ceiling": 2.5, "deficit": 2.0, "auction": 2.0,
    # Inflation / Labor
    "inflation": 3.0, "cpi": 3.0, "pce": 3.0, "core inflation": 3.0,
    "jobs report": 2.5, "nonfarm payroll": 2.5, "unemployment": 2.5,
    "wage growth": 2.5, "labor market": 2.5,
    # Growth / GDP
    "gdp": 2.5, "recession": 3.0, "growth": 1.5, "ism": 2.0,
    "manufacturing": 1.5, "retail sales": 2.0, "housing": 1.5,
    # Markets / Risk
    "financial conditions": 2.5, "credit spread": 2.5, "vix": 2.0,
    "risk sentiment": 2.0, "dollar": 1.5, "risk-off": 2.0,
    "equities": 1.5, "s&p": 1.5, "nasdaq": 1.5, "sector rotation": 2.0,
    # Economy general
    "economy": 1.0, "economic": 1.0, "tariff": 2.0, "trade": 1.5,
    "fiscal": 2.0, "budget": 1.5, "tax": 1.5,
}
