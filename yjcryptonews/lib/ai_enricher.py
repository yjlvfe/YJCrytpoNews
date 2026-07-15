"""
YJCryptoNews v3.0 - Layer 3: AI Processing
AI Enricher for context enrichment with multi-provider fallback - محسن للغة العربية
"""
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from yjcryptonews.models.source import Article
from yjcryptonews import config as cfg
from yjcryptonews.lib.ai_client import AIClient

logger = logging.getLogger(__name__)


@dataclass
class EnrichmentResult:
    """Result of context enrichment"""
    market_context: str
    historical_comparison: str
    related_coins: List[str]
    confidence: float
    provider_used: str
    model_used: str


class AIEnricher:
    """AI-powered context enrichment for articles with provider fallback - Arabic only"""

    def __init__(self):
        self.client = AIClient("enrichment")
        self.add_market = cfg.enrichment.add_market_context
        self.add_historical = cfg.enrichment.add_historical_comparison
        self.add_related = cfg.enrichment.add_related_coins

    def _extract_entities(self, article: Article) -> Dict[str, Any]:
        """Extract relevant entities from article for enrichment"""
        text = f"{article.title} {article.content or ''}"
        entities = {
            "coins": [],
            "exchanges": [],
            "protocols": [],
            "people": [],
            "numbers": [],
        }

        # Known crypto entities (simplified)
        coin_keywords = ["bitcoin", "btc", "ethereum", "eth", "solana", "sol", "cardano", "ada",
                        "ripple", "xrp", "polkadot", "dot", "dogecoin", "doge", "avalanche", "avax",
                        "polygon", "matic", "chainlink", "link", "uniswap", "uni", "aave", "compound"]

        exchange_keywords = ["binance", "coinbase", "kraken", "bybit", "okx", "kucoin", "gemini"]

        protocol_keywords = ["uniswap", "aave", "compound", "makerdao", "lido", "curve", "balancer"]

        text_lower = text.lower()
        for kw in coin_keywords:
            if kw in text_lower:
                entities["coins"].append(kw.upper())

        for kw in exchange_keywords:
            if kw in text_lower:
                entities["exchanges"].append(kw.capitalize())

        for kw in protocol_keywords:
            if kw in text_lower:
                entities["protocols"].append(kw.capitalize())

        # Extract numbers with context
        import re
        for match in re.finditer(r'(\$?[\d,]+\.?\d*\s*[%$€£]?(?:million|billion|trillion)?)', text):
            entities["numbers"].append(match.group().strip())

        # Deduplicate
        for key in entities:
            entities[key] = list(set(entities[key]))

        return entities

    def _build_enrichment_prompt(self, article: Article, entities: Dict[str, Any]) -> str:
        """Build enrichment prompt with strict Arabic-only guidelines - HUMAN-LIKE ANALYSIS"""
        content = article.translated_content or article.content or ""
        title = article.translated_title or article.title

        prompt = f"""أنت محلل أسواق مالي عربي محترف. قدم إثراء سياقياً بأسلوب بشري طبيعي وتحليلي راقٍ.

🔴 قواعد صارمة (مخالفة = رفض):
1. العربية الفصحى فقط - لا يُسمح بأي حرف إنجليزي أو صيني أو ياباني أو كوري
2. أسلوب بشري طبيعي (Human-like) - كأنك تكتب لمدير صندوق استثماري
3. تحليل دقيق مبني على الواقع - لا تخمينات
4. لا حشو، لا تكرار، لا ترجمة حرفية

الخبر الأصلي:
العنوان: {title}
المحتوى: {content}

الكيانات المكتشفة:
- العملات: {', '.join(entities['coins']) or 'لا يوجد'}
- المنصات: {', '.join(entities['exchanges']) or 'لا يوجد'}
- البروتوكولات: {', '.join(entities['protocols']) or 'لا يوجد'}
- الأرقام الرئيسية: {', '.join(entities['numbers']) or 'لا يوجد'}

يرجى تزويد الأقسام التالية بالعربية بأسلوب بشري طبيعي:\n"""

        if self.add_market:
            prompt += """\n\nMARKET_CONTEXT: [سياق السوق الحالي للعملات/البروتوكولات المذكورة - اتجاهات الأسعار، معنويات السوق، مقاييس ذات صلة - بأسلوب بشري طبيعي]"""

        if self.add_historical:
            prompt += """\n\nHISTORICAL_COMPARISON: [مقارنة تاريخية - أحداث سابقة مشابهة، كيف تفاعل السوق سابقاً - بأسلوب بشري طبيعي]"""

        if self.add_related:
            prompt += """\n\nRELATED_COINS: [عملات/أصول أخرى قد تتأثر بهذا الخبر - قائمة بالعربية]"""

        prompt += """

⚠️ التنسيق الإلزامي (لا تكتب شيئاً غير ذلك):
MARKET_CONTEXT: [النص بالعربية بأسلوب بشري]
HISTORICAL_COMPARISON: [النص بالعربية بأسلوب بشري]
RELATED_COINS: [قائمة مفصولة بفواصل بالعربية]"""

        return prompt

    def _validate_arabic_output(self, market_context: str, historical_comparison: str, related_coins: List[str]) -> bool:
        """Strict validation of Arabic output"""
        full_text = market_context + " " + historical_comparison + " " + " ".join(related_coins)
        
        if not full_text.strip():
            return True  # Empty is OK for enrichment
        
        # Must have Arabic characters if not empty
        has_arabic = any('\u0600' <= c <= '\u06FF' for c in full_text)
        if not has_arabic:
            logger.warning("Enrichment: No Arabic characters in output")
            return False
        
        # Reject CJK characters
        has_cjk = any(
            '\u3400' <= c <= '\u4DBF' or
            '\u4E00' <= c <= '\u9FFF' or
            '\u3040' <= c <= '\u309F' or
            '\u30A0' <= c <= '\u30FF' or
            '\uAC00' <= c <= '\uD7AF' or
            '\uFF00' <= c <= '\uFFEF'
            for c in full_text
        )
        if has_cjk:
            logger.warning("Enrichment: CJK characters detected - REJECTED")
            return False
        
        return True

    async def enrich_article(self, article: Article) -> EnrichmentResult:
        """Enrich a single article with context - Arabic only"""
        entities = self._extract_entities(article)
        prompt = self._build_enrichment_prompt(article, entities)

        messages = [{"role": "user", "content": prompt}]
        system_prompt = "أنت محلل أسواق عملات رقمية محترف يقدم إثراء سياق للأخبار. مخرجاتك العربية فقط - لا يُسمح بأي لغة أخرى. التزم بالتنسيق المطلوب بدقة."

        result = await self.client.complete(messages, system_prompt, require_arabic=True)
        
        if not result:
            logger.warning(f"Enrichment failed for article {article.id} - all providers failed")
            return EnrichmentResult(
                market_context="",
                historical_comparison="",
                related_coins=[],
                confidence=0.0,
                provider_used="fallback",
                model_used="fallback",
            )
        
        content = result["content"]

        # Parse the response - flexible parsing
        market_context = ""
        historical_comparison = ""
        related_coins = []
        lines = content.split("\n")
        found_mc = False
        found_hc = False
        found_rc = False
        for line in lines:
            line = line.strip()
            if line.startswith("MARKET_CONTEXT:"):
                market_context = line.replace("MARKET_CONTEXT:", "").strip()
                found_mc = True
            elif line.startswith("HISTORICAL_COMPARISON:"):
                historical_comparison = line.replace("HISTORICAL_COMPARISON:", "").strip()
                found_hc = True
            elif line.startswith("RELATED_COINS:"):
                coins_str = line.replace("RELATED_COINS:", "").strip()
                related_coins = [c.strip() for c in coins_str.split(",") if c.strip()]
                found_rc = True

        # Heuristic fallback if format markers missing
        if not any([found_mc, found_hc, found_rc]) and content.strip():
            raw = content.strip()
            sentences = [s.strip() for s in raw.split("\n") if s.strip()]
            if sentences:
                market_context = " ".join(sentences[:2])
                if len(sentences) > 2:
                    historical_comparison = " ".join(sentences[2:4])
                if len(sentences) > 4:
                    related_coins = [c.strip() for c in sentences[4].replace("،", ",").replace(";", ",").split(",") if c.strip()]

        # Clean artifacts
        artifacts = [
            "MARKET_CONTEXT:", "HISTORICAL_COMPARISON:", "RELATED_COINS:",
            "MARKET_CONTEXT :", "تاريخيا:", "سياق السوق:",
        ]
        for artifact in artifacts:
            market_context = market_context.replace(artifact, "").strip()
            historical_comparison = historical_comparison.replace(artifact, "").strip()

        # Validate Arabic output
        if not self._validate_arabic_output(market_context, historical_comparison, related_coins):
            return EnrichmentResult(
                market_context="",
                historical_comparison="",
                related_coins=[],
                confidence=0.0,
                provider_used="fallback",
                model_used="fallback",
            )

        return EnrichmentResult(
            market_context=market_context,
            historical_comparison=historical_comparison,
            related_coins=related_coins,
            confidence=0.85,
            provider_used=result["provider"],
            model_used=result["model"],
        )

    async def enrich_batch(self, articles: List[Article]) -> List[Article]:
        """Enrich multiple articles concurrently"""
        semaphore = asyncio.Semaphore(2)  # Lower concurrency for enrichment

        async def enrich_one(article: Article) -> Article:
            async with semaphore:
                result = await self.enrich_article(article)
                article.metadata["enrichment"] = {
                    "market_context": result.market_context,
                    "historical_comparison": result.historical_comparison,
                    "related_coins": result.related_coins,
                    "confidence": result.confidence,
                    "provider_used": result.provider_used,
                    "model_used": result.model_used,
                    "enriched_at": datetime.utcnow().isoformat(),
                }
                return article

        tasks = [enrich_one(article) for article in articles]
        return await asyncio.gather(*tasks)


async def enrich_articles(articles: List[Article]) -> List[Article]:
    """Main entry point for enrichment"""
    enricher = AIEnricher()
    return await enricher.enrich_batch(articles)