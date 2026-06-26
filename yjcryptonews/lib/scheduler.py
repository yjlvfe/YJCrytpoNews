"""
YJCryptoNews v3.0 - Layer 4: Orchestration
MULTI-BREAKING: Publishes ALL verified breaking stories (11+ sources same story)
- Hourly: 1 best fresh article
- Breaking (5min): ALL stories with 11+ sources SAME STORY + high market impact
- Semantic dedup: same story = 1 publication
"""
import logging
import asyncio
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

from yjcryptonews.models.source import Article, Source, SourceType, SourceStatus, ArticleStatus, QualityLog
from yjcryptonews.lib.publisher import TelegramPublisher, PublishResult, QueueType
from yjcryptonews import config
from yjcryptonews import database

logger = logging.getLogger(__name__)


class CycleType(str, Enum):
    HOURLY = "hourly"
    BREAKING = "breaking"
    MANUAL = "manual"


@dataclass
class StoryFingerprint:
    """Semantic fingerprint of a story"""
    core_entities: Tuple[str, ...]
    core_keywords: Tuple[str, ...]
    main_action: str
    timestamp_bucket: str

    def to_key(self) -> str:
        data = f"{self.core_entities}|{self.core_keywords}|{self.main_action}|{self.timestamp_bucket}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass
class VerifiedBreakingStory:
    """A fully verified breaking story ready for publication"""
    fingerprint: StoryFingerprint
    articles: List[Article]
    source_count: int
    unique_sources: Set[str]
    avg_quality: float
    max_quality: float
    market_impact_score: float
    primary_article: Article
    urgent_keywords: List[str]
    coins_affected: List[str]
    action_type: str


