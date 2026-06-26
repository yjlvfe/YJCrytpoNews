"""
YJCryptoNews v3.0 - Layer 5: Delivery
Analytics for tracking performance and KPIs
"""
import logging
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from collections import defaultdict
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from yjcryptonews.models.source import (
    Article, Source, Publish, Channel, QualityLog, AnalyticsDaily,
    ArticleStatus, FactCheckStatus, SourceStatus
)
from yjcryptonews import config

logger = logging.getLogger(__name__)


@dataclass
class SourceMetrics:
    """Metrics for a single source"""
    source_id: int
    source_name: str
    source_type: str
    articles_fetched: int
    articles_published: int
    avg_quality_score: float
    fact_check_rate: float
    last_fetch: Optional[datetime]


@dataclass
class ChannelMetrics:
    """Metrics for a single channel"""
    channel_id: str
    channel_name: str
    posts_sent: int
    posts_failed: int
    avg_posts_per_hour: float
    last_post: Optional[datetime]


@dataclass
class DailyKPIs:
    """Daily Key Performance Indicators"""
    date: date
    total_articles: int
    articles_published: int
    articles_rejected: int
    articles_pending: int
    avg_quality_score: float
    sources_active: int
    channels_active: int
    dedup_rate: float
    fact_check_verified: int
    fact_check_failed: int
    publishing_latency_avg_minutes: float


