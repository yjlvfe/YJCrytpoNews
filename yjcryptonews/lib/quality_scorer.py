"""
YJCryptoNews v3.0 - Layer 2: Quality Engine
Quality Scorer for evaluating article quality
"""
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

from yjcryptonews.models.source import Article, Source, QualityLog
from yjcryptonews import config

logger = logging.getLogger(__name__)


@dataclass
class QualityScore:
    """Quality score breakdown"""
    source_trust: float
    content_relevance: float
    readability: float
    freshness: float
    uniqueness: float
    completeness: float
    sentiment_balance: float
    total: float


class QualityScorer:
    """Scores articles based on multiple criteria"""

    def __init__(self):
        self.weights = config.quality_engine.scoring.weights
        self.thresholds = config.quality_engine.scoring.thresholds

    def score_source_trust(self, source: Source) -> float:
        """Score based on source trustworthiness (0-100)"""
        return float(source.trust_score)

    def score_content_relevance(self, article: Article, keywords: Optional[List[str]] = None) -> float:
        """Score content relevance based on crypto-related keywords (0-100)"""
        if not article.content and not article.title:
            return 0.0

        text = f"{article.title} {article.content or ''}".lower()

        # Default crypto keywords
        crypto_keywords = keywords or [
            "bitcoin", "btc", "ethereum", "eth", "crypto", "cryptocurrency",
            "blockchain", "defi", "nft", "web3", "mining", "staking",
            "wallet", "exchange", "trading", "token", "coin", "altcoin",
            "stablecoin", "dao", "smart contract", "layer 2", "scaling",
            "regulation", "sec", "etf", "institutional", "adoption",
            "hack", "exploit", "vulnerability", "security", "audit",
            "partnership", "integration", "launch", "mainnet", "testnet",
            "upgrade", "fork", "halving", "consensus", "validator",
            "liquidity", "yield", "farming", "lending", "borrowing",
            "dex", "cex", "amm", "oracle", "bridge", "cross-chain"
        ]

        matches = sum(1 for kw in crypto_keywords if kw in text)
        # Normalize: 10+ matches = 100, 5 matches = 50, etc.
        score = min(100.0, (matches / 10) * 100)
        return score

    def score_readability(self, article: Article) -> float:
        """Score readability using textstat (0-100)"""
        try:
            import textstat
            text = article.content or article.title or ""
            if not text:
                return 50.0

            # Flesch Reading Ease score (0-100, higher = easier)
            flesch = textstat.flesch_reading_ease(text)
            # Convert to 0-100 where 100 is optimal readability
            # Optimal is around 60-70 for general audience
            if flesch >= 60:
                return 100.0
            elif flesch >= 30:
                return 70.0
            elif flesch >= 0:
                return 40.0
            else:
                return 20.0
        except Exception as e:
            logger.warning(f"Readability scoring failed: {e}")
            return 50.0

    def score_freshness(self, article: Article) -> float:
        """Score based on how recent the article is (0-100)"""
        if not article.metadata.get("published_at"):
            # Use created_at as fallback
            try:
                created = datetime.fromisoformat(article.created_at.isoformat())
                age_hours = (datetime.utcnow() - created).total_seconds() / 3600
            except Exception:
                return 50.0
        else:
            try:
                published = datetime.fromisoformat(article.metadata["published_at"])
                age_hours = (datetime.utcnow() - published).total_seconds() / 3600
            except Exception:
                return 50.0

        # Score based on age: <1h = 100, <6h = 90, <24h = 70, <7d = 40, older = 20
        if age_hours <= 1:
            return 100.0
        elif age_hours <= 6:
            return 90.0
        elif age_hours <= 24:
            return 70.0
        elif age_hours <= 168:  # 7 days
            return 40.0
        else:
            return 20.0

    def score_uniqueness(self, article: Article, existing_articles: List[Article]) -> float:
        """Score uniqueness compared to existing articles (0-100)"""
        if not existing_articles:
            return 100.0

        if not article.content and not article.title:
            return 0.0

        text = f"{article.title} {article.content or ''}".lower()
        words = set(text.split())

        max_similarity = 0.0
        for existing in existing_articles:
            existing_text = f"{existing.title} {existing.content or ''}".lower()
            existing_words = set(existing_text.split())

            if not words or not existing_words:
                continue

            intersection = words & existing_words
            union = words | existing_words
            similarity = len(intersection) / len(union) if union else 0
            max_similarity = max(max_similarity, similarity)

        # Convert similarity to uniqueness (inverse)
        return max(0.0, 100.0 - (max_similarity * 100))

    def score_completeness(self, article: Article) -> float:
        """Score based on completeness of article information (0-100)"""
        score = 0.0
        checks = 0

        # Get metadata dict (handles both SQLAlchemy model and Pydantic)
        # For SQLAlchemy model, use extra_data; for Pydantic, use metadata
        metadata = {}
        if hasattr(article, 'extra_data') and article.extra_data is not None:
            metadata = article.extra_data
        elif hasattr(article, 'metadata') and hasattr(article.metadata, 'get'):
            metadata = article.metadata

        # Has title
        if article.title and len(article.title) > 10:
            score += 20
        checks += 20

        # Has content
        if article.content and len(article.content) > 100:
            score += 25
        elif article.content and len(article.content) > 50:
            score += 15
        checks += 25

        # Has source
        if article.source_id:
            score += 10
        checks += 10

        # Has published date
        if metadata.get("published_at"):
            score += 15
        checks += 15

        # Has author
        if metadata.get("author"):
            score += 10
        checks += 10

        # Has tags/categories
        if metadata.get("tags"):
            score += 10
        checks += 10

        # Has media
        if metadata.get("media"):
            score += 10
        checks += 10

        return (score / checks * 100) if checks > 0 else 0.0

    def score_sentiment_balance(self, article: Article) -> float:
        """Score sentiment balance - avoid overly promotional or FUD content (0-100)"""
        text = f"{article.title} {article.content or ''}".lower()

        # Red flags for promotional content
        promotional_patterns = [
            r"guaranteed.*profit", r"100%.*return", r"get rich",
            r"moon", r"lambo", r"to the moon", r"pump",
            r"don't miss", r"last chance", r"limited time",
            r"exclusive", r"secret", r"insider",
        ]

        # Red flags for FUD (Fear, Uncertainty, Doubt)
        fud_patterns = [
            r"crash", r"collapse", r"dead", r"scam",
            r"ponzi", r"rug pull", r"exit scam",
            r"banned", r"illegal", r"crackdown",
        ]

        promotional_count = sum(1 for p in promotional_patterns if re.search(p, text))
        fud_count = sum(1 for p in fud_patterns if re.search(p, text))

        # Penalize both extremes
        penalty = (promotional_count + fud_count) * 15
        return max(0.0, 100.0 - penalty)

    def score_article(
        self,
        article: Article,
        source: Source,
        existing_articles: Optional[List[Article]] = None
    ) -> QualityScore:
        """Score an article across all criteria"""
        scores = QualityScore(
            source_trust=self.score_source_trust(source),
            content_relevance=self.score_content_relevance(article),
            readability=self.score_readability(article),
            freshness=self.score_freshness(article),
            uniqueness=self.score_uniqueness(article, existing_articles or []),
            completeness=self.score_completeness(article),
            sentiment_balance=self.score_sentiment_balance(article),
            total=0.0,
        )

        # Calculate weighted total
        scores.total = (
            scores.source_trust * getattr(self.weights, "source_trust", 0.25) +
            scores.content_relevance * getattr(self.weights, "content_relevance", 0.20) +
            scores.readability * getattr(self.weights, "readability", 0.10) +
            scores.freshness * getattr(self.weights, "freshness", 0.10) +
            scores.uniqueness * getattr(self.weights, "uniqueness", 0.15) +
            scores.completeness * getattr(self.weights, "completeness", 0.10) +
            scores.sentiment_balance * getattr(self.weights, "sentiment_balance", 0.10)
        )

        return scores

    def should_publish(self, score: QualityScore) -> Tuple[bool, str]:
        """Determine if article should be published based on score"""
        if score.total >= getattr(self.thresholds, "high_quality_score", 80):
            return True, "high_quality"
        elif score.total >= getattr(self.thresholds, "minimum_publish_score", 60):
            return True, "standard"
        elif score.total < getattr(self.thresholds, "auto_reject_below", 40):
            return False, "auto_reject"
        else:
            return False, "below_threshold"


