# YJCryptoNews - Core Package

# Legacy imports (for backward compatibility)
from yjcryptonews import database, fetcher, publisher, market, daily_queue, urgent
from yjcryptonews import translator as legacy_translator
from yjcryptonews import filter as legacy_filter
from yjcryptonews.config import _settings_instance as config  # Re-export settings as config for backward compat

# ============================================================
# NEW v3 Architecture - Layered Design
# ============================================================

# Layer 1: Data Acquisition
from yjcryptonews.lib.rss_aggregator import RSSAggregator, fetch_rss_feeds, RSSFeedItem
from yjcryptonews.lib.scraping_engine import ScrapingEngine, fetch_scraped_articles, ScrapingSelector, ScrapedArticle, create_scrapers_from_config
from yjcryptonews.lib.api_collectors import (
    BaseAPICollector, CoinGeckoCollector, CoinMarketCapCollector,
    FearGreedCollector, DefiLlamaCollector, GitHubTrendingCollector,
    APICollectorManager, fetch_api_articles, create_api_sources_from_config,
)
from yjcryptonews.lib.data_acquisition import DataAcquisitionEngine, run_acquisition_cycle

# Layer 2: Quality Engine
from yjcryptonews.lib.quality_scorer import QualityScorer, QualityScore, score_articles, create_quality_logs
from yjcryptonews.lib.fact_checker import FactChecker, ClaimExtractor, ExtractedClaim, VerificationResult, ClaimType, fact_check_articles
from yjcryptonews.lib.dedup_engine import DeduplicationEngine, DedupResult, DedupAction, DedupStage, deduplicate_articles

# Layer 3: AI Processing
from yjcryptonews.lib.ai_translator import AITranslator, TranslationResult, translate_articles
from yjcryptonews.lib.ai_summarizer import AISummarizer, SummaryResult, summarize_articles
from yjcryptonews.lib.ai_enricher import AIEnricher, EnrichmentResult, enrich_articles
from yjcryptonews.lib.ai_rewriter import AIRewriter, RewriteResult, rewrite_articles
from yjcryptonews.lib.ai_processing import AIProcessingPipeline, run_ai_pipeline

# Layer 4-5: Orchestration & Delivery
from yjcryptonews.lib.publisher import TelegramPublisher, PublishResult, UrgentQueue, StandardQueue, Publisher, run_publish_cycle, QueueType
from yjcryptonews.lib.scheduler import HourlySingleArticleScheduler, run_hourly_cycle, run_breaking_check
from yjcryptonews.lib.analytics import AnalyticsEngine, SourceMetrics, ChannelMetrics, DailyKPIs

# Models & Config
from yjcryptonews.models.source import (
    Base, Source, Article, Channel, Publish, PublishLog, QualityLog, DuplicateCheck, AnalyticsDaily,
    SourceType, SourceStatus, ArticleStatus, FactCheckStatus,
    SourceCreate, SourceUpdate, SourceResponse,
    ArticleCreate, ArticleUpdate, ArticleResponse
)
from yjcryptonews.config import get_settings, load_config
from yjcryptonews.config import _settings_instance as settings

__all__ = [
    # Legacy
    "config", "database", "fetcher", "publisher", "market", "daily_queue", "urgent",
    "legacy_translator", "legacy_filter",

    # Layer 1: Data Acquisition
    "RSSAggregator", "fetch_rss_feeds", "RSSFeedItem",
    "ScrapingEngine", "fetch_scraped_articles", "ScrapingSelector", "ScrapedArticle", "create_scrapers_from_config",
    "BaseAPICollector", "CoinGeckoCollector", "CoinMarketCapCollector", "FearGreedCollector",
    "DefiLlamaCollector", "GitHubTrendingCollector", "APICollectorManager",
    "fetch_api_articles", "create_api_sources_from_config",
    "DataAcquisitionEngine", "run_acquisition_cycle",

    # Layer 2: Quality Engine
    "QualityScorer", "QualityScore", "score_articles", "create_quality_logs",
    "FactChecker", "ClaimExtractor", "ExtractedClaim", "VerificationResult", "ClaimType", "fact_check_articles",
    "DeduplicationEngine", "DedupResult", "DedupAction", "DedupStage", "deduplicate_articles",

    # Layer 3: AI Processing
    "AITranslator", "TranslationResult", "translate_articles",
    "AISummarizer", "SummaryResult", "summarize_articles",
    "AIEnricher", "EnrichmentResult", "enrich_articles",
    "AIRewriter", "RewriteResult", "rewrite_articles",
    "AIProcessingPipeline", "run_ai_pipeline",

    # Layer 4-5: Orchestration & Delivery
    "TelegramPublisher", "PublishResult", "UrgentQueue", "StandardQueue", "Publisher", "run_publish_cycle", "QueueType",
    "Scheduler", "ScheduledTask", "TaskStatus", "create_default_scheduler", "run_scheduler",
    "AnalyticsEngine", "SourceMetrics", "ChannelMetrics", "DailyKPIs",

    # Models & Config
    "Base", "Source", "Article", "Channel", "Publish", "PublishLog", "QualityLog", "DuplicateCheck", "AnalyticsDaily",
    "SourceType", "SourceStatus", "ArticleStatus", "FactCheckStatus",
    "SourceCreate", "SourceUpdate", "SourceResponse",
    "ArticleCreate", "ArticleUpdate", "ArticleResponse",
    "settings", "get_settings", "load_config",
]