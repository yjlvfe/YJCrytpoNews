"""
YJCryptoNews v3.0 - Layer 1: Data Acquisition
API Collectors for fetching data from free APIs
"""
import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass
from abc import ABC, abstractmethod

import httpx

from yjcryptonews.models.source import Source, Article, SourceType, SourceStatus
from yjcryptonews import config

logger = logging.getLogger(__name__)


@dataclass
class APIResponse:
    """Standardized API response"""
    success: bool
    data: Any = None
    error: Optional[str] = None
    rate_limit_remaining: Optional[int] = None
    rate_limit_reset: Optional[datetime] = None


class BaseAPICollector(ABC):
    """Base class for API collectors"""

    def __init__(self, session: httpx.AsyncClient):
        self.session = session
        self.name = self.__class__.__name__

    @abstractmethod
    async def fetch(self, **kwargs) -> APIResponse:
        """Fetch data from API"""
        pass

    @abstractmethod
    def parse_articles(self, data: Any, source: Source) -> List[Article]:
        """Parse API response into Article models"""
        pass

    async def collect(self, source: Source, **kwargs) -> List[Article]:
        """Main collection method"""
        response = await self.fetch(**kwargs)
        if not response.success:
            logger.error(f"{self.name} error: {response.error}")
            return []
        return self.parse_articles(response.data, source)


class CoinGeckoCollector(BaseAPICollector):
    """CoinGecko API collector for market data and news"""

    BASE_URL = "https://api.coingecko.com/api/v3"

    async def fetch(self, **kwargs) -> APIResponse:
        try:
            # Get trending coins
            response = await self.session.get(f"{self.BASE_URL}/search/trending")
            response.raise_for_status()
            return APIResponse(success=True, data=response.json())
        except Exception as e:
            return APIResponse(success=False, error=str(e))

    def parse_articles(self, data: Any, source: Source) -> List[Article]:
        articles = []
        try:
            coins = data.get("coins", [])
            for coin_data in coins[:10]:  # Top 10 trending
                coin = coin_data.get("item", {})
                article = Article(
                    title=f"{coin.get('name', '')} ({coin.get('symbol', '').upper()}) Trending on CoinGecko",
                    content=f"Market cap rank: {coin.get('market_cap_rank', 'N/A')}\n"
                            f"Price (BTC): {coin.get('price_btc', 'N/A')}\n"
                            f"Score: {coin.get('score', 'N/A')}",
                    url=f"https://www.coingecko.com/en/coins/{coin.get('id', '')}",
                    source_id=source.id,
                    language="en",
                    metadata={
                        "coin_id": coin.get("id"),
                        "symbol": coin.get("symbol"),
                        "market_cap_rank": coin.get("market_cap_rank"),
                        "price_btc": coin.get("price_btc"),
                        "score": coin.get("score"),
                        "collected_at": datetime.utcnow().isoformat(),
                    }
                )
                articles.append(article)
        except Exception as e:
            logger.error(f"Error parsing CoinGecko data: {e}")

        return articles


class CoinMarketCapCollector(BaseAPICollector):
    """CoinMarketCap API collector (requires API key for full access)"""

    BASE_URL = "https://pro-api.coinmarketcap.com/v1"

    def __init__(self, session: httpx.AsyncClient, api_key: Optional[str] = None):
        super().__init__(session)
        self.api_key = api_key

    async def fetch(self, **kwargs) -> APIResponse:
        if not self.api_key:
            return APIResponse(success=False, error="No API key provided")

        try:
            headers = {"X-CMC_PRO_API_KEY": self.api_key}
            response = await self.session.get(
                f"{self.BASE_URL}/cryptocurrency/listings/latest",
                headers=headers,
                params={"limit": 10, "sort": "percent_change_24h", "sort_dir": "desc"}
            )
            response.raise_for_status()
            return APIResponse(success=True, data=response.json())
        except Exception as e:
            return APIResponse(success=False, error=str(e))

    def parse_articles(self, data: Any, source: Source) -> List[Article]:
        articles = []
        try:
            for coin in data.get("data", []):
                quote = coin.get("quote", {}).get("USD", {})
                article = Article(
                    title=f"{coin.get('name', '')} ({coin.get('symbol', '')}) - "
                          f"{quote.get('percent_change_24h', 0):.2f}% 24h",
                    content=f"Price: ${quote.get('price', 0):.4f}\n"
                            f"Market Cap: ${quote.get('market_cap', 0):,.0f}\n"
                            f"Volume 24h: ${quote.get('volume_24h', 0):,.0f}\n"
                            f"Change 24h: {quote.get('percent_change_24h', 0):.2f}%",
                    url=f"https://coinmarketcap.com/currencies/{coin.get('slug', '')}/",
                    source_id=source.id,
                    language="en",
                    metadata={
                        "cmc_id": coin.get("id"),
                        "symbol": coin.get("symbol"),
                        "price": quote.get("price"),
                        "percent_change_24h": quote.get("percent_change_24h"),
                        "market_cap": quote.get("market_cap"),
                        "volume_24h": quote.get("volume_24h"),
                        "collected_at": datetime.utcnow().isoformat(),
                    }
                )
                articles.append(article)
        except Exception as e:
            logger.error(f"Error parsing CoinMarketCap data: {e}")

        return articles