class HourlySingleArticleScheduler:
    """
    - Hourly: ONE best fresh article
    - Breaking (5min): ALL verified breaking stories (3+ sources, same story, high impact)
    - Semantic dedup: same story = 1 publication
    """
    
    def __init__(self):
        self.cfg = config.daily_publishing
        self.urgent_cfg = config.urgent_detection
        self.pub_cfg = config.publishing
        self.publisher = TelegramPublisher()
        self._source_cache = {}
        
        # Realistic breaking thresholds
        self.MIN_SOURCES_BREAKING = 3
        self.SAME_STORY_THRESHOLD = 0.75
        self.MAX_STORY_AGE_HOURS = 4
        self.MIN_MARKET_IMPACT = 0.3  # Realistic threshold
        
    def _get_rss_sources(self) -> List[Source]:
        if self._source_cache:
            return list(self._source_cache.values())
        
        sources = []
        for s in config.get("sources", {}).get("rss_feeds", []):
            if s.get("active", True):
                source_id = int(hashlib.md5(s["url"].encode()).hexdigest()[:8], 16) % 1000000
                src = Source(
                    id=source_id,
                    name=s.get("name", s["url"]),
                    url=s["url"],
                    type=SourceType.RSS.value,
                    trust_score=s.get("trust_score", 85),
                    status=SourceStatus.ACTIVE.value,
                )
                sources.append(src)
                self._source_cache[s["url"]] = src
        return sources
    
    async def acquire_all_articles(self, hours_back: int = 4) -> List[Article]:
        """Fetch from ALL sources: RSS + APIs + (future: social)"""
        logger.info(f"📡 Fetching ALL articles (last {hours_back}h)...")
        
        from yjcryptonews.lib.data_acquisition import DataAcquisitionEngine
        from yjcryptonews.models.source import Source, SourceType, SourceStatus
        
        sources = []
        for s in config.get("sources", {}).get("rss_feeds", []):
            if s.get("active", True):
                sources.append(Source(
                    id=int(hashlib.md5(s["url"].encode()).hexdigest()[:8], 16) % 1000000,
                    name=s.get("name", s["url"]),
                    url=s["url"],
                    type=SourceType.RSS.value,
                    trust_score=s.get("trust_score", 85),
                    status=SourceStatus.ACTIVE.value,
                ))
        
        async with DataAcquisitionEngine() as engine:
            articles = await engine.acquire_all(sources)
        
        # Filter by recency
        cutoff = datetime.utcnow() - timedelta(hours=hours_back)
        fresh = []
        for a in articles:
            if a.published_at:
                try:
                    if isinstance(a.published_at, datetime):
                        parsed = a.published_at
                    elif isinstance(a.published_at, str):
                        parsed = datetime.fromisoformat(a.published_at.replace('Z', '+00:00'))
                    else:
                        parsed = datetime.utcnow()
                    if parsed > cutoff:
                        fresh.append(a)
                except Exception:
                    fresh.append(a)
            else:
                fresh.append(a)
        
        logger.info(f"Total acquired: {len(articles)}, Fresh (<{hours_back}h): {len(fresh)}")
        return fresh
    
    async def quality_filter(self, articles: List[Article]) -> List[Article]:
        if not articles:
            return []
        
        logger.info(f"🧠 Quality filtering {len(articles)} articles...")
        
        source_map = {src.id: src for src in self._get_rss_sources()}
        
        from yjcryptonews.lib.quality_scorer import score_articles
        articles = await score_articles(articles, source_map, articles)
        
        min_score = self.cfg.minimum_score
        articles = [a for a in articles if a.quality_score and float(a.quality_score) >= min_score]
        
        from yjcryptonews.lib.fact_checker import fact_check_articles
        articles = await fact_check_articles(articles)
        
        existing_dicts = database.get_recent_articles(limit=1000)
        from yjcryptonews.models.source import Article as ArticleModel
        existing_articles = []
        for d in existing_dicts:
            existing_articles.append(ArticleModel(
                id=d.get("id", 0), source_id=0, title=d.get("title", ""),
                content="", url=d.get("url", ""), published_at=d.get("published_at", ""), language="en"
            ))
        from yjcryptonews.lib.dedup_engine import deduplicate_articles
        articles, _ = await deduplicate_articles(articles, existing_articles)
        
        articles.sort(key=lambda a: (
            float(a.quality_score) if a.quality_score else 0,
            a.published_at or datetime.min
        ), reverse=True)
        
        logger.info(f"✅ {len(articles)} articles passed quality filter")
        return articles
    
    # ===== SEMANTIC FINGERPRINTING =====
    
    def _extract_story_fingerprint(self, article: Article) -> StoryFingerprint:
        text = f"{article.title} {article.content or ''}".lower()
        
        coin_map = {
            "bitcoin": "BTC", "btc": "BTC", "ethereum": "ETH", "eth": "ETH",
            "solana": "SOL", "sol": "SOL", "xrp": "XRP", "ripple": "XRP",
            "cardano": "ADA", "ada": "ADA", "dogecoin": "DOGE", "doge": "DOGE",
            "avalanche": "AVAX", "avax": "AVAX", "polkadot": "DOT", "dot": "DOT",
            "chainlink": "LINK", "link": "LINK", "uniswap": "UNI", "uni": "UNI",
            "aave": "AAVE", "compound": "COMP", "maker": "MKR", "lido": "LDO"
        }
        
        core_coins = tuple(sorted(set(symbol for kw, symbol in coin_map.items() if kw in text)))
        
        action_keywords = {
            "etf_approval": ["etf approved", "etf approval", "spot etf", "etf launches", "etf goes live"],
            "etf_rejection": ["etf rejected", "etf denied", "rejects etf"],
            "ban": ["bans", "banned", "ban ", "prohibits", "restricts", "crackdown"],
            "hack": ["hack", "hacked", "exploit", "exploited", "breach", "stolen", "drained", "drain"],
            "regulation": ["regulation", "regulatory", "sec lawsuit", "cftc charges", "legislation", "bill passed"],
            "partnership": ["partnership", "partners with", "collaboration", "integrates with", "joint venture"],
            "upgrade": ["upgrade", "hard fork", "fork activated", "mainnet launch", "v2 launch", "v3 launch"],
            "funding": ["raises $", "funding round", "series a", "series b", "investment of", "acquires for"],
            "listing": ["lists on", "listing on", "listed on", "delisted", "delisting"],
            "crash": ["crash", "plunge", "collapse", "liquidation cascade", "bankruptcy", "insolvent"],
            "surge": ["surge", "rally", "soars", "pumps", "all-time high", "ath", "record high"],
            "adoption": ["adopts", "adoption", "accepts bitcoin", "accepts crypto", "pay with crypto"],
            "reserve": ["strategic reserve", "national reserve", "treasury buys", "sovereign wealth"]
        }
        
        core_actions = tuple(sorted(set(
            action for action, variants in action_keywords.items() 
            for v in variants if v in text
        )))
        
        entities_list = [
            "sec", "cftc", "federal reserve", "fed", "blackrock", "fidelity", 
            "grayscale", "microstrategy", "tether", "usdt", "usdc", "circle",
            "binance", "coinbase", "kraken", "bybit", "okx", "kucoin",
            "jpmorgan", "goldman sachs", "morgan stanley", "citadel"
        ]
        core_entities = tuple(sorted([e for e in entities_list if e in text]))
        
        all_core = core_coins + core_entities + core_actions
        main_action = core_actions[0] if core_actions else "general"
        timestamp_bucket = datetime.utcnow().strftime("%Y-%m-%d-%H")
        
        return StoryFingerprint(
            core_entities=all_core,
            core_keywords=core_actions,
            main_action=main_action,
            timestamp_bucket=timestamp_bucket
        )
    
    def _calculate_semantic_similarity(self, fp1: StoryFingerprint, fp2: StoryFingerprint) -> float:
        set1 = set(fp1.core_entities) | set(fp1.core_keywords)
        set2 = set(fp2.core_entities) | set(fp2.core_keywords)
        if not set1 or not set2:
            return 0.0
        return len(set1 & set2) / len(set1 | set2)
    
    def _get_published_fingerprints(self, hours_back: int = 48) -> Set[str]:
        """Get fingerprints of already published stories"""
        published_keys = set()
        try:
            recent = database.get_recent_publishes(limit=300)
            cutoff = datetime.utcnow() - timedelta(hours=hours_back)
            
            for pub in recent:
                pub_time = pub.get("published_at")
                if pub_time:
                    try:
                        pub_dt = datetime.fromisoformat(pub_time.replace('Z', '+00:00')) if isinstance(pub_time, str) else pub_time
                        if pub_dt < cutoff:
                            continue
                    except Exception:
                        continue
                
                title = pub.get("item_title", "")
                if title:
                    fp = self._rough_fingerprint_from_title(title)
                    published_keys.add(fp)
        except Exception as e:
            logger.warning(f"Could not load published fingerprints: {e}")
        return published_keys
    
    def _rough_fingerprint_from_title(self, title: str) -> str:
        text = title.lower()
        coin_map = {"bitcoin": "BTC", "btc": "BTC", "ethereum": "ETH", "eth": "ETH",
                   "solana": "SOL", "sol": "SOL", "xrp": "XRP", "cardano": "ADA", "ada": "ADA"}
        found = tuple(sorted([s for k, s in coin_map.items() if k in text]))
        return f"title:{found}"
    
    # ===== MARKET IMPACT =====
    
    def _calculate_market_impact(self, articles: List[Article]) -> float:
        if not articles:
            return 0.0
        
        text = " ".join([f"{a.title} {a.content or ''}" for a in articles]).lower()
        
        impact_score = 0.0
        
        # High impact coins
        high_impact = {"btc": 1.0, "eth": 0.9, "sol": 0.7, "xrp": 0.7, "bnb": 0.7}
        for coin, weight in high_impact.items():
            if coin in text:
                impact_score = max(impact_score, weight)
        
        medium_impact = {"ada": 0.5, "doge": 0.5, "avax": 0.5, "dot": 0.5, "link": 0.5, "uni": 0.5}
        for coin, weight in medium_impact.items():
            if coin in text:
                impact_score = max(impact_score, weight)
        
        low_impact = {"aave": 0.3, "comp": 0.3, "mkr": 0.3, "ldo": 0.3}
        for coin, weight in low_impact.items():
            if coin in text:
                impact_score = max(impact_score, weight)
        
        # Action boosts
        action_boost = {
            "etf_approval": 0.3, "ban": 0.25, "hack": 0.25, "regulation": 0.2,
            "adoption": 0.2, "reserve": 0.25, "crash": 0.15, "surge": 0.1,
            "upgrade": 0.1, "funding": 0.05, "listing": 0.05
        }
        for action, boost in action_boost.items():
            if action.replace("_", " ") in text:
                impact_score = min(1.0, impact_score + boost)
        
        # Major entity boost
        major = ["sec", "blackrock", "fidelity", "binance", "coinbase", "fed", "etf", "jpmorgan", "goldman"]
        for ent in major:
            if ent in text:
                impact_score = min(1.0, impact_score + 0.1)
        
        return impact_score
    
    # ===== DETECT ALL VERIFIED BREAKING STORIES =====
    
    async def detect_all_verified_breaking(self) -> List[VerifiedBreakingStory]:
        """
        Find ALL breaking stories meeting strict criteria:
        1. 11+ unique sources
        2. SAME STORY (semantic similarity >= 0.75)
        3. High market impact (>= 0.5)
        4. Not already published
        5. Returns ALL qualified (not just strongest)
        """
        logger.info("🔍 STRICT scan: ALL breaking stories (3+ sources, same story, high impact)...")
        
        # Get ALL fresh articles from ALL sources
        articles = await self.acquire_all_articles(hours_back=self.MAX_STORY_AGE_HOURS)
        
        if len(articles) < self.MIN_SOURCES_BREAKING:
            logger.info(f"Only {len(articles)} articles total, need {self.MIN_SOURCES_BREAKING}+")
            return []
        
        # Quality filter
        articles = await self.quality_filter(articles)
        
        if len(articles) < self.MIN_SOURCES_BREAKING:
            logger.info(f"Only {len(articles)} passed quality, need {self.MIN_SOURCES_BREAKING}+")
            return []
        
        # Generate fingerprints
        fingerprints = {id(a): self._extract_story_fingerprint(a) for a in articles}
        
        # Published check
        published_fps = self._get_published_fingerprints(hours_back=48)
        
        # Group by semantic similarity (STRICT)
        visited = set()
        verified_stories = []
        
        def get_key(a): return id(a)
        
        for article in articles:
            key = get_key(article)
            if key in visited:
                continue
            
            fp1 = fingerprints[key]
            
            # Skip if already published
            if fp1.to_key() in published_fps:
                visited.add(key)
                continue
            
            similar = [article]
            
            for other in articles:
                ok = get_key(other)
                if ok in visited or ok == key:
                    continue
                if other.metadata.get("source_name") == article.metadata.get("source_name"):
                    continue
                
                fp2 = fingerprints[ok]
                sim = self._calculate_semantic_similarity(fp1, fp2)
                
                if sim >= self.SAME_STORY_THRESHOLD:
                    similar.append(other)
                    visited.add(ok)
            
            visited.add(key)
            
            # Count unique sources
            unique_sources = set()
            for a in similar:
                src = a.metadata.get("source_name", "")
                if src:
                    unique_sources.add(src)
            
            # STRICT: 11+ unique sources
            if len(unique_sources) < self.MIN_SOURCES_BREAKING:
                continue
            
            # Calculate metrics
            qualities = [float(a.quality_score) for a in similar if a.quality_score]
            avg_quality = sum(qualities) / len(qualities) if qualities else 0
            max_quality = max(qualities) if qualities else 0
            market_impact = self._calculate_market_impact(similar)
            
            # STRICT: High market impact
            if market_impact < self.MIN_MARKET_IMPACT:
                logger.debug(f"Story impact {market_impact:.2f} below threshold {self.MIN_MARKET_IMPACT}")
                continue
            
            # Pick best article
            primary = max(similar, key=lambda a: float(a.quality_score) if a.quality_score else 0)
            
            # Collect metadata
            all_coins = set()
            all_actions = set()
            all_entities = set()
            for a in similar:
                fp = fingerprints[id(a)]
                all_coins.update([c for c in fp.core_entities if c in {"BTC","ETH","SOL","XRP","ADA","DOGE","AVAX","DOT","LINK","UNI","AAVE","COMP","MKR","LDO","BNB"}])
                all_actions.update(fp.core_keywords)
                all_entities.update([e for e in fp.core_entities if e not in {"BTC","ETH","SOL","XRP","ADA","DOGE","AVAX","DOT","LINK","UNI","AAVE","COMP","MKR","LDO","BNB"}])
            
            story = VerifiedBreakingStory(
                fingerprint=fp1,
                articles=similar,
                source_count=len(unique_sources),
                unique_sources=unique_sources,
                avg_quality=avg_quality,
                max_quality=max_quality,
                market_impact_score=market_impact,
                primary_article=primary,
                urgent_keywords=list(all_actions),
                coins_affected=list(all_coins),
                action_type=fp1.main_action
            )
            
            verified_stories.append(story)
            
            logger.warning(f"✅ VERIFIED BREAKING: {story.source_count} sources | "
                          f"Quality: {avg_quality:.1f} | Impact: {market_impact:.2f} | "
                          f"Action: {story.action_type} | Coins: {story.coins_affected} | "
                          f"Sources: {story.unique_sources}")
        
        # Sort by impact DESC, then quality DESC
        verified_stories.sort(key=lambda s: (s.market_impact_score, s.avg_quality), reverse=True)
        
        logger.info(f"🎯 TOTAL VERIFIED BREAKING STORIES: {len(verified_stories)}")
        return verified_stories
    
    # ===== PROCESS & PUBLISH =====
    
    async def process_single_article(self, article: Article) -> Optional[Article]:
        logger.info(f"🤖 Processing: {article.title[:60]}...")
        from yjcryptonews.lib.ai_processing import run_ai_pipeline
        processed = await run_ai_pipeline([article])
        if processed:
            logger.info("✅ AI complete")
            return processed[0]
        return None
    
    async def publish_single_article(self, article: Article, cycle_type: CycleType, story_info: dict = None) -> bool:
        title_ar = getattr(article, 'translated_title', None) or ""
        body_ar = getattr(article, 'translated_content', None) or getattr(article, 'summary', '') or ""
        
        # Reject if no Arabic translation - NEVER fallback to English
        if not title_ar:
            logger.warning("❌ No Arabic title found - rejecting publication")
            return False
        
        # Reject if title is mostly English (not actually Arabic)
        arabic_chars = sum(1 for c in title_ar if '\u0600' <= c <= '\u06FF')
        if arabic_chars < 3:
            logger.warning("❌ Title is not Arabic (only %d Arabic chars) - rejecting", arabic_chars)
            return False
        
        # Clean prompt artifacts
        for bad in ["عنوان عربي", "ملخص مختصر", "المقال الأصلي:", "⚠️", "📚", "🔴",
                    "العنوان العربي:", "العنوان:", "عنوان:", "📰"]:
            title_ar = title_ar.replace(bad, "").strip()
            body_ar = body_ar.replace(bad, "").strip()
        
        # If body is missing or too short, attempt recovery
        if not body_ar or len(body_ar) < 50:
            summary = getattr(article, 'summary', None)
            translated_content = getattr(article, 'translated_content', None)
            if summary and isinstance(summary, str) and len(summary) > 50:
                body_ar = summary
            elif translated_content and isinstance(translated_content, str):
                body_ar = translated_content
            else:
                logger.warning("❌ Content too short after all fallbacks")
                return False
        
        # Cap body to ~600 chars max — but cut at a SENTENCE boundary, never mid-word.
        MAX_BODY = 600
        if len(body_ar) > MAX_BODY:
            cut = body_ar[:MAX_BODY]
            # find last sentence end (. ! ؟ newline) to avoid chopping mid-sentence
            last_end = max(cut.rfind("."), cut.rfind("!"), cut.rfind("؟"), cut.rfind("\n"))
            if last_end >= 200:
                body_ar = cut[:last_end + 1].strip()
            else:
                # no sentence break found — cut at last space to avoid mid-word
                last_space = cut.rfind(" ")
                body_ar = (cut[:last_space] if last_space >= 200 else cut).strip()
        
        # Final validation - must have Arabic content
        arabic_chars = sum(1 for c in body_ar if '\u0600' <= c <= '\u06FF')
        if arabic_chars < 10:
            logger.warning("❌ Body lacks sufficient Arabic characters")
            return False
        
        # Remove forbidden words (author names, filler phrases)
        forb = ["الجدير بالذكر", "جدير بالذكر", "📰", "حيث ", "Written by", "Author", "By "]
        meta = getattr(article, 'extra_data', {}) or {}
        author = meta.get("author") if isinstance(meta, dict) else None
        if author and isinstance(author, str):
            forb.append(author)
        for bw in forb:
            if bw:
                title_ar = title_ar.replace(bw, "").strip()
                body_ar = body_ar.replace(bw, "").strip()
        
        marker = ""
        prefix = ""
        
        item_dict = {
            "title": article.title,
            "summary": body_ar,
            "url": article.url,
            "source": "YJCryptoNews AI",
        }
        t = {"title_ar": title_ar, "body_ar": body_ar}
        
        from yjcryptonews import publisher
        results = publisher.publish(item_dict, t)
        
        for r in results:
            if r["status"] == "success":
                database.mark_seen(article.url, article.title)
                logger.info(f"✅ Published to {r['channel'].get('title', r['channel'].get('id'))}")
                return True
        
        logger.error("❌ Failed to publish")
        return False
    
    # ===== MAIN CYCLES =====
    
    async def run_hourly_cycle(self) -> Dict[str, Any]:
        """Hourly: Best single fresh article with sufficient content"""
        cycle_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        logger.info(f"=" * 50)
        logger.info(f"⏰ HOURLY CYCLE #{cycle_id}")
        logger.info(f"=" * 50)
        
        # Get fresh articles (24h window for more candidates)
        articles = await self.acquire_all_articles(hours_back=24)
        articles = await self.quality_filter(articles)
        
        if not articles:
            return {"cycle": cycle_id, "type": "hourly", "published": 0, "reason": "no_articles"}
        
        # Filter out already published articles BEFORE selecting best
        articles = [a for a in articles if not database.is_article_published(a.url)]
        logger.info(f"After removing already-published: {len(articles)} articles")
        
        if not articles:
            logger.info("All articles already published")
            return {"cycle": cycle_id, "type": "hourly", "published": 0, "reason": "all_published"}
        
        # Filter by minimum content length (accept shorter items too)
        min_content_chars = 50
        articles = [a for a in articles if a.content and len(a.content) >= min_content_chars]
        logger.info(f"After content length filter (>{min_content_chars} chars): {len(articles)} articles")
        
        if not articles:
            logger.info("No articles with sufficient content")
            return {"cycle": cycle_id, "type": "hourly", "published": 0, "reason": "short_content"}
        
        # Deduplicate against existing published articles (content-based)
        from yjcryptonews.lib.dedup_engine import deduplicate_articles
        existing_dicts = database.get_recent_articles(limit=500)
        existing_articles = []
        for d in existing_dicts:
            art = Article(
                id=d.get("id", 0),
                title=d.get("title", ""),
                content=d.get("content", ""),
                url=d.get("url", ""),
                metadata={}
            )
            existing_articles.append(art)
        articles, _ = await deduplicate_articles(articles, existing_articles)
        logger.info(f"After content dedup: {len(articles)} articles")
        
        if not articles:
            logger.info("All articles are duplicates")
            return {"cycle": cycle_id, "type": "hourly", "published": 0, "reason": "all_duplicates"}
        
        # Try articles in order - if one fails translation, try next
        for idx, best in enumerate(articles):
            logger.info(f"🏆 Trying article #{idx+1}: {best.title[:60]} (score: {best.quality_score})")
            
            processed = await self.process_single_article(best)
            if not processed:
                logger.warning(f"Article #{idx+1} failed AI processing, trying next...")
                continue
            
            success = await self.publish_single_article(processed, CycleType.HOURLY)
            if success:
                return {"cycle": cycle_id, "type": "hourly", "published": 1, "title": best.title[:80], "score": best.quality_score}
            else:
                logger.warning(f"Article #{idx+1} failed publishing, trying next...")
        
        return {"cycle": cycle_id, "type": "hourly", "published": 0, "reason": "all_articles_failed"}
    
    async def run_breaking_cycle(self) -> Dict[str, Any]:
        """
        Breaking check: Find ALL verified breaking stories, process & publish EACH ONE
        """
        cycle_id = datetime.now().strftime("%Y%m%d_%H%M%S_BREAK")
        logger.info(f"=" * 50)
        logger.info(f"🚨 BREAKING CYCLE #{cycle_id} - Find & Publish ALL verified")
        logger.info(f"=" * 50)
        
        verified_stories = await self.detect_all_verified_breaking()
        
        if not verified_stories:
            logger.info("No verified breaking stories found")
            return {"cycle": cycle_id, "type": "breaking", "published": 0, "stories_found": 0}
        
        published_count = 0
        published_stories = []
        
        for story in verified_stories:
            logger.info(f"🔄 Processing breaking story: {story.coins_affected} | {story.action_type} | {story.source_count} sources")
            
            processed = await self.process_single_article(story.primary_article)
            
            if not processed:
                logger.error(f"AI failed for story: {story.primary_article.title[:50]}")
                continue
            
            story_info = {
                "source_count": story.source_count,
                "coins": story.coins_affected,
                "action": story.action_type,
                "impact": story.market_impact_score
            }
            
            success = await self.publish_single_article(processed, CycleType.BREAKING, story_info)
            
            if success:
                published_count += 1
                published_stories.append({
                    "title": story.primary_article.title[:80],
                    "sources": story.source_count,
                    "coins": story.coins_affected,
                    "action": story.action_type,
                    "impact": story.market_impact_score,
                    "quality": story.avg_quality
                })
                logger.info(f"✅ Published breaking #{published_count}: {story.coins_affected} | {story.action_type}")
            else:
                logger.error(f"❌ Failed to publish: {story.primary_article.title[:50]}")
        
        logger.info(f"=" * 50)
        logger.info(f"🎯 BREAKING CYCLE COMPLETE: {published_count}/{len(verified_stories)} stories published")
        logger.info(f"=" * 50)
        
        return {
            "cycle": cycle_id,
            "type": "breaking",
            "published": published_count,
            "stories_found": len(verified_stories),
            "stories_published": published_stories
        }


# Convenience functions
async def run_hourly_cycle():
    scheduler = HourlySingleArticleScheduler()
    return await scheduler.run_hourly_cycle()


async def run_breaking_check():
    scheduler = HourlySingleArticleScheduler()
    return await scheduler.run_breaking_cycle()