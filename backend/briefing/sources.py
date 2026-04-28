"""
Source registry for Daily Macro News Briefing.
All sources use publicly accessible RSS feeds — no paywalls, no login walls.
"""
from dataclasses import dataclass, field
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
    # ── Official U.S. Government Sources ──────────────────────────────────
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
        id="treasury_press",
        name="U.S. Treasury Press Releases",
        category="official",
        feed_url="https://home.treasury.gov/system/files/press-releases.rss.xml",
        access_type="rss",
        enabled=True,
        reliability_weight=1.0,
        topic_tags=["treasury", "fiscal_policy", "bonds"],
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
        id="ny_fed",
        name="NY Fed Liberty Street Economics",
        category="official",
        feed_url="https://libertystreeteconomics.newyorkfed.org/feeds/index.xml",
        access_type="rss",
        enabled=True,
        reliability_weight=0.95,
        topic_tags=["fed", "monetary_policy", "financial_markets"],
        max_items=8,
    ),
    NewsSource(
        id="fred_blog",
        name="FRED Blog (St. Louis Fed)",
        category="official",
        feed_url="https://fredblog.stlouisfed.org/feed/",
        access_type="rss",
        enabled=True,
        reliability_weight=0.9,
        topic_tags=["monetary_policy", "macro_data"],
        max_items=8,
    ),

    # ── Macro Analysis Blogs (free, high quality) ─────────────────────────
    NewsSource(
        id="calculated_risk",
        name="Calculated Risk",
        category="analysis",
        feed_url="https://www.calculatedriskblog.com/feeds/posts/default",
        access_type="rss",
        enabled=True,
        reliability_weight=0.9,
        topic_tags=["growth", "labor_market", "housing", "financial_markets"],
        max_items=15,
    ),
    NewsSource(
        id="econbrowser",
        name="Econbrowser",
        category="analysis",
        feed_url="https://econbrowser.com/feed",
        access_type="rss",
        enabled=True,
        reliability_weight=0.85,
        topic_tags=["macro_data", "monetary_policy", "growth"],
        max_items=10,
    ),

    # ── Financial News RSS ────────────────────────────────────────────────
    NewsSource(
        id="marketwatch_econ",
        name="MarketWatch Economy & Politics",
        category="news",
        feed_url="https://feeds.marketwatch.com/marketwatch/economy-politics/",
        access_type="rss",
        enabled=True,
        reliability_weight=0.75,
        topic_tags=["financial_markets", "monetary_policy", "fiscal_policy"],
        max_items=20,
    ),
    NewsSource(
        id="reuters_business",
        name="Reuters Business",
        category="news",
        feed_url="https://feeds.reuters.com/reuters/businessNews",
        access_type="rss",
        enabled=True,
        reliability_weight=0.8,
        topic_tags=["financial_markets", "equities", "risk_sentiment"],
        max_items=20,
    ),
    NewsSource(
        id="reuters_money",
        name="Reuters Money & Markets",
        category="news",
        feed_url="https://feeds.reuters.com/reuters/MostRead",
        access_type="rss",
        enabled=True,
        reliability_weight=0.8,
        topic_tags=["bonds", "financial_markets", "risk_sentiment"],
        max_items=15,
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
}
