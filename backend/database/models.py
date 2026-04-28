from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

HORIZONS = ("6m", "12m", "3y", "10y")


def now_utc():
    return datetime.utcnow()


class RunLog(Base):
    __tablename__ = "run_log"
    id = Column(Integer, primary_key=True)
    started_at = Column(DateTime, default=now_utc)
    completed_at = Column(DateTime)
    status = Column(String(20), default="running")
    cycle_type = Column(String(20), default="scheduled")
    collaboration_rounds = Column(Integer, default=1)
    outputs = relationship("AgentOutput", back_populates="run", cascade="all, delete-orphan")
    mock_trades = relationship("MockTrade", back_populates="run", cascade="all, delete-orphan")
    horizon_forecasts = relationship("HorizonForecast", back_populates="run", cascade="all, delete-orphan")


class AgentOutput(Base):
    __tablename__ = "agent_output"
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("run_log.id"))
    agent_id = Column(Integer)
    agent_name = Column(String(50))
    round = Column(Integer, default=1)          # 1=independent, 2=post-collaboration
    signal = Column(String(20))
    rate_path_delta_bps = Column(Float)         # 12m for backward compat
    horizons_json = Column(Text)                # JSON: {6m, 12m, 3y, 10y}
    confidence = Column(Float)
    weight_applied = Column(Float)
    duration_ms = Column(Integer)
    limited_mode = Column(Boolean, default=False)
    raw_json = Column(Text)
    run = relationship("RunLog", back_populates="outputs")


class HorizonForecast(Base):
    """One record per horizon (6m/12m/3y/10y) per cycle."""
    __tablename__ = "horizon_forecast"
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("run_log.id"))
    horizon = Column(String(5))                 # 6m|12m|3y|10y
    published_at = Column(DateTime, default=now_utc)
    target_date = Column(String(10))
    raw_delta_bps = Column(Float)
    smoothed_delta = Column(Float)
    published_delta = Column(Float)
    confidence = Column(Float)
    signal = Column(String(20))
    trigger_event = Column(String(20))
    unchanged_streak_days = Column(Integer, default=0)
    change_justification = Column(Text)
    is_published = Column(Boolean, default=False)
    report_text = Column(Text)                  # Korean derivation report
    report_text_en = Column(Text)               # English derivation report
    run = relationship("RunLog", back_populates="horizon_forecasts")


# Keep PublishedForecast for backward-compat (= 12m horizon)
class PublishedForecast(Base):
    __tablename__ = "published_forecast"
    id = Column(Integer, primary_key=True)
    published_at = Column(DateTime, default=now_utc)
    target_date = Column(String(10))
    raw_delta_bps = Column(Float)
    smoothed_delta = Column(Float)
    published_delta = Column(Float)
    confidence = Column(Float)
    trigger_event = Column(String(20))
    unchanged_streak_days = Column(Integer, default=0)
    change_justification = Column(Text)
    is_published = Column(Boolean, default=False)


class DataCollectionSnapshot(Base):
    """Web-scraped data stored every 30 min without AI tokens."""
    __tablename__ = "data_collection_snapshot"
    id = Column(Integer, primary_key=True)
    collected_at = Column(DateTime, default=now_utc)
    macro_json = Column(Text)       # FRED series data
    speeches_json = Column(Text)    # Fed speeches list
    minutes_json = Column(Text)     # FOMC minutes texts
    beige_book_text = Column(Text)
    regional_json = Column(Text)
    cme_json = Column(Text)
    has_new_data = Column(Boolean, default=True)


class FeedbackEntry(Base):
    __tablename__ = "feedback_entry"
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("run_log.id"))
    agent_id = Column(Integer)
    error_type = Column(String(50))
    predicted_delta = Column(Float)
    actual_delta = Column(Float)
    divergence_bps = Column(Float)
    negative_example_text = Column(Text)
    created_at = Column(DateTime, default=now_utc)
    injected_at = Column(DateTime)
    curated_by_admin = Column(Boolean, default=False)


class MockTrade(Base):
    __tablename__ = "mock_trade"
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("run_log.id"))
    instrument = Column(String(20))
    direction = Column(String(10))
    entry_rate = Column(Float)
    exit_rate = Column(Float)
    pnl = Column(Float)
    rationale = Column(Text)
    created_at = Column(DateTime, default=now_utc)
    run = relationship("RunLog", back_populates="mock_trades")


# ── Daily Macro News Briefing tables ────────────────────────────────────────

class DailyBriefing(Base):
    __tablename__ = "daily_briefing"
    id = Column(Integer, primary_key=True)
    briefing_date = Column(String(10), nullable=False)       # "2026-04-28"
    language = Column(String(5), nullable=False)             # "en" | "ko"
    timezone = Column(String(50), default="Asia/Seoul")
    title = Column(String(500))
    market_impact_headline = Column(String(500))
    executive_summary_json = Column(Text)                    # JSON array of strings
    body_json = Column(Text)                                 # Full LLM JSON response
    sources_json = Column(Text)                              # JSON array of source metadata
    source_count = Column(Integer, default=0)
    article_count = Column(Integer, default=0)
    model_used = Column(String(100))
    status = Column(String(20), default="draft")             # draft|published|failed
    generation_started_at = Column(DateTime)
    generation_finished_at = Column(DateTime)
    created_at = Column(DateTime, default=now_utc)
    updated_at = Column(DateTime, default=now_utc)
    __table_args__ = (
        UniqueConstraint("briefing_date", "language", name="uq_briefing_date_lang"),
    )
    articles = relationship("BriefingArticle", back_populates="briefing", cascade="all, delete-orphan")


class NewsArticle(Base):
    __tablename__ = "news_article"
    id = Column(Integer, primary_key=True)
    source_id = Column(String(100))
    source_name = Column(String(200))
    title = Column(String(1000))
    url = Column(String(2000))
    canonical_url = Column(String(2000), unique=True)
    author = Column(String(500))
    published_at = Column(DateTime)
    fetched_at = Column(DateTime, default=now_utc)
    snippet = Column(Text)
    topic_tags_json = Column(Text)
    relevance_score = Column(Float, default=0.0)
    impact_score = Column(Float, default=0.0)
    cluster_id = Column(String(100))
    created_at = Column(DateTime, default=now_utc)
    briefings = relationship("BriefingArticle", back_populates="article")


class BriefingArticle(Base):
    __tablename__ = "briefing_article"
    id = Column(Integer, primary_key=True)
    briefing_id = Column(Integer, ForeignKey("daily_briefing.id"))
    article_id = Column(Integer, ForeignKey("news_article.id"))
    role = Column(String(20), default="primary")             # primary|supporting|background
    briefing = relationship("DailyBriefing", back_populates="articles")
    article = relationship("NewsArticle", back_populates="briefings")


class PipelineRun(Base):
    __tablename__ = "pipeline_run"
    id = Column(Integer, primary_key=True)
    run_type = Column(String(50))
    status = Column(String(20))                              # running|completed|failed
    started_at = Column(DateTime, default=now_utc)
    finished_at = Column(DateTime)
    error_message = Column(Text)
    logs_json = Column(Text)
    briefing_date = Column(String(10))
    language = Column(String(5))
