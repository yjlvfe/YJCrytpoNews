from .log import get_logger
from . import database
import re

logger = get_logger("quality_check")

def check_post_quality(item, translated):
    """فحص جودة نشر الخبر قبل النشر (تداخل الجودة والأمور التقنية)"""
    title_ar = translated.get("title_ar", "")
    body_ar = translated.get("body_ar", "")

    # 🛡️ فحص الجودة الأساسي: الحقول غير الفارغة
    if not title_ar or not body_ar:
        logger.warning("❌ جودة النشر الفاشلة: title_ar=%s، body_ar=%s",
                      title_ar[:50] if title_ar else "(فارغ)",
                      body_ar[:50] if body_ar else "(فارغ)")
        return False

    # 2. فحص الحجم الأساسي
    if len(title_ar) < 12:
        logger.warning("❌ جودة النشر الفاشلة: طول العنوان القصير جدًا (%d)", len(title_ar))
        return False
    if len(body_ar) < 50:
        logger.warning("❌ جودة النشر الفاشلة: طول الملخص القصير جدًا (%d)", len(body_ar))
        return False

    # 3. إزالة الكلمات المحظورة الأساسية (التكرار)
    banned_words = ["الجدير بالذكر", "جدير بالذكر", "حيث ", " حيث"]
    for bw in banned_words:
        if bw in title_ar or bw in body_ar:
            logger.warning("❌ جودة النشر الفاشلة: تم العثور على كلمات محظورة '%s'", bw)
            return False

    # 4. فحص التكرار: هل المخطط الأساسي موجود في قاعدة البيانات بالفعل؟ (أي سجل من نفس القناة لنفس العنوان)
    channels = database.get_channels(active_only=True)
    for ch in channels:
        last_post = database.get_last_publish_for_channel_id(ch["id"], hours=1)
        if last_post and item.get("title", "") == last_post.get("title", ""):
            logger.warning("❌ جودة النشر الفاشلة: خبر مكرر في القناة %s خلال الساعة الماضية", ch.get("title", ch["chat_id"]))
            return False

    # 5. فحص عنوان عربي: يمنع إرسال عنوان إنجليزي
    latin_ratio = sum(1 for c in title_ar if ord(c) < 0x0600 and c.isalpha())
    if latin_ratio > len(title_ar) * 0.3:
        logger.warning("❌ جودة النشر الفاشلة: عنوان عربي يحتوي على %d%% أحرف لاتينية", int(latin_ratio / max(1, len(title_ar)) * 100))
        return False

    # 6. فحص أسماء المؤلفين - ممنوع تماماً
    author_patterns = ["Written by", "Author", "By ", "بواسطة", "previous", "more"]
    for ap in author_patterns:
        if ap.lower() in title_ar.lower() or ap.lower() in body_ar.lower():
            logger.warning("❌ جودة النشر الفاشلة: تم العثور على نمط مؤلف '%s'", ap)
            return False

    # 5. تفاصيل الخطأ المحتمل (اللغة، علامة البيتكوين، الكلمات الأجنبية)
    if "\u20bf" in title_ar or "\u20bf" in body_ar:
        logger.warning("❌ جودة النشر الفاشلة: علامة البيتكوين موجودة")
        return False
    if re.search(r'[\u3400-\u4DBF\u4E00-\u9FFF\u3040-\u309F\u30A0-\u30FF\uAC00-\uD7AF\uF900-\uFAFF\uFF00-\uFFEF]', title_ar) or re.search(r'[\u3400-\u4DBF\u4E00-\u9FFF\u3040-\u309F\u30A0-\u30FF\uAC00-\uD7AF\uF900-\uFAFF\uFF00-\uFFEF]', body_ar):
        logger.warning("❌ جودة النشر الفاشلة: نص CJK موجود")
        return False
    if re.search(r'[\u0400-\u04FF]+', title_ar) or re.search(r'[\u0400-\u04FF]+', body_ar):
        logger.warning("❌ جودة النشر الفاشلة: نص أجنبي (سيريلي/يوناني) موجود")
        return False
    if re.search(r'acceso\b', body_ar, re.IGNORECASE) or re.search(r'parte\b', body_ar, re.IGNORECASE):
        logger.warning("❌ جودة النشر الفاشلة: كلمة إسبانية موجودة")
        return False

    # 6. الفحص الصحيح: لا تبدأ كلمة الانجليزية الأولى (ASCII، >1) والتي ليست مدرجة
    first_word = title_ar.split()[0] if title_ar.split() else ""
    if first_word and re.match(r'^[A-Za-z]{2,}$', first_word):
        # Allow common crypto terms that are ok in Arabic titles
        _base = {"btc", "eth", "usdt", "usdc", "sol", "xrp", "ada", "doge", "avax", "dot", "link", "uni", "aave", "comp", "mkr", "ldo", "bnb", "usd", "eur", "jpy", "cny", "etf", "defi", "dao", "nft", "web3", "ai", "sec", "fed", "cpi", "ppi", "gdp", "omn", "oman", "omani", "btc", "eth", "xrp"}
        allowed_english = _base | {"bitcoin", "ethereum", "solana", "ripple", "cardano", "dogecoin", "avalanche", "polkadot", "chainlink", "uniswap", "litecoin", "toncoin", "cosmos", "su"}
        if first_word.lower() not in allowed_english:
            logger.warning("❌ جودة النشر الفاشلة: كلمة انجليزية قصيرة '%s' تبدأ بالعنوان", first_word)
            return False

    # 7. ضمان أن يحتوي الملخص على نشاط الفعل (يحتوي على فعل).
    if not re.search(r'[أ-ي]', body_ar):
        logger.warning("❌ جودة النشر الفاشلة: الملخص لا يحتوي على أي أحرف عربية")
        return False

    # 8. إذا كان title_ar مساوياً للإنجليزي الأصلي (فشل الترجمة) - ارفض
    if title_ar == item.get("title", ""):
        logger.warning("❌ جودة النشر الفاشلة: الترجمة فشلت (العنوان بالإنجليزي)")
        return False

    # ✅ نجح كل الفحوصات
    return True
