"""
Configuration management for YJCryptoNews v3.0
"""
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from functools import lru_cache

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RSSSettings(BaseModel):
    timeout: int = 30
    max_concurrent: int = 20
    user_agent: str = "YJCryptoNews/3.0 (+https://yjcryptonews.example.com)"


class ScrapingSettings(BaseModel):
    timeout: int = 60
    max_concurrent: int = 10
    use_playwright: bool = True
    rate_limit: int = 2


class MonitoringSettings(BaseModel):
    google_alerts_enabled: bool = True
    check_interval_minutes: int = 15


class DataAcquisitionSettings(BaseModel):
    rss: RSSSettings = Field(default_factory=RSSSettings)
    scraping: ScrapingSettings = Field(default_factory=ScrapingSettings)
    monitoring: MonitoringSettings = Field(default_factory=MonitoringSettings)


class ScoringWeights(BaseModel):
    source_trust: float = 0.25
    content_relevance: float = 0.20
    readability: float = 0.10
    freshness: float = 0.10
    uniqueness: float = 0.15
    completeness: float = 0.10
    sentiment_balance: float = 0.10


class ScoringThresholds(BaseModel):
    minimum_publish_score: int = 60
    high_quality_score: int = 80
    auto_reject_below: int = 40


class ScoringSettings(BaseModel):
    weights: ScoringWeights = Field(default_factory=ScoringWeights)
    thresholds: ScoringThresholds = Field(default_factory=ScoringThresholds)


class FactCheckSettings(BaseModel):
    min_sources_required: int = 2
    min_source_trust: int = 70
    cross_reference_enabled: bool = True
    blockchain_verification_enabled: bool = False


class DeduplicationSettings(BaseModel):
    stage1_exact_match: bool = True
    stage2_fuzzy_threshold: float = 0.85
    stage3_semantic_threshold: float = 0.82
    stage4_key_facts_threshold: float = 0.70
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"


class QualityEngineSettings(BaseModel):
    scoring: ScoringSettings = Field(default_factory=ScoringSettings)
    fact_check: FactCheckSettings = Field(default_factory=FactCheckSettings)
    deduplication: DeduplicationSettings = Field(default_factory=DeduplicationSettings)


class TelegramSettings(BaseModel):
    bot_token: str = ""
    max_posts_per_hour: int = 8
    min_interval_minutes: int = 15
    burst_limit: int = 3
    global_max_per_hour: int = 30
    prioritize_urgent: bool = True


class UrgentQueueSettings(BaseModel):
    max_age_minutes: int = 5
    publish_immediately: bool = True
    retry_strategy: str = "exponential_backoff"
    max_retries: int = 3


class StandardQueueSettings(BaseModel):
    max_age_minutes: int = 30
    publish_schedule: str = "optimal_timeslot"
    bundle_similar: bool = True
    max_retries: int = 5


class QueueSettings(BaseModel):
    urgent: UrgentQueueSettings = Field(default_factory=UrgentQueueSettings)
    standard: StandardQueueSettings = Field(default_factory=StandardQueueSettings)


class ScheduleSettings(BaseModel):
    optimal_hours: List[int] = Field(default_factory=lambda: [9, 13, 17, 21])
    timezone: str = "UTC"


class PublishingSettings(BaseModel):
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    queues: QueueSettings = Field(default_factory=QueueSettings)
    schedule: ScheduleSettings = Field(default_factory=ScheduleSettings)


class AIModels(BaseModel):
    primary: str = "deepseek-v4-pro"
    fallback: str = "deepseek-v4-flash"
    translation: str = "deepseek-v4-pro"
    summarization: str = "deepseek-v4-flash"
    enrichment: str = "deepseek-v4-pro"


class AIMaxTokens(BaseModel):
    translation: int = 4096
    summarization: int = 1024
    enrichment: int = 8192


class AITemperature(BaseModel):
    translation: float = 0.2
    summarization: float = 0.1
    enrichment: float = 0.3


class AISettings(BaseModel):
    provider: str = "opencode-go"
    base_url: str = "https://opencode.ai/zen/v1/chat/completions"
    models: AIModels = Field(default_factory=AIModels)
    max_tokens: AIMaxTokens = Field(default_factory=AIMaxTokens)
    temperature: AITemperature = Field(default_factory=AITemperature)


class DatabaseSettings(BaseModel):
    host: str = "localhost"
    port: int = 5432
    username: str = "yjcryptonews"
    password: str = "yjcryptonews_dev"
    name: str = "yjcryptonews"
    pool_size: int = 10
    max_overflow: int = 20

    @property
    def url(self) -> str:
        return f"postgresql://{self.username}:***@{self.host}:{self.port}/{self.name}"

    @property
    def async_url(self) -> str:
        return f"postgresql+asyncpg://{self.username}:{self.password}@{self.host}:{self.port}/{self.name}"


class RedisSettings(BaseModel):
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    max_connections: int = 50

    @property
    def url(self) -> str:
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )

    app_name: str = "YJCryptoNews v3.0"
    environment: str = "development"
    debug: bool = True
    timezone: str = "UTC"

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    ai: AISettings = Field(default_factory=AISettings)
    data_acquisition: DataAcquisitionSettings = Field(default_factory=DataAcquisitionSettings)
    quality_engine: QualityEngineSettings = Field(default_factory=QualityEngineSettings)
    publishing: PublishingSettings = Field(default_factory=PublishingSettings)


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two dictionaries"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def get_settings() -> Settings:
    """Get cached settings instance"""
    # Create settings with defaults
    settings = Settings()

    # Load from config.yaml if exists
    config_path = Path(__file__).parent.parent / "config" / "config.yaml"
    if config_path.exists():
        with open(config_path, 'r') as f:
            yaml_config = yaml.safe_load(f) or {}

        # Deep merge YAML config into settings
        settings_dict = settings.model_dump()
        merged = _deep_merge(settings_dict, yaml_config)
        settings = Settings(**merged)

    return settings


settings = get_settings()