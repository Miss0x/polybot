from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
BOARD_CONFIG_DIR = CONFIG_DIR / "boards"
ENV_FILE = ROOT_DIR / ".env"


class ConfigError(Exception):
    """Raised when configuration is invalid or incomplete."""


class AppConfig(BaseModel):
    name: str
    env: str = "development"
    default_board: str
    top_n_markets: int = 10
    scan_interval_minutes: int = 60
    snapshot_interval_minutes: int = 15
    log_level: str = "INFO"


class StorageConfig(BaseModel):
    database_url: str = "sqlite:///data/polybot.db"


class PolymarketConfig(BaseModel):
    gamma_base_url: str
    clob_base_url: str


class ThresholdConfig(BaseModel):
    trigger_price_1h: float = 0.03
    trigger_price_24h: float = 0.05
    trigger_news_count: int = 2
    alert_absolute: float = 0.08
    alert_relative: float = 0.20


class LLMConfig(BaseModel):
    primary: str
    cheap_tier: str
    fallback: str


class BoardMeta(BaseModel):
    id: str
    name: str
    source_slug: str | None = None
    tag_slug: str | None = None
    keywords_market: list[str] = Field(default_factory=list)
    keywords_news: list[str] = Field(default_factory=list)



class BoardConfig(BaseModel):
    board: BoardMeta
    thresholds: ThresholdConfig
    llm: LLMConfig


class Settings(BaseModel):
    app: AppConfig
    storage: StorageConfig
    polymarket: PolymarketConfig
    board: BoardConfig
    env: dict[str, Any]


_cached_settings: Settings | None = None


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"配置文件不存在: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    if not isinstance(data, dict):
        raise ConfigError(f"配置文件格式无效: {path}")

    return data


def load_app_config() -> dict[str, Any]:
    return _read_yaml(CONFIG_DIR / "app.yaml")


def load_board_config(board_id: str) -> dict[str, Any]:
    return _read_yaml(BOARD_CONFIG_DIR / f"{board_id}.yaml")


def get_settings(force_reload: bool = False) -> Settings:
    global _cached_settings

    if _cached_settings is not None and not force_reload:
        return _cached_settings

    load_dotenv(ENV_FILE, override=False)

    app_data = load_app_config()
    app_config = AppConfig(**app_data.get("app", {}))
    storage_config = StorageConfig(**app_data.get("storage", {}))
    polymarket_config = PolymarketConfig(**app_data.get("polymarket", {}))
    board_config = BoardConfig(**load_board_config(app_config.default_board))

    env_snapshot = {
        "APP_ENV": app_config.env,
        "LOG_LEVEL": app_config.log_level,
        "DATABASE_URL": storage_config.database_url,
        "DEFAULT_BOARD": app_config.default_board,
    }

    _cached_settings = Settings(
        app=app_config,
        storage=storage_config,
        polymarket=polymarket_config,
        board=board_config,
        env=env_snapshot,
    )
    return _cached_settings
