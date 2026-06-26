"""
YJCryptoNews v3.0 - Layer 1: Data Acquisition & Layer 2: Quality Engine & Layer 3: AI Processing & Layer 4-5: Orchestration & Delivery Package
"""
from yjcryptonews.lib.rss_aggregator import RSSAggregator, fetch_rss_feeds, RSSFeedItem
from yjcryptonews.lib.scraping_engine import ScrapingEngine, fetch_scraped_articles, ScrapingSelector, ScrapedArticle, create_scrapers_from_config
from yjcryptonews.lib.api_collectors import (
    BaseAPICollector,
    CoinGeckoCollector,
    CoinMarketCapCollector,
    FearGreedCollector,
    DefiLlamaCollector,
    GitHubTrendingCollector,
    APICollectorManager,
    fetch_api_articles,
    create_api_sources_from_config,
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
from yjcryptonews.lib.publisher import (
    TelegramPublisher,
    PublishResult,
    UrgentQueue,
    StandardQueue,
    Publisher,
    run_publish_cycle,
    QueueType,
)
from yjcryptonews.lib.scheduler import (
    HourlySingleArticleScheduler,
    run_hourly_cycle,
    run_breaking_check,
)
from yjcryptonews.lib.analytics import (
    AnalyticsEngine,
    SourceMetrics,
    ChannelMetrics,
    DailyKPIs,
)

__all__ = [
    # Layer 1: Data Acquisition
    # RSS
    "RSSAggregator",
    "fetch_rss_feeds",
    "RSSFeedItem",
    # Scraping
    "ScrapingEngine",
    "fetch_scraped_articles",
    "ScrapingSelector",
    "ScrapedArticle",
    "create_scrapers_from_config",
    # API
    "BaseAPICollector",
    "CoinGeckoCollector",
    "CoinMarketCapCollector",
    "FearGreedCollector",
    "DefiLlamaCollector",
    "GitHubTrendingCollector",
    "APICollectorManager",
    "fetch_api_articles",
    "create_api_sources_from_config",
    # Main
    "DataAcquisitionEngine",
    "run_acquisition_cycle",
    # Layer 2: Quality Engine
    # Quality Scorer
    "QualityScorer",
    "QualityScore",
    "score_articles",
    "create_quality_logs",
    # Fact Checker
    "FactChecker",
    "ClaimExtractor",
    "ExtractedClaim",
    "VerificationResult",
    "ClaimType",
    "fact_check_articles",
    # Deduplication
    "DeduplicationEngine",
    "DedupResult",
    "DedupAction",
    "DedupStage",
    "deduplicate_articles",
    # Layer 3: AI Processing
    # Translation
    "AITranslator",
    "TranslationResult",
    "translate_articles",
    # Summarization
    "AISummarizer",
    "SummaryResult",
    "summarize_articles",
    # Enrichment
    "AIEnricher",
    "EnrichmentResult",
    "enrich_articles",
    # Rewrite
    "AIRewriter",
    "RewriteResult",
    "rewrite_articles",
    # Pipeline
    "AIProcessingPipeline",
    "run_ai_pipeline",
    # Layer 4-5: Orchestration & Delivery
    # Publisher
    "TelegramPublisher",
    "PublishResult",
    "UrgentQueue",
    "StandardQueue",
    "Publisher",
    "run_publish_cycle",
    "QueueType",
    # Scheduler (New - Hourly Single Article)
    "HourlySingleArticleScheduler",
    "run_hourly_cycle",
    "run_breaking_check",
    # Analytics
    "AnalyticsEngine",
    "SourceMetrics",
    "ChannelMetrics",
    "DailyKPIs",
]