def create_quality_logs(article_id: int, scores: QualityScore) -> List[QualityLog]:
    """Create QualityLog entries for each criterion"""
    logs = []
    for criterion, value in [
        ("source_trust", scores.source_trust),
        ("content_relevance", scores.content_relevance),
        ("readability", scores.readability),
        ("freshness", scores.freshness),
        ("uniqueness", scores.uniqueness),
        ("completeness", scores.completeness),
        ("sentiment_balance", scores.sentiment_balance),
    ]:
        logs.append(QualityLog(
            article_id=article_id,
            criterion=criterion,
            score=str(value),
            details={"weight": config.quality_engine.scoring.weights.get(criterion, 0)}
        ))
    return logs


async def score_articles(
    articles: List[Article],
    sources: Dict[int, Source],
    existing_articles: Optional[List[Article]] = None
) -> List[Article]:
    """Score a batch of articles"""
    scorer = QualityScorer()

    for article in articles:
        source = sources.get(article.source_id)
        if not source:
            logger.warning(f"No source found for article {article.id}")
            continue

        scores = scorer.score_article(article, source, existing_articles)
        article.quality_score = str(scores.total)

        # Log individual scores
        logs = create_quality_logs(article.id, scores)
        # In a real implementation, these would be saved to the database
        article.metadata["quality_scores"] = {
            "source_trust": scores.source_trust,
            "content_relevance": scores.content_relevance,
            "readability": scores.readability,
            "freshness": scores.freshness,
            "uniqueness": scores.uniqueness,
            "completeness": scores.completeness,
            "sentiment_balance": scores.sentiment_balance,
            "total": scores.total,
        }

        should_pub, reason = scorer.should_publish(scores)
        article.metadata["publish_decision"] = {
            "should_publish": should_pub,
            "reason": reason,
        }

        logger.info(f"Article {article.id} scored: {scores.total:.2f} ({reason})")

    return articles