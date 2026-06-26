"""
YJCryptoNews v3.0 - Layer 3: AI Processing
AI Summarizer with multi-provider fallback - محسن للغة العربية
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
class SummaryResult:
    """Result of summarization"""
    summary: str
    key_points: List[str]
    confidence: float
    provider_used: str
    model_used: str


class AISummarizer:
    """AI-powered content summarizer with provider fallback - Arabic only"""

    def __init__(self):
        self.client = AIClient("summarization")
        self.max_chars = cfg.summarization.max_chars
        self.key_points_count = cfg.summarization.key_points_count

    def _build_summarization_prompt(self, article: Article) -> str:
        """Build summarization prompt with strict Arabic-only guidelines - HUMAN-LIKE SUMMARY"""
        use_translated = article.translated_content and cfg.translation.preserve_technical_terms
        content = article.translated_content if use_translated else article.content or ""
        title = article.translated_title if use_translated else article.title

        return f"""أنت ملخص أخبار مالي عربي محترف. اكتب ملخصاً بشرياً طبيعياً بأسلوب صحفي راقٍ.

🔴 قواعد صارمة (مخالفة = رفض):
1. العربية الفصحى فقط - لا يُسمح بأي حرف إنجليزي أو صيني أو ياباني أو كوري
2. الملخص ≤ {self.max_chars} حرف بالضبط
3. استخراج {self.key_points_count} نقاط رئيسية فقط
4. أسلوب بشري طبيعي (Human-like) - كأنك تكتب تلخيصاً لمدير تنفيذي
5. ركز على: ماذا حدث، لماذا يهم، الأرقام/التواريخ الرئيسية
6. لا تكرار، لا حشو، لا ترجمة حرفية

العنوان: {title}
المحتوى: {content}

⚠️ التنسيق الإلزامي (لا تكتب شيئاً غير ذلك):
SUMMARY: [الملخص العربي البشري ≤ {self.max_chars} حرف]
KEY_POINTS:
1. [نقطة رئيسية 1 بالعربية بأسلوب بشري]
2. [نقطة رئيسية 2 بالعربية بأسلوب بشري]
3. [نقطة رئيسية 3 بالعربية بأسلوب بشري]"""

    def _validate_arabic_output(self, summary: str, key_points: List[str]) -> bool:
        """Strict validation of Arabic output"""
        full_text = summary + " " + " ".join(key_points)
        
        # Must have Arabic characters
        has_arabic = any('\u0600' <= c <= '\u06FF' for c in full_text)
        if not has_arabic:
            logger.warning(f"No Arabic characters in summary output")
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
            logger.warning("CJK characters detected in summary - REJECTED")
            return False
        
        # Reject if mostly Latin
        arabic_count = sum(1 for c in full_text if '\u0600' <= c <= '\u06FF')
        latin_count = sum(1 for c in full_text if c.isascii() and c.isalpha())
        if latin_count > arabic_count * 2:
            logger.warning(f"Too much Latin text in summary ({latin_count} vs {arabic_count} Arabic) - REJECTED")
            return False
        
        return True

    async def summarize_article(self, article: Article) -> SummaryResult:
        """Summarize a single article with strict Arabic validation"""
        prompt = self._build_summarization_prompt(article)

        messages = [{"role": "user", "content": prompt}]
        system_prompt = "أنت ملخص أخبار مالي عربي محترف متخصص في العملات الرقمية. مخرجاتك العربية فقط - لا يُسمح بأي لغة أخرى. التزم بالتنسيق المطلوب بدقة."

        result = await self.client.complete(messages, system_prompt, require_arabic=True)
        
        if not result:
            fallback_summary = self._create_fallback_summary(article)
            logger.warning(f"Summarization fallback used for article {article.id}")
            return SummaryResult(
                summary=fallback_summary,
                key_points=["تعذر التلخيص - جرب لاحقاً"] * self.key_points_count,
                confidence=0.3,
                provider_used="fallback",
                model_used="fallback",
            )
        
        content = result["content"]
        
        # Parse the response
        summary = ""
        key_points = []

        lines = content.split("\n")
        parsing_points = False
        for line in lines:
            line = line.strip()
            if line.startswith("SUMMARY:"):
                summary = line.replace("SUMMARY:", "").strip()
            elif line.startswith("KEY_POINTS:"):
                parsing_points = True
            elif parsing_points and line:
                point = line
                for prefix in ["1.", "2.", "3.", "4.", "5.", "-", "•"]:
                    if point.startswith(prefix):
                        point = point[len(prefix):].strip()
                        break
                if point:
                    key_points.append(point)

        # Validate summary length
        if len(summary) > self.max_chars:
            summary = summary[:self.max_chars - 3] + "..."

        # Validate Arabic output
        if not self._validate_arabic_output(summary, key_points):
            fallback_summary = self._create_fallback_summary(article)
            return SummaryResult(
                summary=fallback_summary,
                key_points=["تعذر التلخيص - مخرجات غير عربية"] * self.key_points_count,
                confidence=0.2,
                provider_used="fallback",
                model_used="fallback",
            )

        # Ensure we have the right number of key points
        key_points = key_points[:self.key_points_count]
        while len(key_points) < self.key_points_count:
            key_points.append("")

        return SummaryResult(
            summary=summary,
            key_points=key_points,
            confidence=0.9,
            provider_used=result["provider"],
            model_used=result["model"],
        )

    def _create_fallback_summary(self, article: Article) -> str:
        """Create a basic fallback summary - IN ARABIC from translated content"""
        content = article.translated_content or article.content or ""
        # Take first few sentences from translated content
        sentences = content.split(". ")
        summary = ". ".join(sentences[:3]) + "."
        if len(summary) > self.max_chars:
            summary = summary[:self.max_chars - 3] + "..."
        return summary

    async def summarize_batch(self, articles: List[Article]) -> List[Article]:
        """Summarize multiple articles concurrently"""
        semaphore = asyncio.Semaphore(3)

        async def summarize_one(article: Article) -> Article:
            async with semaphore:
                result = await self.summarize_article(article)
                article.summary = result.summary
                article.key_points = result.key_points
                article.metadata["summarization"] = {
                    "confidence": result.confidence,
                    "provider_used": result.provider_used,
                    "model_used": result.model_used,
                    "summarized_at": datetime.utcnow().isoformat(),
                    "original_length": len(article.content or ""),
                    "summary_length": len(result.summary),
                }
                return article

        tasks = [summarize_one(article) for article in articles]
        return await asyncio.gather(*tasks)


async def summarize_articles(articles: List[Article]) -> List[Article]:
    """Main entry point for summarization"""
    summarizer = AISummarizer()
    return await summarizer.summarize_batch(articles)