"""
YJCryptoNews v3.0 - Layer 1: Data Acquisition
Main orchestrator for all data acquisition methods
"""
import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

import httpx

from yjcryptonews.models.source import Source, Article, SourceType, SourceStatus
from yjcryptonews.lib.rss_aggregator import fetch_rss_feeds
from yjcryptonews.lib.scraping_engine import fetch_scraped_articles, create_scrapers_from_config
from yjcryptonews.lib.api_collectors import fetch_api_articles, create_api_sources_from_config
from yjcryptonews import config

logger = logging.getLogger(__name__)


class DataAcquisitionEngine:
    """Main orchestrator for all data acquisition"""

    def __init__(self):
        self.session: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        cfg = config if isinstance(config, dict) else config.dict()
        ua = cfg.get("data_acquisition", {}).get("rss", {}).get("user_agent", "YJCryptoNews/3.0")
        self.session = httpx.AsyncClient(
            timeout=httpx.Timeout(60),
            headers={"User-Agent": ua},
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.aclose()

    async def acquire_all(self, db_sources: List[Source]) -> List[Article]:
        """Run all acquisition methods and combine results"""
        logger.info("Starting data acquisition from all sources")

        # Combine database sources with config-based sources
        all_sources = list(db_sources)
        all_sources.extend(create_scrapers_from_config())
        all_sources.extend(create_api_sources_from_config())

        # Run all acquisition methods concurrently
        rss_task = fetch_rss_feeds(all_sources)
        scraping_task = fetch_scraped_articles(all_sources)
        api_task = fetch_api_articles(all_sources)

        rss_articles, scraped_articles, api_articles = await asyncio.gather(
            rss_task, scraping_task, api_task, return_exceptions=True
        )

        # Handle exceptions
        all_articles = []
        for name, articles in [
            ("RSS", rss_articles),
            ("Scraping", scraped_articles),
            ("API", api_articles),
        ]:
            if isinstance(articles, Exception):
                logger.error(f"{name} acquisition failed: {articles}")
            else:
                all_articles.extend(articles)
                logger.info(f"{name} acquired {len(articles)} articles")

        logger.info(f"Total articles acquired: {len(all_articles)}")
        return all_articles

    async def acquire_by_type(
        self,
        db_sources: List[Source],
        source_type: SourceType
    ) -> List[Article]:
        """Acquire from specific source type"""
        all_sources = list(db_sources)
        all_sources.extend(create_scrapers_from_config())
        all_sources.extend(create_api_sources_from_config())

        if source_type == SourceType.RSS:
            return await fetch_rss_feeds(all_sources)
        elif source_type == SourceType.SCRAPING:
            return await fetch_scraped_articles(all_sources)
        elif source_type == SourceType.API:
            return await fetch_api_articles(all_sources)
        else:
            logger.warning(f"Unknown source type: {source_type}")
            return []


async def run_acquisition_cycle(db_sources: List[Source]) -> List[Article]:
    """Run a complete data acquisition cycle"""
    async with DataAcquisitionEngine() as engine:
        return await engine.acquire_all(db_sources)


# For backwards compatibility and easy imports
__all__ = [
    "DataAcquisitionEngine",
    "run_acquisition_cycle",
    "fetch_rss_feeds",
    "fetch_scraped_articles",
    "fetch_api_articles",
]