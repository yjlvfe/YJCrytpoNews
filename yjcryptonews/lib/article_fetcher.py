"""
YJCryptoNews - Full Article Fetcher
يجلب نص المقال الكامل من الرابط (بدل الاكتفاء بملخص RSS القصير).
يستخدم trafilatura لاستخراج النص الأساسي للمقال بدقة عالية.
"""
import logging
import asyncio
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# طول أدنى للمحتوى يُعتبر "كاملاً" — لو RSS أعطى أقل، نجلب من الرابط
MIN_FULL_CONTENT = 800
# حد أقصى للنص المُستخرج (نمرّره للملخّص) — نتجنب مقالات ضخمة جداً
MAX_EXTRACT_CHARS = 6000
# مهلة جلب الصفحة
FETCH_TIMEOUT = 15

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; YJCryptoNews/1.0; +https://github.com/yjlvfe)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _extract_with_trafilatura(html: str, url: str) -> Optional[str]:
    """استخراج النص الأساسي للمقال من HTML."""
    try:
        import trafilatura
        text = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
            favor_precision=True,
        )
        if text:
            text = " ".join(text.split())  # تطبيع المسافات
            return text[:MAX_EXTRACT_CHARS]
    except Exception as ex:
        logger.debug(f"trafilatura extract failed for {url}: {ex}")
    return None


async def fetch_full_article(url: str, client: Optional[httpx.AsyncClient] = None) -> Optional[str]:
    """
    يجلب نص المقال الكامل من الرابط.
    يرجّع النص النظيف أو None لو فشل.
    """
    if not url or not url.startswith(("http://", "https://")):
        return None

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(
            timeout=FETCH_TIMEOUT,
            follow_redirects=True,
            headers=_HEADERS,
        )
    try:
        resp = await client.get(url)
        if resp.status_code != 200:
            logger.debug(f"Full-article fetch HTTP {resp.status_code} for {url}")
            return None
        html = resp.text
        if not html:
            return None
        # الاستخراج عملية CPU — ننقلها لخيط منفصل حتى لا نحجب event loop
        text = await asyncio.to_thread(_extract_with_trafilatura, html, url)
        if text and len(text) >= 200:
            logger.info(f"📄 Full article fetched: {len(text)} chars from {url[:60]}")
            return text
        logger.debug(f"Full-article extract too short/empty for {url}")
        return None
    except Exception as ex:
        logger.debug(f"Full-article fetch error for {url}: {ex}")
        return None
    finally:
        if own_client:
            await client.aclose()


async def enrich_article_content(article, client: Optional[httpx.AsyncClient] = None) -> None:
    """
    يحدّث article.content بالنص الكامل لو كان محتوى RSS قصيراً.
    تعديل في المكان (in-place). آمن — لا يرمي استثناءات.
    """
    try:
        current = getattr(article, "content", "") or ""
        url = getattr(article, "url", "") or ""
        # لو المحتوى الحالي كافٍ، لا نتعب الشبكة
        if len(current) >= MIN_FULL_CONTENT:
            return
        full = await fetch_full_article(url, client)
        if full and len(full) > len(current):
            article.content = full
    except Exception as ex:
        logger.debug(f"enrich_article_content failed: {ex}")