class FearGreedCollector(BaseAPICollector):
    """Alternative.me Fear & Greed Index collector"""

    BASE_URL = "https://api.alternative.me/fng/"

    async def fetch(self, **kwargs) -> APIResponse:
        try:
            response = await self.session.get(self.BASE_URL, params={"limit": 10})
            response.raise_for_status()
            return APIResponse(success=True, data=response.json())
        except Exception as e:
            return APIResponse(success=False, error=str(e))

    def parse_articles(self, data: Any, source: Source) -> List[Article]:
        articles = []
        try:
            for item in data.get("data", []):
                value = int(item.get("value", 0))
                classification = item.get("value_classification", "Neutral")

                article = Article(
                    title=f"Crypto Fear & Greed Index: {value} ({classification})",
                    content=f"Current value: {value}/100\n"
                            f"Classification: {classification}\n"
                            f"Date: {item.get('timestamp', 'N/A')}",
                    url="https://alternative.me/crypto/fear-and-greed-index/",
                    source_id=source.id,
                    language="en",
                    metadata={
                        "value": value,
                        "classification": classification,
                        "timestamp": item.get("timestamp"),
                        "time_until_update": item.get("time_until_update"),
                        "collected_at": datetime.utcnow().isoformat(),
                    }
                )
                articles.append(article)
        except Exception as e:
            logger.error(f"Error parsing Fear & Greed data: {e}")

        return articles


class DefiLlamaCollector(BaseAPICollector):
    """DeFi Llama API collector for TVL and protocol data"""

    BASE_URL = "https://api.llama.fi"

    async def fetch(self, **kwargs) -> APIResponse:
        try:
            # Get protocols with highest TVL
            response = await self.session.get(f"{self.BASE_URL}/protocols")
            response.raise_for_status()
            return APIResponse(success=True, data=response.json())
        except Exception as e:
            return APIResponse(success=False, error=str(e))

    def parse_articles(self, data: Any, source: Source) -> List[Article]:
        articles = []
        try:
            # Top 10 protocols by TVL
            sorted_protocols = sorted(data, key=lambda x: x.get("tvl", 0), reverse=True)[:10]

            for protocol in sorted_protocols:
                article = Article(
                    title=f"DeFi Protocol: {protocol.get('name', '')} - TVL: ${protocol.get('tvl', 0):,.0f}",
                    content=f"Category: {protocol.get('category', 'N/A')}\n"
                            f"Chains: {', '.join(protocol.get('chains', []))}\n"
                            f"TVL: ${protocol.get('tvl', 0):,.0f}\n"
                            f"Change 24h: {protocol.get('change_24h', 0):.2f}%\n"
                            f"Change 7d: {protocol.get('change_7d', 0):.2f}%",
                    url=protocol.get("url", "#"),
                    source_id=source.id,
                    language="en",
                    metadata={
                        "protocol_id": protocol.get("id"),
                        "name": protocol.get("name"),
                        "category": protocol.get("category"),
                        "chains": protocol.get("chains"),
                        "tvl": protocol.get("tvl"),
                        "change_24h": protocol.get("change_24h"),
                        "change_7d": protocol.get("change_7d"),
                        "collected_at": datetime.utcnow().isoformat(),
                    }
                )
                articles.append(article)
        except Exception as e:
            logger.error(f"Error parsing DeFi Llama data: {e}")

        return articles


