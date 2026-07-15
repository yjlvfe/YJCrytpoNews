"""
RSS Aggregator for fetching and parsing RSS feeds
"""
import asyncio
import hashlib
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup

from yjcryptonews.models.source import Source, Article, SourceType, SourceStatus
from yjcryptonews import config

logger = logging.getLogger(__name__)


@dataclass
class RSSFeedItem:
    """Parsed RSS feed item"""
    title: str
    content: str
    url: str
    published_at: Optional[datetime]
    author: Optional[str]
    tags: List[str]
    media: List[Dict[str, Any]]


class RSSAggregator:
    """Aggregates news from RSS feeds"""

    def __init__(self, session: Optional[httpx.AsyncClient] = None):
        self.session = session or httpx.AsyncClient(
            timeout=httpx.Timeout(config.data_acquisition.rss.timeout),
            headers={"User-Agent": config.data_acquisition.rss.user_agent},
            follow_redirects=True,
        )
        self._semaphore = asyncio.Semaphore(config.data_acquisition.rss.max_concurrent)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.session.aclose()

    def _generate_hash(self, url: str) -> str:
        """Generate unique hash for URL"""
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def _parse_feed_item(self, entry: Any, feed_url: str, raw_xml: Optional[bytes] = None) -> Optional[RSSFeedItem]:
        """Parse a single feed entry"""
        try:
            # Get title
            title = getattr(entry, 'title', '').strip()
            if not title:
                return None

            # Get content - try multiple fields
            content = ""
            for field in ['content', 'summary', 'description']:
                val = getattr(entry, field, None)
                if val:
                    if isinstance(val, list) and val:
                        text = val[0].get('value', '') if isinstance(val[0], dict) else str(val[0])
                    elif isinstance(val, dict):
                        text = val.get('value', '')
                    else:
                        text = str(val)
                    # Only use if non-empty after stripping HTML
                    text = BeautifulSoup(text, 'html.parser').get_text(separator=' ', strip=True)
                    if text:
                        content = text
                        break

            # XML fallback: if feedparser failed, use ElementTree directly
            if not content and raw_xml:
                try:
                    root = ET.fromstring(raw_xml)
                    items = root.findall('.//item')
                    for item in items:
                        item_title = item.find('title')
                        if item_title is not None and item_title.text and title.lower() in item_title.text.lower():
                            desc = item.find('description')
                            if desc is not None and desc.text:
                                content = BeautifulSoup(desc.text, 'html.parser').get_text(separator=' ', strip=True)
                                break
                except Exception as ex:
                    logger.debug(f"XML fallback failed: {ex}")

            # Clean HTML from content
            if content:
                soup = BeautifulSoup(content, 'html.parser')
                content = soup.get_text(separator=' ', strip=True)
            
            # Fallback: if no content, use title as content (allow translation)
            if not content:
                content = title

            # Get URL
            url = getattr(entry, 'link', '').strip()
            if not url:
                return None

            # Make URL absolute
            url = urljoin(feed_url, url)

            # Get published date - try multiple fields
            published_at = None
            # First try parsed datetime tuples (feedparser standard)
            for field in ['published_parsed', 'updated_parsed', 'created_parsed']:
                val = getattr(entry, field, None)
                if val:
                    try:
                        published_at = datetime(*val[:6])
                        break
                    except (TypeError, ValueError):
                        continue
            
            # If no parsed date, try string date fields
            if not published_at:
                for field in ['published', 'updated', 'created', 'date', 'dc_date', 'dc:date']:
                    val = getattr(entry, field, None)
                    if val and isinstance(val, str):
                        try:
                            # Try multiple formats
                            for fmt in [
                                '%a, %d %b %Y %H:%M:%S %z',  # RFC 2822
                                '%a, %d %b %Y %H:%M:%S %Z',
                                '%Y-%m-%dT%H:%M:%S%z',      # ISO 8601
                                '%Y-%m-%dT%H:%M:%S.%f%z',
                                '%Y-%m-%dT%H:%M:%SZ',
                                '%Y-%m-%dT%H:%M:%S',
                                '%Y-%m-%d %H:%M:%S',
                                '%d %b %Y %H:%M:%S',
                            ]:
                                try:
                                    published_at = datetime.strptime(val.strip(), fmt)
                                    break
                                except ValueError:
                                    continue
                            if published_at:
                                break
                        except Exception:
                            continue

            # Get author
            author = getattr(entry, 'author', None)
            if not author:
                author = getattr(entry, 'author_detail', {}).get('name') if hasattr(entry, 'author_detail') else None

            # Get tags/categories
            tags = []
            for tag in getattr(entry, 'tags', []):
                if isinstance(tag, dict):
                    tags.append(tag.get('term', ''))
                else:
                    tags.append(str(tag))

            # Get media/enclosures
            media = []
            for enclosure in getattr(entry, 'enclosures', []):
                media.append({
                    'url': enclosure.get('href', ''),
                    'type': enclosure.get('type', ''),
                    'length': enclosure.get('length', 0),
                })

            return RSSFeedItem(
                title=title,
                content=content,
                url=url,
                published_at=published_at,
                author=author,
                tags=tags,
                media=media,
            )
        except Exception as e:
            logger.warning(f"Failed to parse feed item: {e}")
            return None

    async def fetch_feed(self, source: Source) -> List[RSSFeedItem]:
        """Fetch and parse a single RSS feed"""
        async with self._semaphore:
            try:
                logger.info(f"Fetching RSS feed: {source.name} ({source.url})")

                response = await self.session.get(source.url)
                response.raise_for_status()

                # Parse with feedparser
                feed = feedparser.parse(response.content)

                if feed.bozo and feed.bozo_exception:
                    logger.warning(f"Feed parsing warning for {source.name}: {feed.bozo_exception}")

                items = []
                for entry in feed.entries:
                    parsed = self._parse_feed_item(entry, source.url, raw_xml=response.content)
                    if parsed:
                        items.append(parsed)

                logger.info(f"Fetched {len(items)} items from {source.name}")
                return items

            except httpx.TimeoutException:
                logger.error(f"Timeout fetching {source.name}")
                return []
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error fetching {source.name}: {e.response.status_code}")
                return []
            except Exception as e:
                logger.error(f"Error fetching {source.name}: {e}")
                return []

    async def fetch_all_feeds(self, sources: List[Source]) -> Dict[int, List[RSSFeedItem]]:
        """Fetch all RSS feeds concurrently"""
        rss_sources = [s for s in sources if s.type == SourceType.RSS.value and s.status == SourceStatus.ACTIVE.value]

        tasks = [self.fetch_feed(source) for source in rss_sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        feed_items = {}
        for source, result in zip(rss_sources, results):
            if isinstance(result, Exception):
                logger.error(f"Error fetching {source.name}: {result}")
                feed_items[source.id] = []
            else:
                feed_items[source.id] = result

        return feed_items

    def items_to_articles(self, source: Source, items: List[RSSFeedItem]) -> List[Article]:
        """Convert RSS feed items to Article models"""
        articles = []
        for item in items:
            article = Article(
                title=item.title,
                content=item.content,
                url=item.url,
                source_id=source.id,
                language="en",  # Will be detected later
                published_at=item.published_at,  # SET published_at field
                metadata={
                    "author": item.author,
                    "tags": item.tags,
                    "media": item.media,
                    "published_at": item.published_at.isoformat() if item.published_at else None,
                    "fetched_at": datetime.utcnow().isoformat(),
                    "source_name": source.name,  # ADD source name for cross-source matching
                }
            )
            articles.append(article)

        return articles


async def fetch_rss_feeds(sources: List[Source]) -> List[Article]:
    """Main entry point for RSS feed fetching"""
    async with RSSAggregator() as aggregator:
        feed_items = await aggregator.fetch_all_feeds(sources)

        all_articles = []
        for source in sources:
            if source.id in feed_items:
                articles = aggregator.items_to_articles(source, feed_items[source.id])
                all_articles.extend(articles)

        return all_articles