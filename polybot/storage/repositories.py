from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select

from polybot.collect.news_source import NewsItem
from polybot.storage.models import MarketORM, MarketProfileORM, NewsEventORM, NewsItemORM, NewsMarketLinkORM, SnapshotORM


def upsert_market(
    session,
    market_id: str,
    slug: str | None,
    question: str,
    category: str | None,
    end_date,
    condition_id: str | None = None,
    description: str | None = None,
    subcategory: str | None = None,
    resolution_source: str | None = None,
    outcomes_json: str | None = None,
    clob_token_ids_json: str | None = None,
    raw_event_json: str | None = None,
    raw_market_json: str | None = None,
    updated_at=None,
):
    market = session.get(MarketORM, market_id)
    now = _utc_now()
    if market is None:
        market = MarketORM(
            id=market_id,
            slug=slug,
            question=question,
            category=category,
            subcategory=subcategory,
            condition_id=condition_id,
            description=description,
            resolution_source=resolution_source,
            outcomes_json=outcomes_json,
            clob_token_ids_json=clob_token_ids_json,
            raw_event_json=raw_event_json,
            raw_market_json=raw_market_json,
            end_date=end_date,
            updated_at=updated_at or now,
        )
        session.add(market)
    else:
        market.slug = slug
        market.question = question
        market.category = category
        market.subcategory = subcategory
        market.condition_id = condition_id
        market.description = description
        market.resolution_source = resolution_source
        market.outcomes_json = outcomes_json
        market.clob_token_ids_json = clob_token_ids_json
        market.raw_event_json = raw_event_json
        market.raw_market_json = raw_market_json
        market.end_date = end_date
        market.updated_at = updated_at or now
    return market


def insert_snapshot(session, market_id: str, ts: datetime, yes_price: float | None, volume_24h: float | None, liquidity: float | None):
    stmt = select(SnapshotORM).where(SnapshotORM.market_id == market_id, SnapshotORM.ts == ts)
    existing = session.execute(stmt).scalar_one_or_none()
    if existing is not None:
        return existing

    snapshot = SnapshotORM(
        market_id=market_id,
        ts=ts,
        yes_price=yes_price,
        volume_24h=volume_24h,
        liquidity=liquidity,
    )
    session.add(snapshot)
    return snapshot


def list_existing_news_url_hashes(session, board_id: str | None = None) -> set[str]:
    """返回数据库中已有的所有 url_hash 集合（用于精确去重）。"""
    stmt = select(NewsItemORM.url_hash)
    if board_id:
        stmt = stmt.where(NewsItemORM.board_tags == board_id)
    rows = session.execute(stmt).scalars().all()
    return set(rows)


def list_existing_news_simhashes(session, board_id: str | None = None) -> list[str]:
    """返回数据库中已有的所有 title_simhash 列表（用于近似去重）。"""
    stmt = select(NewsItemORM.title_simhash).where(NewsItemORM.title_simhash.isnot(None))
    if board_id:
        stmt = stmt.where(NewsItemORM.board_tags == board_id)
    rows = session.execute(stmt).scalars().all()
    return list(rows)


def insert_news_item(session, item: NewsItem, title_simhash: str | None, board_tags: str | None = None) -> NewsItemORM | None:
    """将一条新闻入库（幂等，URL hash 重复则返回 None）。"""
    stmt = select(NewsItemORM).where(NewsItemORM.url_hash == item.url_hash)
    existing = session.execute(stmt).scalar_one_or_none()
    if existing is not None:
        return None

    news_orm = NewsItemORM(
        url_hash=item.url_hash,
        title_simhash=title_simhash,
        title=item.title,
        url=item.url,
        source_name=item.source_name,
        published_at=item.published_at,
        raw_text=item.raw_text,
        board_tags=board_tags,
    )
    session.add(news_orm)
    return news_orm


def upsert_market_profile(
    session,
    market_id: str,
    subjects_json: str | None = None,
    actions_json: str | None = None,
    objects_json: str | None = None,
    aliases_json: str | None = None,
    positive_signals_json: str | None = None,
    negative_signals_json: str | None = None,
    context_terms_json: str | None = None,
    ambiguous_terms_json: str | None = None,
    edge_cases_json: str | None = None,
    deadline_utc: datetime | None = None,
    generated_method: str = "rule_v1",
    raw_profile_json: str | None = None,
) -> MarketProfileORM:
    """Upsert market profile."""
    profile = session.get(MarketProfileORM, market_id)
    now = _utc_now()
    if profile is None:
        profile = MarketProfileORM(
            market_id=market_id,
            subjects_json=subjects_json,
            actions_json=actions_json,
            objects_json=objects_json,
            aliases_json=aliases_json,
            positive_signals_json=positive_signals_json,
            negative_signals_json=negative_signals_json,
            context_terms_json=context_terms_json,
            ambiguous_terms_json=ambiguous_terms_json,
            edge_cases_json=edge_cases_json,
            deadline_utc=deadline_utc,
            generated_method=generated_method,
            generated_at=now,
            raw_profile_json=raw_profile_json,
        )
        session.add(profile)
    else:
        profile.subjects_json = subjects_json
        profile.actions_json = actions_json
        profile.objects_json = objects_json
        profile.aliases_json = aliases_json
        profile.positive_signals_json = positive_signals_json
        profile.negative_signals_json = negative_signals_json
        profile.context_terms_json = context_terms_json
        profile.ambiguous_terms_json = ambiguous_terms_json
        profile.edge_cases_json = edge_cases_json
        profile.deadline_utc = deadline_utc
        profile.generated_method = generated_method
        profile.generated_at = now
        profile.raw_profile_json = raw_profile_json
    return profile


