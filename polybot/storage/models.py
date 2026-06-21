from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from polybot.storage.db import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class MarketORM(Base):
    __tablename__ = "markets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    slug: Mapped[str | None] = mapped_column(String(255), nullable=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subcategory: Mapped[str | None] = mapped_column(String(64), nullable=True)
    condition_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcomes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    clob_token_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_event_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_market_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, nullable=False)


class SnapshotORM(Base):
    __tablename__ = "snapshots"
    __table_args__ = (UniqueConstraint("market_id", "ts", name="uq_snapshot_market_ts"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    yes_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_24h: Mapped[float | None] = mapped_column(Float, nullable=True)
    liquidity: Mapped[float | None] = mapped_column(Float, nullable=True)


class NewsItemORM(Base):
    __tablename__ = "news_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    title_simhash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    board_tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, nullable=False)


class NewsEventORM(Base):
    __tablename__ = "news_events"
    __table_args__ = (UniqueConstraint("news_id", "event_type", name="uq_news_event_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    news_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actors_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    certainty: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    time_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    evidence_sentence: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_keywords_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_method: Mapped[str] = mapped_column(String(32), nullable=False, default="rule_v1")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, nullable=False)


class MarketProfileORM(Base):
    __tablename__ = "market_profiles"

    market_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subjects_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    actions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    objects_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    aliases_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    positive_signals_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    negative_signals_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_terms_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ambiguous_terms_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    edge_cases_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    deadline_utc: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    generated_method: Mapped[str] = mapped_column(String(32), nullable=False, default="rule_v1")
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, nullable=False)
    raw_profile_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class NewsMarketLinkORM(Base):
    __tablename__ = "news_market_links"
    __table_args__ = (UniqueConstraint("news_id", "market_id", name="uq_news_market_link"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    news_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    market_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    relevance: Mapped[float] = mapped_column(Float, nullable=False)
    direction: Mapped[int] = mapped_column(Integer, nullable=False)
    strength: Mapped[float] = mapped_column(Float, nullable=False)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    evidence_type: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    layer: Mapped[str] = mapped_column(String(32), nullable=False, default="L1_RULE")
    llm_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, nullable=False)

