"""
YJCryptoNews v3.0 - Layer 1: Data Acquisition
Scraping Engine for fetching content from websites
"""
import asyncio
import logging
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from bs4.element import Tag

from yjcryptonews.models.source import Source, SourceType, SourceStatus
from yjcryptonews import config

logger = logging.getLogger(__name__)


@dataclass
class ScrapingSelector:
    """CSS selectors for extracting article data"""
    article: str = ".article, .post, .entry, article, .news-item"
    title: str = "h1, h2, h3, .title, .headline"
    link: str = "a@href"
    content: str = ".content, .body, .article-body, .post-content, .entry-content"
    date: str = ".date, .published, .timestamp, time, [datetime]"
    author: str = ".author, .by-line, [rel='author']"
    tags: str = ".tags, .categories, .topics"


@dataclass
class ScrapedArticle:
    """Scraped article data"""
    title: str
    content: str
    url: str
    published_at: Optional[datetime] = None
    author: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class ScrapingEngine:
    """Web scraping engine with support for static and dynamic content"""

    def __init__(self):
        self._session: Optional[httpx.AsyncClient] = None
        self._semaphore = asyncio.Semaphore(config.data_acquisition.scraping.max_concurrent)
        self._rate_limiters: Dict[str, asyncio.Semaphore] = {}
        self._playwright_browser = None

    async def __aenter__(self):
        self._session = httpx.AsyncClient(
            timeout=httpx.Timeout(config.data_acquisition.scraping.timeout),
            headers={"User-Agent": config.data_acquisition.rss.user_agent},
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.aclose()
        if self._playwright_browser:
            await self._playwright_browser.close()

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL"""
        return urlparse(url).netloc

    def _get_rate_limiter(self, domain: str) -> asyncio.Semaphore:
        """Get or create rate limiter for domain"""
        if domain not in self._rate_limiters:
            self._rate_limiters[domain] = asyncio.Semaphore(config.data_acquisition.scraping.rate_limit)
        return self._rate_limiters[domain]

    def _extract_text(self, element: Optional[Tag], selector: str = "") -> str:
        """Extract text from element using selector"""
        if not element:
            return ""

        if selector and selector.endswith("@href"):
            # Extract href attribute
            sel = selector[:-5]
            link = element.select_one(sel)
            if link and link.get("href"):
                return link["href"].strip()
            return ""

        if selector and "@" in selector:
            # Extract attribute
            sel, attr = selector.split("@", 1)
            el = element.select_one(sel)
            if el and el.get(attr):
                return el[attr].strip()
            return ""

        if selector:
            el = element.select_one(selector)
            if el:
                return el.get_text(strip=True)
            return ""

        return element.get_text(strip=True)

    def _extract_all_text(self, element: Optional[Tag], selector: str) -> List[str]:
        """Extract all matching elements' text"""
        if not element:
            return []
        return [el.get_text(strip=True) for el in element.select(selector)]

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string to datetime"""
        if not date_str:
            return None

        # Try common formats
        formats = [
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%d %b %Y",
            "%b %d, %Y",
            "%B %d, %Y",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue

        # Try to extract datetime attribute
        return None

    def clean_content(self, content: str) -> str:
        """Clean and normalize content"""
        # Remove extra whitespace
        content = re.sub(r'\s+', ' ', content)
        # Remove common unwanted patterns
        content = re.sub(r'(Subscribe|Sign up|Newsletter|Follow us).*?(?=\.|$)', '', content, flags=re.IGNORECASE)
        return content.strip()

    async def _fetch_with_playwright(self, url: str) -> Optional[str]:
        """Fetch page using Playwright for JavaScript-rendered content"""
        if not config.data_acquisition.scraping.use_playwright:
            return None

        try:
            from playwright.async_api import async_playwright

            if not self._playwright_browser:
                playwright = await async_playwright().start()
                self._playwright_browser = await playwright.chromium.launch(headless=True)

            page = await self._playwright_browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=config.data_acquisition.scraping.timeout * 1000)
            content = await page.content()
            await page.close()
            return content
        except Exception as e:
            logger.warning(f"Playwright fetch failed for {url}: {e}")
            return None

    async def fetch_page(self, url: str) -> Optional[str]:
        """Fetch page content (static first, then dynamic if needed)"""
        async with self._semaphore:
            domain = self._get_domain(url)
            limiter = self._get_rate_limiter(domain)

            async with limiter:
                try:
                    logger.debug(f"Fetching page: {url}")

                    # Try static fetch first
                    response = await self._session.get(url)
                    response.raise_for_status()
                    content = response.text

                    # Check if content seems empty or requires JS
                    if len(content) < 1000 and config.data_acquisition.scraping.use_playwright:
                        logger.debug(f"Static content small, trying Playwright for {url}")
                        dynamic_content = await self._fetch_with_playwright(url)
                        if dynamic_content and len(dynamic_content) > len(content):
                            content = dynamic_content

                    return content

                except httpx.TimeoutException:
                    logger.error(f"Timeout fetching {url}")
                    return None
                except httpx.HTTPStatusError as e:
                    logger.error(f"HTTP error fetching {url}: {e.response.status_code}")
                    return None
                except Exception as e:
                    logger.error(f"Error fetching {url}: {e}")
                    return None

    def parse_articles(self, html: str, source: Source, base_url: str) -> List[ScrapedArticle]:
        """Parse articles from HTML using source-specific selectors"""
        soup = BeautifulSoup(html, 'html.parser')
        articles = []

        # Get selectors from source config or use defaults
        selectors_config = source.config.get("selectors", {})
        selectors = ScrapingSelector(**selectors_config) if selectors_config else ScrapingSelector()

        # Find article containers
        containers = soup.select(selectors.article)
        if not containers:
            # Try alternative: look for links that might be articles
            containers = soup.select("a[href]")

        for container in containers[:50]:  # Limit to 50 articles per page
            try:
                # Extract title
                title = self._extract_text(container, selectors.title)
                if not title or len(title) < 10:
                    continue

                # Extract link
                link = self._extract_text(container, selectors.link)
                if not link:
                    # Try to find any link in container
                    link_el = container.select_one("a[href]")
                    if link_el:
                        link = link_el.get("href", "")

                if not link:
                    continue

                # Make URL absolute
                url = urljoin(base_url, link)

                # Extract content (optional for list pages)
                content = self._extract_text(container, selectors.content)
                content = self.clean_content(content)

                # Extract date
                date_str = self._extract_text(container, selectors.date)
                published_at = self._parse_date(date_str) if date_str else None

                # Extract author
                author = self._extract_text(container, selectors.author)

                # Extract tags
                tags = self._extract_all_text(container, selectors.tags)

                article = ScrapedArticle(
                    title=title,
                    content=content,
                    url=url,
                    published_at=published_at,
                    author=author,
                    tags=tags,
                    metadata={
                        "selector_used": selectors.article,
                        "container_html": str(container)[:500],
                    }
                )
                articles.append(article)

            except Exception as e:
                logger.warning(f"Error parsing article container: {e}")
                continue

        return articles

    async def scrape_source(self, source: Source) -> List[ScrapedArticle]:
        """Scrape a single source"""
        logger.info(f"Scraping source: {source.name} ({source.url})")

        html = await self.fetch_page(source.url)
        if not html:
            logger.warning(f"No content fetched from {source.name}")
            return []

        articles = self.parse_articles(html, source, source.url)
        logger.info(f"Scraped {len(articles)} articles from {source.name}")

        return articles

    async def scrape_all_sources(self, sources: List[Source]) -> Dict[int, List[ScrapedArticle]]:
        """Scrape all sources concurrently"""
        scraping_sources = [
            s for s in sources
            if s.type == SourceType.SCRAPING.value and s.status == SourceStatus.ACTIVE.value
        ]

        tasks = [self.scrape_source(source) for source in scraping_sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        scraped_data = {}
        for source, result in zip(scraping_sources, results):
            if isinstance(result, Exception):
                logger.error(f"Error scraping {source.name}: {result}")
                scraped_data[source.id] = []
            else:
                scraped_data[source.id] = result

        return scraped_data


def create_scrapers_from_config() -> List[Source]:
    """Create Source objects from scraping targets in config"""
    cfg = config if isinstance(config, dict) else config.dict()
    scraping_targets = cfg.get("scraping_targets", [])
    sources = []
    for target in scraping_targets:
        # Skip targets explicitly disabled (dead endpoints: 403/404/429)
        if target.get("enabled", True) is False:
            continue
        source = Source(
            name=target["name"],
            url=target["url"],
            type=SourceType.SCRAPING.value,
            trust_score=target.get("trust_score", 80),
            status=SourceStatus.ACTIVE.value,
            config={
                "selectors": target.get("selectors", {}),
            }
        )
        sources.append(source)
    return sources


async def fetch_scraped_articles(sources: List[Source]) -> List["Article"]:
    """Main entry point for scraping"""
    from yjcryptonews.models.source import Article

    async with ScrapingEngine() as engine:
        scraped_data = await engine.scrape_all_sources(sources)

        all_articles = []
        for source in sources:
            if source.id in scraped_data:
                for scraped in scraped_data[source.id]:
                    article = Article(
                        title=scraped.title,
                        content=scraped.content,
                        url=scraped.url,
                        source_id=source.id,
                        language="en",
                        metadata={
                            "author": scraped.author,
                            "tags": scraped.tags,
                            "published_at": scraped.published_at.isoformat() if scraped.published_at else None,
                            "scraped_at": datetime.utcnow().isoformat(),
                            "scraper_metadata": scraped.metadata,
                        }
                    )
                    all_articles.append(article)

        return all_articles