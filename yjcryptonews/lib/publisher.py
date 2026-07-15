"""
YJCryptoNews v3.0 - Layer 4: Orchestration
Publisher for Telegram channel delivery
"""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

import httpx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from yjcryptonews.models.source import Article, Publish, Channel, PublishLog, ArticleStatus
from yjcryptonews import config

logger = logging.getLogger(__name__)


class QueueType(str, Enum):
    URGENT = "urgent"
    STANDARD = "standard"


@dataclass
class PublishResult:
    """Result of a publish attempt"""
    success: bool
    message_id: Optional[int] = None
    error: Optional[str] = None
    queue_type: QueueType = QueueType.STANDARD


class TelegramPublisher:
    """Handles publishing to Telegram channels"""

    def __init__(self, bot_token: Optional[str] = None):
        self.bot_token = bot_token or config.publishing.telegram.bot_token
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.session: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self.session = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.aclose()

    def _format_message(self, article: Article) -> str:
        """Format article for Telegram"""
        title = article.translated_title or article.title
        summary = article.summary or ""
        url = article.url

        # Build message
        parts = [f"📰 <b>{title}</b>\n"]

        if summary:
            parts.append(f"{summary}\n")

        # Add key points if available
        if article.key_points:
            points = "\n".join([f"• {kp}" for kp in article.key_points if kp])
            if points:
                parts.append(f"\n🎯 <b>Key Points:</b>\n{points}\n")

        # Add source - REMOVED per user request
        # if article.metadata.get("source_name"):
        #     parts.append(f"\n📌 Source: {article.metadata['source_name']}")

        parts.append(f"\n🔗 <a href='{url}'>Read Full Article</a>")

        # Add hashtags for crypto topics - REMOVED per user request
        # tags = article.metadata.get("tags", [])
        # if tags:
        #     hashtags = " ".join([f"#{tag.replace(' ', '_')}" for tag in tags[:5]])
        #     parts.append(f"\n{hashtags}")

        return "".join(parts)

    async def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: str = "HTML",
        disable_web_page_preview: bool = False
    ) -> Tuple[bool, Optional[int], Optional[str]]:
        """Send a message to Telegram channel"""
        if not self.session:
            raise RuntimeError("Publisher not initialized. Use async context manager.")

        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_web_page_preview,
        }

        try:
            response = await self.session.post(f"{self.api_url}/sendMessage", json=payload)
            response.raise_for_status()
            result = response.json()

            if result.get("ok"):
                message_id = result["result"]["message_id"]
                return True, message_id, None
            else:
                error = result.get("description", "Unknown error")
                return False, None, error

        except httpx.HTTPStatusError as e:
            return False, None, f"HTTP {e.response.status_code}: {e.response.text}"
        except Exception as e:
            return False, None, str(e)

    async def publish_article(
        self,
        article: Article,
        channel: Channel
    ) -> PublishResult:
        """Publish a single article to a channel"""
        if not self.bot_token:
            return PublishResult(success=False, error="Bot token not configured")

        message_text = self._format_message(article)

        success, message_id, error = await self.send_message(
            chat_id=channel.chat_id,
            text=message_text,
        )

        return PublishResult(
            success=success,
            message_id=message_id,
            error=error,
            queue_type=article.metadata.get("queue_type", QueueType.STANDARD),
        )


class UrgentQueue:
    """Priority queue for breaking news"""

    def __init__(self, session: AsyncSession, publisher: TelegramPublisher):
        self.session = session
        self.publisher = publisher
        self.max_age_minutes = config.publishing.queues.urgent.max_age_minutes
        self.max_retries = config.publishing.queues.urgent.max_retries

    def _is_urgent(self, article: Article) -> bool:
        """Determine if article should go to urgent queue"""
        # Check for urgent keywords in title/content
        urgent_keywords = [
            "breaking", "urgent", "alert", "crash", "hack", "exploit",
            "etf approval", "sec decision", "regulation", "ban",
            "halving", "fork", "upgrade", "mainnet launch",
        ]

        text = f"{article.title} {article.content or ''}".lower()
        for kw in urgent_keywords:
            if kw in text:
                return True

        # Check if quality score is very high
        try:
            if float(article.quality_score) >= 90:
                return True
        except (ValueError, TypeError):
            pass

        return False

    async def get_pending_articles(self) -> List[Article]:
        """Get articles ready for urgent publishing"""
        from sqlalchemy import select

        query = select(Article).where(
            Article.publish_status == ArticleStatus.PENDING.value,
            Article.quality_score >= "60",  # Minimum quality
        ).order_by(Article.created_at.desc()).limit(50)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def process(self) -> Dict[str, int]:
        """Process urgent queue"""
        logger.info("Processing urgent queue...")
        articles = await self.get_pending_articles()
        urgent_articles = [a for a in articles if self._is_urgent(a)]

        stats = {"processed": 0, "published": 0, "failed": 0}

        for article in urgent_articles:
            article.metadata["queue_type"] = QueueType.URGENT.value
            article.publish_status = ArticleStatus.PROCESSING.value

            # Get active channels
            channels_query = select(Channel).where(Channel.is_active == True)
            channels_result = await self.session.execute(channels_query)
            channels = list(channels_result.scalars().all())

            for channel in channels:
                result = await self.publisher.publish_article(article, channel)
                stats["processed"] += 1

                if result.success:
                    stats["published"] += 1
                    # Record publish
                    publish = Publish(
                        article_id=article.id,
                        channel_id=channel.chat_id,
                        channel_username=channel.username,
                        status="success",
                        message_id=result.message_id,
                        queue_type=QueueType.URGENT.value,
                    )
                    self.session.add(publish)
                else:
                    stats["failed"] += 1
                    article.retry_count += 1
                    if article.retry_count >= self.max_retries:
                        article.publish_status = ArticleStatus.REJECTED.value

            article.publish_status = ArticleStatus.PUBLISHED.value if stats["published"] > 0 else ArticleStatus.PENDING.value

        await self.session.commit()
        logger.info(f"Urgent queue processed: {stats}")
        return stats


