from contextlib import contextmanager
from typing import Generator

from loguru import logger
from sqlalchemy import create_engine, Engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from polybot.settings import ROOT_DIR, get_settings


class Base(DeclarativeBase):
    pass


def get_database_url() -> str:
    settings = get_settings()
    raw_url = settings.storage.database_url
    if raw_url.startswith("sqlite:///") and not raw_url.startswith("sqlite:////"):
        relative_path = raw_url.replace("sqlite:///", "", 1)
        absolute_path = (ROOT_DIR / relative_path).resolve()
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{absolute_path.as_posix()}"
    return raw_url


def _make_engine() -> Engine:
    return create_engine(get_database_url(), future=True)


# 懒加载：首次调用 get_session() 时才初始化 engine
_engine = None
_SessionLocal = None


def _get_session_factory():
    global _engine, _SessionLocal
    if _SessionLocal is None:
        _engine = _make_engine()
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    return _SessionLocal


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """提供一个带自动 rollback/close 的 Session 上下文管理器。"""
    factory = _get_session_factory()
    session: Session = factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_engine() -> Engine:
    """返回（懒加载的）全局 Engine 实例。"""
    _get_session_factory()  # 确保 _engine 已初始化
    return _engine


def init_db() -> None:
    from polybot.storage.models import Base as ModelBase

    ModelBase.metadata.create_all(bind=get_engine())
    _migrate_schema()


def _migrate_schema() -> None:
    """为已有数据库补充新列（ALTER TABLE），避免丢失历史数据。"""
    engine = get_engine()
    inspector = inspect(engine)

    # markets 表新增列
    _migrate_table(
        engine, inspector,
        "markets",
        [
            ("subcategory", "VARCHAR(64)"),
            ("condition_id", "VARCHAR(128)"),
            ("description", "TEXT"),
            ("resolution_source", "TEXT"),
            ("outcomes_json", "TEXT"),
            ("clob_token_ids_json", "TEXT"),
            ("raw_event_json", "TEXT"),
            ("raw_market_json", "TEXT"),
            ("updated_at", "TIMESTAMP"),
        ],
    )

    # news_items 表新增列（SQLite 不允许 ALTER TABLE ADD NOT NULL 列无默认值，迁完再改 ORM）
    _migrate_table(
        engine, inspector,
        "news_items",
        [("created_at", "TIMESTAMP")],
    )

    # news_events 表由 metadata.create_all 创建；如未来增列，在这里补 ALTER TABLE

    # news_market_links 表新增 ontology 匹配字段
    _migrate_table(
        engine, inspector,
        "news_market_links",
        [
            ("event_type", "VARCHAR(64)"),
            ("evidence_type", "VARCHAR(32)"),
        ],
    )

    # news_items 表新增 Serbia election pipeline 扩展列
    _migrate_table(
        engine, inspector,
        "news_items",
        [
            ("feed_id", "VARCHAR(64)"),
            ("source_class", "VARCHAR(32)"),
            ("tier", "VARCHAR(8)"),
            ("lang", "VARCHAR(8)"),
            ("title_en", "TEXT"),
            ("title_zh", "TEXT"),
            ("triage_relevant", "INTEGER"),
            ("variable_ids_json", "TEXT"),
            ("novelty", "INTEGER"),
            ("is_new_fact", "INTEGER"),
            ("triage_method", "VARCHAR(32)"),
            ("triaged_at", "TIMESTAMP"),
        ],
    )


def _migrate_table(engine, inspector, table: str, columns: list[tuple[str, str]]) -> None:

    """如果列不存在则 ALTER TABLE ADD COLUMN，并记录日志便于排查。"""
    existing = {c["name"] for c in inspector.get_columns(table)}
    with engine.connect() as conn:
        for col_name, col_def in columns:
            if col_name in existing:
                continue
            try:
                logger.info("数据库迁移：为表 {} 添加列 {} {}", table, col_name, col_def)
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"))
                conn.commit()
            except Exception as exc:
                # 这里不要静默吞异常，否则会出现“代码以为迁移好了，数据库其实没变”的隐性问题。
                logger.warning("数据库迁移失败：表 {} 添加列 {} 时出错: {}", table, col_name, exc)