def list_markets(session) -> list[MarketORM]:
    """返回所有市场记录。"""
    stmt = select(MarketORM)
    return list(session.execute(stmt).scalars().all())


def list_recent_news_items(session, hours: int = 72) -> list[NewsItemORM]:
    """
    返回最近 N 小时内的新闻。

    优先使用 created_at（系统入库时间）；
    对历史旧数据，如果 created_at 为空，则退回 published_at，避免 Week 3 后续匹配遗漏已存在新闻。
    """
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)
    stmt = select(NewsItemORM).where(
        or_(
            and_(NewsItemORM.created_at.isnot(None), NewsItemORM.created_at >= since),
            and_(NewsItemORM.created_at.is_(None), NewsItemORM.published_at.isnot(None), NewsItemORM.published_at >= since),
        )
    )
    return list(session.execute(stmt).scalars().all())


def list_news_items(session, board_id: str | None = None, limit: int | None = None) -> list[NewsItemORM]:
    """返回新闻列表，可按 board_id 过滤，可限制条数。"""
    stmt = select(NewsItemORM)
    if board_id:
        stmt = stmt.where(NewsItemORM.board_tags == board_id)
    stmt = stmt.order_by(NewsItemORM.created_at.desc(), NewsItemORM.id.desc())
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.execute(stmt).scalars().all())


def upsert_news_event(
    session,
    news_id: int,
    event_type: str,
    actors_json: str | None = None,
    certainty: str = "unknown",
    time_ref: str | None = None,
    evidence_sentence: str | None = None,
    matched_keywords_json: str | None = None,
    extraction_method: str = "rule_v1",
) -> NewsEventORM:
    """Upsert news_event（同一 news_id + event_type 幂等）。"""
    stmt = select(NewsEventORM).where(
        NewsEventORM.news_id == news_id,
        NewsEventORM.event_type == event_type,
    )
    existing = session.execute(stmt).scalar_one_or_none()
    now = _utc_now()
    if existing is not None:
        existing.actors_json = actors_json
        existing.certainty = certainty
        existing.time_ref = time_ref
        existing.evidence_sentence = evidence_sentence
        existing.matched_keywords_json = matched_keywords_json
        existing.extraction_method = extraction_method
        existing.created_at = now
        return existing

    row = NewsEventORM(
        news_id=news_id,
        event_type=event_type,
        actors_json=actors_json,
        certainty=certainty,
        time_ref=time_ref,
        evidence_sentence=evidence_sentence,
        matched_keywords_json=matched_keywords_json,
        extraction_method=extraction_method,
        created_at=now,
    )
    session.add(row)
    return row


def list_news_events(session, news_id: int | None = None) -> list[NewsEventORM]:
    """返回所有或指定 news_id 的新闻事件。"""
    stmt = select(NewsEventORM)
    if news_id is not None:
        stmt = stmt.where(NewsEventORM.news_id == news_id)
    stmt = stmt.order_by(NewsEventORM.id.asc())
    return list(session.execute(stmt).scalars().all())


def upsert_news_market_link(
    session,
    news_id: int,
    market_id: str,
    relevance: float,
    direction: int,
    strength: float,
    reasoning: str | None = None,
    layer: str = "L1_RULE",
    llm_model: str | None = None,
    event_type: str | None = None,
    evidence_type: str | None = None,
) -> NewsMarketLinkORM:
    """Upsert news-market link（幂等，UNIQUE constraint 保重）。"""
    stmt = select(NewsMarketLinkORM).where(
        NewsMarketLinkORM.news_id == news_id,
        NewsMarketLinkORM.market_id == market_id,
    )
    existing = session.execute(stmt).scalar_one_or_none()
    now = _utc_now()
    if existing is not None:
        existing.relevance = relevance
        existing.direction = direction
        existing.strength = strength
        existing.reasoning = reasoning
        existing.event_type = event_type
        existing.evidence_type = evidence_type
        existing.layer = layer
        existing.llm_model = llm_model
        return existing
    link = NewsMarketLinkORM(
        news_id=news_id,
        market_id=market_id,
        relevance=relevance,
        direction=direction,
        strength=strength,
        reasoning=reasoning,
        event_type=event_type,
        evidence_type=evidence_type,
        layer=layer,
        llm_model=llm_model,
        created_at=now,
    )
    session.add(link)
    return link



def list_market_links(
    session,
    market_id: str | None = None,
    layer: str | None = None,
) -> list[NewsMarketLinkORM]:
    """返回所有或指定市场的 news-market links，可按 layer 过滤。"""
    stmt = select(NewsMarketLinkORM)
    if market_id:
        stmt = stmt.where(NewsMarketLinkORM.market_id == market_id)
    if layer:
        stmt = stmt.where(NewsMarketLinkORM.layer == layer)
    return list(session.execute(stmt).scalars().all())



def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