class StandardQueue:
    """Standard priority queue for regular news"""

    def __init__(self, session: AsyncSession, publisher: TelegramPublisher):
        self.session = session
        self.publisher = publisher
        self.max_age_minutes = config.publishing.queues.standard.max_age_minutes
        self.bundle_similar = config.publishing.queues.standard.bundle_similar
        self.max_retries = config.publishing.queues.standard.max_retries

    async def get_pending_articles(self) -> List[Article]:
        """Get articles ready for standard publishing"""
        from sqlalchemy import select

        query = select(Article).where(
            Article.publish_status == ArticleStatus.PENDING.value,
            Article.quality_score >= "60",
        ).order_by(Article.quality_score.desc()).limit(20)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def process(self) -> Dict[str, int]:
        """Process standard queue with anti-flood protection"""
        logger.info("Processing standard queue...")
        articles = await self.get_pending_articles()

        stats = {"processed": 0, "published": 0, "failed": 0, "skipped": 0}

        # Check rate limits per channel
        for article in articles:
            article.metadata["queue_type"] = QueueType.STANDARD.value

            # Get active channels
            channels_query = select(Channel).where(Channel.is_active == True)
            channels_result = await self.session.execute(channels_query)
            channels = list(channels_result.scalars().all())

            for channel in channels:
                # Check rate limits (simplified - in production use Redis)
                can_publish = await self._check_rate_limit(channel.chat_id)
                if not can_publish:
                    stats["skipped"] += 1
                    continue

                result = await self.publisher.publish_article(article, channel)
                stats["processed"] += 1

                if result.success:
                    stats["published"] += 1
                    publish = Publish(
                        article_id=article.id,
                        channel_id=channel.chat_id,
                        channel_username=channel.username,
                        status="success",
                        message_id=result.message_id,
                        queue_type=QueueType.STANDARD.value,
                    )
                    self.session.add(publish)
                else:
                    stats["failed"] += 1
                    article.retry_count += 1

            article.publish_status = ArticleStatus.PUBLISHED.value if stats["published"] > 0 else ArticleStatus.PENDING.value

        await self.session.commit()
        logger.info(f"Standard queue processed: {stats}")
        return stats

    async def _check_rate_limit(self, chat_id: str) -> bool:
        """Check if channel can accept more posts (simplified)"""
        # In production, use Redis for accurate rate limiting
        return True


class Publisher:
    """Main publisher orchestrator"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.telegram_publisher = TelegramPublisher()
        self.urgent_queue = UrgentQueue(session, self.telegram_publisher)
        self.standard_queue = StandardQueue(session, self.telegram_publisher)

    async def __aenter__(self):
        await self.telegram_publisher.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.telegram_publisher.__aexit__(exc_type, exc_val, exc_tb)

    async def publish_cycle(self) -> Dict[str, Any]:
        """Run a complete publishing cycle"""
        cycle_start = datetime.utcnow()
        cycle_id = f"cycle_{cycle_start.strftime('%Y%m%d_%H%M%S')}"

        # Process urgent queue first
        urgent_stats = await self.urgent_queue.process()

        # Then process standard queue
        standard_stats = await self.standard_queue.process()

        total_stats = {
            "cycle_id": cycle_id,
            "started_at": cycle_start.isoformat(),
            "urgent": urgent_stats,
            "standard": standard_stats,
            "total_published": urgent_stats.get("published", 0) + standard_stats.get("published", 0),
        }

        logger.info(f"Publish cycle {cycle_id} complete: {total_stats}")
        return total_stats


async def run_publish_cycle(session: AsyncSession) -> Dict[str, Any]:
    """Main entry point for publishing"""
    async with Publisher(session) as publisher:
        return await publisher.publish_cycle()