class AnalyticsEngine:
    """Analytics engine for tracking KPIs"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_daily_kpis(self, target_date: Optional[date] = None) -> DailyKPIs:
        """Get KPIs for a specific date"""
        target_date = target_date or date.today()
        start_dt = datetime.combine(target_date, datetime.min.time())
        end_dt = start_dt + timedelta(days=1)

        # Total articles
        total_articles = await self.session.scalar(
            select(func.count(Article.id)).where(
                Article.created_at >= start_dt,
                Article.created_at < end_dt
            )
        ) or 0

        # Published articles
        published = await self.session.scalar(
            select(func.count(Publish.id)).where(
                Publish.published_at >= start_dt,
                Publish.published_at < end_dt,
                Publish.status == "success"
            )
        ) or 0

        # Rejected articles (publish failed)
        rejected = await self.session.scalar(
            select(func.count(Publish.id)).where(
                Publish.published_at >= start_dt,
                Publish.published_at < end_dt,
                Publish.status != "success"
            )
        ) or 0

        # Pending articles
        pending = await self.session.scalar(
            select(func.count(Article.id)).where(
                Article.publish_status == ArticleStatus.PENDING.value
            )
        ) or 0

        # Average quality score
        avg_quality_result = await self.session.execute(
            select(func.avg(Article.quality_score.cast(Float))).where(
                Article.created_at >= start_dt,
                Article.created_at < end_dt
            )
        )
        avg_quality = avg_quality_result.scalar() or 0.0

        # Active sources
        sources_active = await self.session.scalar(
            select(func.count(Source.id)).where(
                Source.status == SourceStatus.ACTIVE.value
            )
        ) or 0

        # Active channels
        channels_active = await self.session.scalar(
            select(func.count(Channel.id)).where(
                Channel.is_active == True
            )
        ) or 0

        # Deduplication rate
        dedup_checks = await self.session.scalar(
            select(func.count()).where(
                Article.created_at >= start_dt,
                Article.created_at < end_dt
            )
        ) or 1
        dedup_rejected = await self.session.scalar(
            select(func.count()).where(
                Article.publish_status == ArticleStatus.REJECTED.value,
                Article.created_at >= start_dt,
                Article.created_at < end_dt
            )
        ) or 0
        dedup_rate = dedup_rejected / dedup_checks if dedup_checks > 0 else 0.0

        # Fact check stats
        fact_check_verified = await self.session.scalar(
            select(func.count(Article.id)).where(
                Article.fact_check_status == FactCheckStatus.VERIFIED.value,
                Article.created_at >= start_dt,
                Article.created_at < end_dt
            )
        ) or 0

        fact_check_failed = await self.session.scalar(
            select(func.count(Article.id)).where(
                Article.fact_check_status == FactCheckStatus.FAILED.value,
                Article.created_at >= start_dt,
                Article.created_at < end_dt
            )
        ) or 0

        # Publishing latency (average time from article creation to publish)
        latency_result = await self.session.execute(
            select(
                func.avg(
                    func.extract('epoch', Publish.published_at - Article.created_at) / 60
                )
            ).join(Article, Publish.article_id == Article.id).where(
                Publish.published_at >= start_dt,
                Publish.published_at < end_dt,
                Publish.status == "success"
            )
        )
        latency_avg = latency_result.scalar() or 0.0

        return DailyKPIs(
            date=target_date,
            total_articles=total_articles,
            articles_published=published,
            articles_rejected=rejected,
            articles_pending=pending,
            avg_quality_score=float(avg_quality),
            sources_active=sources_active,
            channels_active=channels_active,
            dedup_rate=dedup_rate,
            fact_check_verified=fact_check_verified,
            fact_check_failed=fact_check_failed,
            publishing_latency_avg_minutes=float(latency_avg),
        )

    async def get_source_metrics(self, days: int = 7) -> List[SourceMetrics]:
        """Get metrics for all sources"""
        cutoff = datetime.utcnow() - timedelta(days=days)

        # Get all active sources
        sources_result = await self.session.execute(
            select(Source).where(Source.status == SourceStatus.ACTIVE.value)
        )
        sources = list(sources_result.scalars().all())

        metrics = []
        for source in sources:
            # Articles fetched
            fetched = await self.session.scalar(
                select(func.count(Article.id)).where(
                    Article.source_id == source.id,
                    Article.created_at >= cutoff
                )
            ) or 0

            # Articles published
            published = await self.session.scalar(
                select(func.count(Publish.id)).join(Article).where(
                    Article.source_id == source.id,
                    Publish.published_at >= cutoff,
                    Publish.status == "success"
                )
            ) or 0

            # Average quality score
            avg_quality_result = await self.session.execute(
                select(func.avg(Article.quality_score.cast(Float))).where(
                    Article.source_id == source.id,
                    Article.created_at >= cutoff
                )
            )
            avg_quality = avg_quality_result.scalar() or 0.0

            # Fact check rate
            total_with_fc = await self.session.scalar(
                select(func.count(Article.id)).where(
                    Article.source_id == source.id,
                    Article.created_at >= cutoff,
                    Article.fact_check_status != FactCheckStatus.PENDING.value
                )
            ) or 0
            verified = await self.session.scalar(
                select(func.count(Article.id)).where(
                    Article.source_id == source.id,
                    Article.created_at >= cutoff,
                    Article.fact_check_status == FactCheckStatus.VERIFIED.value
                )
            ) or 0
            fc_rate = verified / total_with_fc if total_with_fc > 0 else 0.0

            metrics.append(SourceMetrics(
                source_id=source.id,
                source_name=source.name,
                source_type=source.type,
                articles_fetched=fetched,
                articles_published=published,
                avg_quality_score=float(avg_quality),
                fact_check_rate=fc_rate,
                last_fetch=source.last_fetch,
            ))

        return metrics

    async def get_channel_metrics(self, days: int = 7) -> List[ChannelMetrics]:
        """Get metrics for all channels"""
        cutoff = datetime.utcnow() - timedelta(days=days)

        channels_result = await self.session.execute(
            select(Channel).where(Channel.is_active == True)
        )
        channels = list(channels_result.scalars().all())

        metrics = []
        for channel in channels:
            # Posts sent
            sent = await self.session.scalar(
                select(func.count(Publish.id)).where(
                    Publish.channel_id == channel.chat_id,
                    Publish.published_at >= cutoff,
                    Publish.status == "success"
                )
            ) or 0

            # Posts failed
            failed = await self.session.scalar(
                select(func.count(Publish.id)).where(
                    Publish.channel_id == channel.chat_id,
                    Publish.published_at >= cutoff,
                    Publish.status != "success"
                )
            ) or 0

            # Average posts per hour
            hours = days * 24
            avg_per_hour = sent / hours if hours > 0 else 0

            # Last post
            last_post_result = await self.session.execute(
                select(Publish.published_at).where(
                    Publish.channel_id == channel.chat_id,
                    Publish.status == "success"
                ).order_by(Publish.published_at.desc()).limit(1)
            )
            last_post = last_post_result.scalar()

            metrics.append(ChannelMetrics(
                channel_id=channel.chat_id,
                channel_name=channel.title or channel.username or channel.chat_id,
                posts_sent=sent,
                posts_failed=failed,
                avg_posts_per_hour=avg_per_hour,
                last_post=last_post,
            ))

        return metrics

    async def get_trending_topics(self, days: int = 7, limit: int = 10) -> List[Dict[str, Any]]:
        """Get trending topics from articles"""
        cutoff = datetime.utcnow() - timedelta(days=days)

        # Get all non-rejected articles
        articles_result = await self.session.execute(
            select(Article).where(
                Article.created_at >= cutoff,
                Article.publish_status != ArticleStatus.REJECTED.value
            )
        )
        articles = list(articles_result.scalars().all())

        # Simple keyword frequency analysis
        topic_counts = defaultdict(int)
        crypto_terms = [
            "bitcoin", "btc", "ethereum", "eth", "crypto", "blockchain",
            "defi", "nft", "web3", "etf", "sec", "regulation",
            "binance", "coinbase", "solana", "cardano", "polkadot",
            "hack", "exploit", "etf", "institutional", "adoption",
        ]

        for article in articles:
            text = f"{article.title} {article.content or ''}".lower()
            for term in crypto_terms:
                if term in text:
                    topic_counts[term] += 1

        # Sort and return top topics
        sorted_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)
        return [
            {"topic": topic, "count": count}
            for topic, count in sorted_topics[:limit]
        ]

    async def save_daily_analytics(self, kpis: DailyKPIs):
        """Save daily analytics to database"""
        analytics = AnalyticsDaily(
            date=datetime.combine(kpis.date, datetime.min.time()),
            total_articles=kpis.total_articles,
            published_articles=kpis.articles_published,
            rejected_articles=kpis.articles_rejected,
            avg_quality_score=kpis.avg_quality_score,
            sources_active=kpis.sources_active,
            channels_active=kpis.channels_active,
        )
        self.session.add(analytics)
        await self.session.commit()


# Add Float import
from sqlalchemy import Float