class GitHubTrendingCollector(BaseAPICollector):
    """GitHub Trending collector for crypto-related repos"""

    BASE_URL = "https://ghapi.huchen.dev/repositories"

    async def fetch(self, **kwargs) -> APIResponse:
        try:
            # Search for crypto/blockchain related trending repos
            response = await self.session.get(
                self.BASE_URL,
                params={
                    "language": "",
                    "since": "daily",
                    "spoken_language_code": "en",
                }
            )
            response.raise_for_status()
            return APIResponse(success=True, data=response.json())
        except Exception as e:
            return APIResponse(success=False, error=str(e))

    def parse_articles(self, data: Any, source: Source) -> List[Article]:
        articles = []
        crypto_keywords = ["blockchain", "crypto", "bitcoin", "ethereum", "defi", "web3",
                          "solidity", "smart contract", "wallet", "nft", "dao"]

        try:
            for repo in data[:20]:
                description = (repo.get("description") or "").lower()
                if any(kw in description for kw in crypto_keywords):
                    article = Article(
                        title=f"GitHub Trending: {repo.get('author', '')}/{repo.get('name', '')}",
                        content=f"Description: {repo.get('description', 'N/A')}\n"
                                f"Language: {repo.get('language', 'N/A')}\n"
                                f"Stars: {repo.get('stars', 0)}\n"
                                f"Forks: {repo.get('forks', 0)}\n"
                                f"Stars today: {repo.get('current_period_stars', 0)}",
                        url=repo.get("url", "#"),
                        source_id=source.id,
                        language="en",
                        metadata={
                            "author": repo.get("author"),
                            "repo_name": repo.get("name"),
                            "description": repo.get("description"),
                            "language": repo.get("language"),
                            "stars": repo.get("stars"),
                            "forks": repo.get("forks"),
                            "stars_today": repo.get("current_period_stars"),
                            "collected_at": datetime.utcnow().isoformat(),
                        }
                    )
                    articles.append(article)
        except Exception as e:
            logger.error(f"Error parsing GitHub Trending data: {e}")

        return articles


class APICollectorManager:
    """Manages all API collectors"""

    def __init__(self, session: Optional[httpx.AsyncClient] = None):
        self.session = session or httpx.AsyncClient(
            timeout=httpx.Timeout(30),
            headers={"User-Agent": config.data_acquisition.rss.user_agent},
        )
        self.collectors: Dict[str, BaseAPICollector] = {}
        self._register_collectors()

    def _register_collectors(self):
        """Register all available collectors"""
        # CoinGecko (no auth needed)
        self.collectors["coingecko"] = CoinGeckoCollector(self.session)

        # CoinMarketCap (requires API key)
        cmc_key = config.sources.get("coinmarketcap_api_key")
        self.collectors["coinmarketcap"] = CoinMarketCapCollector(self.session, cmc_key)

        # Fear & Greed Index (no auth needed)
        self.collectors["fear_greed"] = FearGreedCollector(self.session)

        # DeFi Llama (no auth needed)
        self.collectors["defillama"] = DefiLlamaCollector(self.session)

        # GitHub Trending (no auth needed)
        self.collectors["github_trending"] = GitHubTrendingCollector(self.session)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.session.aclose()

    async def collect_all(self, sources: List[Source]) -> Dict[int, List[Article]]:
        """Collect from all API sources"""
        api_sources = [
            s for s in sources
            if s.type == SourceType.API.value and s.status == SourceStatus.ACTIVE.value
        ]

        results = {}
        for source in api_sources:
            collector = self.collectors.get(source.name.lower().replace(" ", "_"))
            if collector:
                try:
                    articles = await collector.collect(source)
                    results[source.id] = articles
                    logger.info(f"Collected {len(articles)} articles from {source.name}")
                except Exception as e:
                    logger.error(f"Error collecting from {source.name}: {e}")
                    results[source.id] = []
            else:
                logger.warning(f"No collector registered for {source.name}")
                results[source.id] = []

        return results

    def get_collector(self, name: str) -> Optional[BaseAPICollector]:
        """Get collector by name"""
        return self.collectors.get(name.lower())


def create_api_sources_from_config() -> List[Source]:
    """Create Source objects for API collectors"""
    sources = [
        Source(
            name="CoinGecko",
            url="https://api.coingecko.com/api/v3",
            type=SourceType.API.value,
            trust_score=90,
            status=SourceStatus.ACTIVE.value,
            config={"collector": "coingecko"}
        ),
        Source(
            name="Fear & Greed Index",
            url="https://api.alternative.me/fng/",
            type=SourceType.API.value,
            trust_score=85,
            status=SourceStatus.ACTIVE.value,
            config={"collector": "fear_greed"}
        ),
        Source(
            name="DeFi Llama",
            url="https://api.llama.fi",
            type=SourceType.API.value,
            trust_score=90,
            status=SourceStatus.ACTIVE.value,
            config={"collector": "defillama"}
        ),
        Source(
            name="GitHub Trending",
            url="https://ghapi.huchen.dev",
            type=SourceType.API.value,
            trust_score=75,
            status=SourceStatus.ACTIVE.value,
            config={"collector": "github_trending"}
        ),
    ]
    return sources


async def fetch_api_articles(sources: List[Source]) -> List[Article]:
    """Main entry point for API collection"""
    async with APICollectorManager() as manager:
        collected = await manager.collect_all(sources)

        all_articles = []
        for source in sources:
            if source.id in collected:
                all_articles.extend(collected[source.id])

        return all_articles