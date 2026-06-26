"""
YJCryptoNews v3.0 - Layer 3: AI Processing
Main orchestrator for all AI processing steps
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional

from yjcryptonews.models.source import Article
from yjcryptonews.lib.ai_translator import translate_articles
from yjcryptonews.lib.ai_summarizer import summarize_articles
from yjcryptonews.lib.ai_enricher import enrich_articles
from yjcryptonews.lib.ai_rewriter import rewrite_articles
from yjcryptonews import config

logger = logging.getLogger(__name__)


class AIProcessingPipeline:
    """Orchestrates all AI processing steps"""

    def __init__(self):
        self.enable_translation = True
        self.enable_summarization = True
        self.enable_enrichment = config.enrichment.add_market_context or config.enrichment.add_historical_comparison or config.enrichment.add_related_coins
        self.enable_rewrite = False  # Optional, can be enabled for A/B testing

    async def process_articles(self, articles: List[Article]) -> List[Article]:
        """Run all AI processing steps in sequence"""
        logger.info(f"Starting AI processing for {len(articles)} articles")

        processed = articles

        # Step 1: Translation (to Arabic)
        if self.enable_translation:
            logger.info("Running translation...")
            processed = await translate_articles(processed)
            logger.info("Translation complete")

        # Step 2: Summarization
        if self.enable_summarization:
            logger.info("Running summarization...")
            processed = await summarize_articles(processed)
            logger.info("Summarization complete")

        # Step 3: Enrichment (market context, historical, related coins)
        if self.enable_enrichment:
            logger.info("Running enrichment...")
            processed = await enrich_articles(processed)
            logger.info("Enrichment complete")

        # Step 4: Smart Rewrite (optional, for A/B testing)
        if self.enable_rewrite:
            logger.info("Running smart rewrite...")
            processed = await rewrite_articles(processed)
            logger.info("Smart rewrite complete")

        logger.info("AI processing pipeline complete")
        return processed

    async def process_single(self, article: Article) -> Article:
        """Process a single article through the pipeline"""
        results = await self.process_articles([article])
        return results[0] if results else article


async def run_ai_pipeline(articles: List[Article]) -> List[Article]:
    """Main entry point for AI processing pipeline"""
    pipeline = AIProcessingPipeline()
    return await pipeline.process_articles(articles)