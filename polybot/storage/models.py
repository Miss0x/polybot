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

    # --- Serbia election pipeline 扩展列（见 db._migrate_schema）---
    feed_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source_class: Mapped[str | None] = mapped_column(String(32), nullable=True)   # core/realtime/corroboration
    tier: Mapped[str | None] = mapped_column(String(8), nullable=True)            # A1-A4
    lang: Mapped[str | None] = mapped_column(String(8), nullable=True)
    title_en: Mapped[str | None] = mapped_column(Text, nullable=True)             # 机翻英文标题（管线内语言）
    triage_relevant: Mapped[int | None] = mapped_column(Integer, nullable=True)   # 0/1/None=未分诊
    variable_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)    # 命中的关键变量列表
    novelty: Mapped[int | None] = mapped_column(Integer, nullable=True)           # 1-5 新颖度
    is_new_fact: Mapped[int | None] = mapped_column(Integer, nullable=True)       # 0/1 是否含新事实
    triage_method: Mapped[str | None] = mapped_column(String(32), nullable=True)  # rule_v1 / jev_v1
    triaged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


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


class PollORM(Base):
    """民调账本：结构化数字，机构偏差与口径逐条标注（ADR D15 原料）。"""

    __tablename__ = "polls"
    __table_args__ = (
        UniqueConstraint("pollster", "fieldwork_end", "party", name="uq_pollster_date_party"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pollster: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    bias: Mapped[str | None] = mapped_column(String(32), nullable=True)  # independent/centre_right_academic/pro_govt_accused/unknown
    fieldwork_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fieldwork_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=False, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sample_n: Mapped[int | None] = mapped_column(Integer, nullable=True)
    party: Mapped[str] = mapped_column(String(64), nullable=False)       # SNS / STU / SPS / ...
    pct: Mapped[float] = mapped_column(Float, nullable=False)
    method_note: Mapped[str | None] = mapped_column(Text, nullable=True)  # 口径说明（逐党/联盟）
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, nullable=False)


class VariableSnapshotORM(Base):
    """变量档案库：每日每个关键变量一行状态快照（Master Dossier 的数据层）。"""

    __tablename__ = "variable_snapshots"
    __table_args__ = (UniqueConstraint("election_id", "variable_id", "snapshot_date", name="uq_var_snapshot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    election_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    variable_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    snapshot_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD（本地日）
    state_text: Mapped[str] = mapped_column(Text, nullable=False)           # 当前状态描述
    change_flag: Mapped[str] = mapped_column(String(8), nullable=False, default="flat")  # up/down/flat/new
    evidence_news_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, nullable=False)


class JudgmentLogORM(Base):
    """决策日志：两段式（D13）——看价前 pre 看价后 post，复盘量化的原始数据。"""

    __tablename__ = "judgment_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    election_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    market_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, nullable=False)
    stage: Mapped[str] = mapped_column(String(8), nullable=False)           # pre / post
    direction: Mapped[str | None] = mapped_column(String(16), nullable=True)  # sns / students / other
    intent_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

