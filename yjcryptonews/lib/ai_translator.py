"""
YJCryptoNews v3.0 - Layer 3: AI Processing
AI Translator with multi-provider fallback chain - محسن للغة العربية
"""
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from yjcryptonews.models.source import Article
from yjcryptonews import config
from yjcryptonews.lib.ai_client import AIClient

logger = logging.getLogger(__name__)


@dataclass
class TranslationResult:
    """Result of translation"""
    translated_title: str
    translated_content: str
    detected_language: str
    confidence: float
    preserved_terms: Dict[str, str]
    provider_used: str
    model_used: str


class AITranslator:
    """Smart translator with professional Arabic financial style and provider fallback"""

    def __init__(self):
        self.glossary = config.translation.terms_glossary if hasattr(config, 'translation') else {}
        self.client = AIClient("translation")

    def _build_translation_prompt(self, article: Article) -> str:
        """Build translation prompt - output MUST be clean Arabic only, NO labels, NO prefixes"""
        glossary = self.glossary
        if hasattr(glossary, 'dict'):
            glossary = glossary.dict()
        elif hasattr(glossary, '_cfg'):
            glossary = glossary._cfg
        elif not isinstance(glossary, dict):
            glossary = {}

        glossary_text = "\n".join([f"- {en}: {ar}" for en, ar in glossary.items()])
        title_val = getattr(article, 'title', '') or ''
        content_val = getattr(article, 'content', '') or ''

        return f"""أنت صحفي مالي عربي محترف. أعد صياغة هذا الخبر بأسلوب بشري طبيعي ومهني.

🔴 قواعد صارمة:
1. الفصحى العربية فقط - لا حروف إنجليزية ولا صينية/يابانية/كورية
2. احذف أسماء المؤلفين والمراسلين تماماً
3. احذف عبارات التعبئة: "الجدير بالذكر"، "يجدر الذكر"، "حيث"، "تجدر الإشارة"
4. الأرقام والنسب والرموز تبقى كما هي
5. نفس المعنى لكن بأسلوب عربي أصيل
6. العنوان: 10 إلى 15 كلمة عربية فقط
7. المحتوى: ملخص مختصر 2-3 أسطر فقط

📚 المصطلحات:
{glossary_text}

المقال الأصلي:
{title_val}

{content_val or ""}

⚠️ القاعدة الأخطر: لا تكتب "العنوان العربي" أو "المحتوى العربي" أو أي علامة قبل النص.
اكتب النص مباشرة بدون أي إشارة إلى الترجمة.
اكتب العنوان العربي أولاً (سطر واحد)، ثم سطرين فارغين، ثم الملخص العربي.
مثال - افعل هذا:
______
عنوان عربي خالي من أي ملاحظات

ملخص عربي هنا
______
ممنوع تماماً كتابة "العنوان العربي:" أو "المحتوى العربي:" أو أي لون أو forme. النص فقط."""

    def _validate_arabic_output(self, title: str, content: str, provider_name: str) -> bool:
        """Strict validation of Arabic output"""
        title_s = str(title) if title else ""
        content_s = str(content) if content else ""
        full_text = f"{title_s} {content_s}"
        
        # Must have Arabic characters
        has_arabic = any('\u0600' <= c <= '\u06FF' for c in full_text)
        if not has_arabic:
            logger.warning(f"{provider_name}: No Arabic characters in output")
            return False
        
        # Title MUST be Arabic (no English letters) - relaxed: allow up to 20% latin
        title_arabic = sum(1 for c in title_s if '\u0600' <= c <= '\u06FF')
        title_latin = sum(1 for c in title_s if c.isascii() and c.isalpha())
        if title_s and title_latin > title_arabic and title_latin > 3:
            logger.warning(f"{provider_name}: English letters in title - REJECTED ({title_latin} latin vs {title_arabic} arabic)")
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
            logger.warning(f"{provider_name}: CJK characters detected - REJECTED")
            return False
        
        # Content must be mostly Arabic (allow crypto tickers)
        content_arabic = sum(1 for c in content_s if '\u0600' <= c <= '\u06FF')
        content_latin = sum(1 for c in content_s if c.isascii() and c.isalpha())
        if content_s and content_latin > 0:
            ratio = content_arabic / (content_latin + content_arabic) if (content_latin + content_arabic) > 0 else 0
            if ratio < 0.4:
                logger.warning(f"{provider_name}: Too much Latin text (Arabic ratio {ratio:.1%}) - REJECTED")
                return False
        
        return True

    async def _try_translate_title_fallback(self, provider_name: str, title_en, client) -> Optional[str]:
        """Try to translate just the title if main translation failed on title"""
        title_str = str(title_en) if not isinstance(title_en, str) else title_en
        if not title_str:
            return None
        
        prompt = f"ترجم هذا العنوان إلى العربية فقط:\n{title_str}\nالعنوان المترجم:"
        messages = [{"role": "user", "content": prompt}]
        system_prompt = "مترجم عناوين عربي محترف. المخرجات عربية فقط بشكل كامل."
        result = await client.complete(messages, system_prompt, require_arabic=True)
        if result:
            text = result["content"].strip()
            if isinstance(text, str):
                has_eng = any(c.isascii() and c.isalpha() for c in text)
                if not has_eng and any('\u0600' <= c <= '\u06FF' for c in text):
                    return text
        return None

    async def _try_translate(self, provider_name: str, article: Article) -> Optional[TranslationResult]:
        """Try translation using AIClient with provider override"""
        
        prompt = self._build_translation_prompt(article)
        messages = [{"role": "user", "content": prompt}]
        system_prompt = "أنت مترجم مالي عربي محترف متخصص في أخبار العملات الرقمية. مخرجاتك عربية فقط - لا يُسمح بأي لغة أخرى في العنوان أو المحتوى."

        result = await self.client.complete(messages, system_prompt, require_arabic=True)
        
        if not result:
            return None
        
        content = result["content"]

        # Parse: model outputs clean Arabic text (maybe with [Title] [Body] markers)
        # Find the first Arabic text block (title) and second block (body)
        lines = content.split("\n")
        raw = content.strip()

        # Remove any wrapper markers from model
        for marker in ['[', ']', 'TRANSLATED_TITLE:', 'TRANSLATED_CONTENT:', 'العنوان:', 'المحتوى:', '---']:
            raw = raw.replace(marker, '')

        parts = [p.strip() for p in raw.split("\n\n") if p.strip()]

        if len(parts) >= 2:
            translated_title = parts[0]
            translated_content = " ".join(parts[1:4])  # skip key points/extra
        elif len(parts) == 1:
            translated_title = parts[0]
            translated_content = parts[0]
        else:
            return None
        
        # Final validation
        if not translated_content or len(translated_content) < 10:
            return None
        
        # Fallback: if title is English but content is Arabic, try translating title alone
        title_val = translated_title or ""
        content_val = translated_content or ""
        title_is_good = (not any(c.isascii() and c.isalpha() for c in title_val)) if title_val else False
        content_is_good = any('\u0600' <= c <= '\u06FF' for c in content_val) if content_val else False
        
        if not title_is_good and content_is_good:
            article_title = getattr(article, 'title', None)
            if article_title:
                article_title = str(article_title)
                logger.info(f"Trying title-only fallback for: {article_title[:40]}...")
                title_fb = await self._try_translate_title_fallback(provider_name, article_title, self.client)
                if title_fb:
                    translated_title = title_fb
                    title_val = translated_title
                    logger.info(f"✅ Title fallback succeeded: {translated_title[:50]}")
        
        if not self._validate_arabic_output(title_val, content_val, result["provider"]):
            return None
        
        # Extract preserved terms
        glossary = self.glossary
        if hasattr(glossary, 'dict'):
            glossary = glossary.dict()
        elif hasattr(glossary, '_cfg'):
            glossary = glossary._cfg
        elif not isinstance(glossary, dict):
            glossary = {}
        
        preserved = {}
        article_title_raw = getattr(article, 'title', '') or ''
        article_content_raw = getattr(article, 'content', '') or ''
        full_text = f"{article_title_raw} {article_content_raw}"
        for en, ar in glossary.items():
            if en.lower() in full_text.lower():
                preserved[en] = ar
        
        return TranslationResult(
            translated_title=translated_title,
            translated_content=translated_content,
            detected_language="en",
            confidence=0.95,
            preserved_terms=preserved,
            provider_used=result["provider"],
            model_used=result["model"],
        )

    async def translate_article(self, article: Article) -> TranslationResult:
        """Translate a single article with provider fallback via AIClient"""
        result = await self._try_translate("", article)
        if result:
            logger.info(f"✅ Translation successful with {result.provider_used} ({result.model_used})")
            # Add AI fields to article
            article.title_emoji = self._extract_title_emoji(result.translated_title, getattr(article, 'title', ''))
            article.body_emoji = self._extract_body_emoji(result.translated_content, result.translated_title)
            article.hashtags = self._extract_hashtags(getattr(article, 'title', ''), result.translated_content)
            return result
        
        logger.error("ALL AI PROVIDERS FAILED for translation - returning original")
        return TranslationResult(
            translated_title=getattr(article, 'title', '') or "",
            translated_content=getattr(article, 'content', '') or "",
            detected_language="en",
            confidence=0.0,
            preserved_terms={},
            provider_used="none",
            model_used="none",
        )

    def _extract_title_emoji(self, title_ar: str, title_en: str) -> str:
        """Extract appropriate emoji for title based on Arabic content"""
        text = f"{title_ar} {title_en}".lower()
        if any(w in text for w in ["hack", "exploit", "سرقة", "اختراق", "ثغرة"]): return "🚨"
        if any(w in text for w in ["etf", "blackrock", "مؤسس", "صندوق", "استثمار"]): return "🏛️"
        if any(w in text for w in ["ban", "تنظيم", "قانون", "sec", "هيئة", "عقوبات"]): return "⚖️"
        if any(w in text for w in ["surge", "rally", "قفز", "ارتفاع", "صعود", "قياسي"]): return "📈"
        if any(w in text for w in ["crash", "انهيار", "هبوط", "تراجع", "خسائر"]): return "📉"
        if any(w in text for w in ["partnership", "شراكة", "تعاون", "integrates"]): return "🤝"
        if any(w in text for w in ["upgrade", "fork", "ترقية", "تحديث", "v2", "v3"]): return "⚡"
        if any(w in text for w in ["funding", "raises", "تمويل", "مليون", "مليار"]): return "💰"
        if any(w in text for w in ["bitcoin", "btc", "بيتكوين", "بتكوين"]): return "🪙"
        if any(w in text for w in ["ai", "ذكاء", "nvidia", "grok", "openai"]): return "🤖"
        return "💡"

    def _extract_body_emoji(self, body_ar: str, title_ar: str) -> str:
        """Extract appropriate emoji for body based on Arabic content"""
        text = f"{body_ar} {title_ar}"
        if any(w in text for w in ["قفز", "ارتفاع", "صعود", "قياسي", "سجل", "أعلى"]): return "📈"
        if any(w in text for w in ["خسائر", "انهيار", "تراجع", "هبوط", "سلبية", "انخفاض"]): return "📉"
        if any(w in text for w in ["اختراق", "سرقة", "ثغرة", "تهديد", "قرصنة", "خرق"]): return "🚨"
        if any(w in text for w in ["عاجل", "طارئ", "مستجد", "فوري"]): return "🔥"
        if any(w in text for w in ["مليار", "مليون", "تمويل", "تريليون", "استثمار", "صندوق"]): return "💰"
        if any(w in text for w in ["طفرة", "انفجار", "نمو", "انطلاق"]): return "🚀"
        if any(w in text for w in ["مؤسسي", "etf", "بنك", "مصرف", "صندوق"]): return "🏛️"
        if any(w in text for w in ["تنظيم", "قانون", "تشريع", "الرقاب", "عقوبات"]): return "⚖️"
        if any(w in text for w in ["xrp", "ريبل", "تحويل", "دفع", "swift"]): return "💱"
        if any(w in text for w in ["سعر", "سهم", "تصفية", "تداول", "محفظة"]): return "💹"
        if any(w in text for w in ["تضخم", "فائدة", "فيدرالي", "مركزي", "اقتصاد", "سندات"]): return "🏦"
        if any(w in text for w in ["ذكاء", "nvidia", "رقاقة", "شريحة"]): return "🤖"
        return "💡"

    def _extract_hashtags(self, title: str, content: str) -> List[str]:
        """Extract relevant hashtags from title and content"""
        text = f"{title} {content}".lower()
        tags = set()
        coin_map = {
            "bitcoin": "#BTC", "btc": "#BTC", "ethereum": "#ETH", "eth": "#ETH",
            "solana": "#SOL", "sol": "#SOL", "xrp": "#XRP", "ripple": "#XRP",
            "cardano": "#ADA", "ada": "#ADA", "dogecoin": "#DOGE", "doge": "#DOGE",
            "avalanche": "#AVAX", "avax": "#AVAX", "polkadot": "#DOT", "dot": "#DOT",
            "chainlink": "#LINK", "link": "#LINK", "uniswap": "#UNI", "uni": "#UNI",
            "aave": "#AAVE", "compound": "#COMP", "maker": "#MKR", "lido": "#LDO"
        }
        for kw, tag in coin_map.items():
            if kw in text:
                tags.add(tag)
        action_tags = {"etf": "#ETF", "hack": "#Hack", "ban": "#Ban", "regulation": "#Regulation"}
        for kw, tag in action_tags.items():
            if kw in text.replace("_", " "):
                tags.add(tag)
        return list(tags)[:5]  # Max 5 hashtags

    async def translate_batch(self, articles: List[Article]) -> List[Article]:
        """Translate multiple articles concurrently"""
        semaphore = asyncio.Semaphore(2)  # Lower concurrency to avoid rate limits

        async def translate_one(article: Article) -> Article:
            async with semaphore:
                result = await self.translate_article(article)
                article.translated_title = result.translated_title
                article.translated_content = result.translated_content
                article.original_language = getattr(article, 'language', 'en')
                article.language = "ar"
                article.metadata["translation"] = {
                    "detected_language": result.detected_language,
                    "confidence": result.confidence,
                    "preserved_terms": result.preserved_terms,
                    "provider_used": result.provider_used,
                    "model_used": result.model_used,
                    "translated_at": datetime.utcnow().isoformat(),
                }
                return article

        tasks = [translate_one(article) for article in articles]
        return await asyncio.gather(*tasks)


async def translate_articles(articles: List[Article]) -> List[Article]:
    """Main entry point for translation"""
    translator = AITranslator()
    return await translator.translate_batch(articles)
