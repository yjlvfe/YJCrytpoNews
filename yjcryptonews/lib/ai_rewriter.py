"""
YJCryptoNews v3.0 - Layer 3: AI Processing
AI Smart Rewrite for generating original content
"""
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

import httpx

from yjcryptonews.models.source import Article
from yjcryptonews import config

logger = logging.getLogger(__name__)


@dataclass
class RewriteResult:
    """Result of smart rewrite"""
    rewritten_title: str
    rewritten_content: str
    unique_analysis: str
    confidence: float


class AIRewriter:
    """Smart rewrite engine for generating original content from facts"""

    def __init__(self):
        self.model = config.ai.models.enrichment  # Use enrichment model for rewrite
        self.max_tokens = config.ai.max_tokens.enrichment
        self.temperature = config.ai.temperature.enrichment
        self.base_url = config.ai.base_url

    def _extract_core_facts(self, article: Article) -> Dict[str, Any]:
        """Extract core facts (who, what, when, where, why) from article"""
        # Combine original and translated content
        title = article.translated_title or article.title
        content = article.translated_content or article.content or ""

        # Use the summary if available
        summary = article.summary or ""

        # Extract key points
        key_points = article.key_points or []

        return {
            "title": title,
            "content": content,
            "summary": summary,
            "key_points": key_points,
            "entities": article.metadata.get("enrichment", {}).get("related_coins", []),
        }

    def _build_rewrite_prompt(self, facts: Dict[str, Any]) -> str:
        """Build rewrite prompt for generating original narrative"""
        return f"""Rewrite the following cryptocurrency news into an original Arabic analysis article.

CORE FACTS:
Title: {facts['title']}
Summary: {facts['summary']}
Key Points:
{chr(10).join([f"- {kp}" for kp in facts['key_points']])}
Related Entities: {', '.join(facts['entities']) or 'None'}

ORIGINAL CONTENT (for reference):
{facts['content']}

REQUIREMENTS:
1. Write an ORIGINAL narrative article in Arabic - do not translate, rewrite
2. Use the facts as source material but create new analysis and perspective
3. Structure: Headline → Lead paragraph → Analysis sections → Conclusion
4. Add unique insights: implications, market impact, expert perspective
5. Professional Arabic financial journalism style
6. Length: 400-800 Arabic words
7. Preserve all factual accuracy - do not invent facts
8. Use proper Arabic terminology for crypto/finance

OUTPUT FORMAT:
REWRITTEN_TITLE: [Original Arabic headline]
REWRITTEN_CONTENT: [Full Arabic article]
UNIQUE_ANALYSIS: [Key analytical insights added]"""

    async def rewrite_article(self, article: Article) -> RewriteResult:
        """Rewrite a single article into original content"""
        facts = self._extract_core_facts(article)
        prompt = self._build_rewrite_prompt(facts)

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "You are a senior cryptocurrency financial analyst and journalist writing original Arabic analysis articles. You create unique narratives from factual source material."},
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature,
                }

                headers = {"Content-Type": "application/json"}
                response = await client.post(self.base_url, json=payload, headers=headers)
                response.raise_for_status()

                result = response.json()
                content = result["choices"][0]["message"]["content"]

                # Parse the response
                rewritten_title = ""
                rewritten_content = ""
                unique_analysis = ""

                current_section = ""
                for line in content.split("\n"):
                    line = line.strip()
                    if line.startswith("REWRITTEN_TITLE:"):
                        rewritten_title = line.replace("REWRITTEN_TITLE:", "").strip()
                        current_section = "title"
                    elif line.startswith("REWRITTEN_CONTENT:"):
                        rewritten_content = line.replace("REWRITTEN_CONTENT:", "").strip()
                        current_section = "content"
                    elif line.startswith("UNIQUE_ANALYSIS:"):
                        unique_analysis = line.replace("UNIQUE_ANALYSIS:", "").strip()
                        current_section = "analysis"
                    elif line and current_section == "content":
                        rewritten_content += "\n" + line
                    elif line and current_section == "analysis":
                        unique_analysis += "\n" + line

                return RewriteResult(
                    rewritten_title=rewritten_title or facts["title"],
                    rewritten_content=rewritten_content or facts["content"],
                    unique_analysis=unique_analysis,
                    confidence=0.9,
                )

            except Exception as e:
                logger.error(f"Rewrite failed for article {article.id}: {e}")
                return RewriteResult(
                    rewritten_title=facts["title"],
                    rewritten_content=facts["content"],
                    unique_analysis="",
                    confidence=0.0,
                )

    async def rewrite_batch(self, articles: List[Article]) -> List[Article]:
        """Rewrite multiple articles concurrently"""
        semaphore = asyncio.Semaphore(2)  # Low concurrency for rewrite

        async def rewrite_one(article: Article) -> Article:
            async with semaphore:
                result = await self.rewrite_article(article)
                article.metadata["rewrite"] = {
                    "rewritten_title": result.rewritten_title,
                    "rewritten_content": result.rewritten_content,
                    "unique_analysis": result.unique_analysis,
                    "confidence": result.confidence,
                    "rewritten_at": datetime.utcnow().isoformat(),
                }
                return article

        tasks = [rewrite_one(article) for article in articles]
        return await asyncio.gather(*tasks)


async def rewrite_articles(articles: List[Article]) -> List[Article]:
    """Main entry point for smart rewrite"""
    rewriter = AIRewriter()
    return await rewriter.rewrite_batch(articles)