"""
Data models for YJCryptoNews v3.0 - Layer 1: Data Acquisition
"""
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, JSON, ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class SourceType(str, Enum):
    RSS = "rss"
    SCRAPING = "scraping"
    API = "api"
    MONITORING = "monitoring"


class SourceStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


class Source(Base):
    """Source model for data acquisition"""
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    url = Column(Text, nullable=False)
    type = Column(String(50), nullable=False)  # SourceType enum
    trust_score = Column(Integer, default=50)  # 0-100
    last_fetch = Column(DateTime, nullable=True)
    status = Column(String(20), default=SourceStatus.ACTIVE.value)
    config = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    articles = relationship("Article", back_populates="source")

    __table_args__ = (
        Index('idx_sources_type', 'type'),
        Index('idx_sources_status', 'status'),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "type": self.type,
            "trust_score": self.trust_score,
            "last_fetch": self.last_fetch.isoformat() if self.last_fetch else None,
            "status": self.status,
            "config": self.config,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# Pydantic models for API/validation
class SourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    url: HttpUrl
    type: SourceType
    trust_score: int = Field(default=50, ge=0, le=100)
    config: Dict[str, Any] = Field(default_factory=dict)


class SourceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    url: Optional[HttpUrl] = None
    type: Optional[SourceType] = None
    trust_score: Optional[int] = Field(None, ge=0, le=100)
    status: Optional[SourceStatus] = None
    config: Optional[Dict[str, Any]] = None


class SourceResponse(BaseModel):
    id: int
    name: str
    url: str
    type: SourceType
    trust_score: int
    last_fetch: Optional[datetime]
    status: SourceStatus
    config: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ArticleStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    PUBLISHED = "published"
    REJECTED = "rejected"
    SCHEDULED = "scheduled"


class FactCheckStatus(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"
    FLAGGED = "flagged"
    REQUIRES_REVIEW = "requires_review"


class Article(Base):
    """Article model for content pipeline"""
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(Text, nullable=False)
    content = Column(Text, nullable=True)
    url = Column(Text, nullable=False, unique=True)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)
    quality_score = Column(String(10), default="0.00")  # Decimal as string for SQLite compatibility
    fact_check_status = Column(String(20), default=FactCheckStatus.PENDING.value)
    publish_status = Column(String(20), default=ArticleStatus.PENDING.value)
    language = Column(String(10), default="en")
    original_language = Column(String(10), nullable=True)
    summary = Column(Text, nullable=True)
    translated_title = Column(Text, nullable=True)
    translated_content = Column(Text, nullable=True)
    key_points = Column(JSON, default=list)
    extra_data = Column(JSON, default=dict)
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    source = relationship("Source", back_populates="articles")
    publishes = relationship("Publish", back_populates="article")
    duplicate_checks = relationship("DuplicateCheck", back_populates="article", foreign_keys="DuplicateCheck.article_id")
    quality_logs = relationship("QualityLog", back_populates="article")

    __table_args__ = (
        Index('idx_articles_source', 'source_id'),
        Index('idx_articles_quality', 'quality_score'),
        Index('idx_articles_publish_status', 'publish_status'),
        Index('idx_articles_created', 'created_at'),
        Index('idx_articles_url', 'url'),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "url": self.url,
            "source_id": self.source_id,
            "quality_score": float(self.quality_score) if self.quality_score else 0.0,
            "fact_check_status": self.fact_check_status,
            "publish_status": self.publish_status,
            "language": self.language,
            "original_language": self.original_language,
            "summary": self.summary,
            "translated_title": self.translated_title,
            "translated_content": self.translated_content,
            "key_points": self.key_points,
            "metadata": self.extra_data,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# Pydantic models for Article
class ArticleCreate(BaseModel):
    title: str = Field(..., min_length=1)
    content: Optional[str] = None
    url: HttpUrl
    source_id: int
    language: str = "en"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ArticleUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    quality_score: Optional[float] = Field(None, ge=0, le=100)
    fact_check_status: Optional[FactCheckStatus] = None
    publish_status: Optional[ArticleStatus] = None
    summary: Optional[str] = None
    translated_title: Optional[str] = None
    translated_content: Optional[str] = None
    key_points: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class ArticleResponse(BaseModel):
    id: int
    title: str
    content: Optional[str]
    url: str
    source_id: int
    quality_score: float
    fact_check_status: FactCheckStatus
    publish_status: ArticleStatus
    language: str
    original_language: Optional[str]
    summary: Optional[str]
    translated_title: Optional[str]
    translated_content: Optional[str]
    key_points: List[str]
    metadata: Dict[str, Any]
    published_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DuplicateCheck(Base):
    """Deduplication tracking"""
    __tablename__ = "duplicate_checks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    article_id = Column(Integer, ForeignKey("articles.id"), nullable=False)
    hash = Column(String(64), nullable=False)
    embedding = Column(JSON, nullable=True)  # Store as JSON array for compatibility
    checked_against = Column(Integer, ForeignKey("articles.id"), nullable=True)
    similarity_score = Column(String(10), nullable=True)  # Decimal as string
    stage = Column(Integer, nullable=False)  # 1, 2, 3, 4
    action_taken = Column(String(20), nullable=True)  # 'reject', 'merge', 'queue_review', 'flag'
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    article = relationship("Article", back_populates="duplicate_checks", foreign_keys=[article_id])
    checked_against_article = relationship("Article", foreign_keys=[checked_against])

    __table_args__ = (
        Index('idx_duplicate_article', 'article_id'),
        Index('idx_duplicate_hash', 'hash'),
    )


class Publish(Base):
    """Publish tracking"""
    __tablename__ = "publishes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    article_id = Column(Integer, ForeignKey("articles.id"), nullable=False)
    channel_id = Column(String(100), nullable=False)
    channel_username = Column(String(255), nullable=True)
    published_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(20), default="success")
    error_log = Column(Text, nullable=True)
    message_id = Column(Integer, nullable=True)
    queue_type = Column(String(20), default="standard")
    retry_count = Column(Integer, default=0)

    # Relationships
    article = relationship("Article", back_populates="publishes")

    __table_args__ = (
        Index('idx_publishes_article', 'article_id'),
        Index('idx_publishes_channel', 'channel_id'),
        Index('idx_publishes_published', 'published_at'),
    )


class PublishLog(Base):
    """Publish log for detailed tracking"""
    __tablename__ = "publish_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cycle_id = Column(String(100), nullable=False)
    channel_id = Column(String(100), nullable=True)
    item_title = Column(Text, nullable=True)
    status = Column(String(20), nullable=True)
    error = Column(Text, nullable=True)
    event = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_publish_logs_cycle', 'cycle_id'),
        Index('idx_publish_logs_created', 'created_at'),
    )


class QualityLog(Base):
    """Quality scoring logs"""
    __tablename__ = "quality_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    article_id = Column(Integer, ForeignKey("articles.id"), nullable=False)
    criterion = Column(String(50), nullable=False)
    score = Column(String(10), nullable=False)  # Decimal as string
    details = Column(JSON, default=dict)
    checked_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    article = relationship("Article", back_populates="quality_logs")

    __table_args__ = (
        Index('idx_quality_logs_article', 'article_id'),
        Index('idx_quality_logs_criterion', 'criterion'),
    )


class Channel(Base):
    """Telegram channels"""
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(String(100), nullable=False, unique=True)
    username = Column(String(255), nullable=True)
    title = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    config = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)


class AnalyticsDaily(Base):
    """Daily analytics"""
    __tablename__ = "analytics_daily"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime, nullable=False, unique=True)  # Store as date
    total_articles = Column(Integer, default=0)
    published_articles = Column(Integer, default=0)
    rejected_articles = Column(Integer, default=0)
    avg_quality_score = Column(String(10), nullable=True)
    sources_active = Column(Integer, default=0)
    channels_active = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)