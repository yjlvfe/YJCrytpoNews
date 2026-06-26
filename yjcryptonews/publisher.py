"""النشر على تيليجرام — تنسيق احترافي فاخر"""
import re
import time
import json
import random
import requests
from . import config, database
from .log import get_logger

logger = get_logger("publisher")

TELEGRAM_API = "https://api.telegram.org/bot"

# ===== إيموجي بداية المنشور =====
# جميع الأنماط تستخدم re.IGNORECASE للتعامل مع الأحرف الكبيرة (BTC, CLARITY, Law...)
# والأنماط تستخدم \b فقط للحروف اللاتينية (تعمل مع الإنجليزي فقط).
# يتم البحث في النص الأصلي + النص العربي المترجم معاً لتحسين التغطية.

EMOJI_MAP = [
    # أمن / اختراق
    (r"\b(?:hack(?:ers?|ing|ed)?|exploit|breach|scam|phish(?:ing)?|theft|stolen|attack|malware|ransomware|vulnerability|cyber|data breach)\b", "🚨"),
    # مؤسسات / استثمار مؤسسي / ETF / بنوك
    (r"\b(?:etf|blackrock|fidelity|grayscale|institution(?:al)?|blackstone|morgan\s+stanley|strategy|microstrategy|saylor|coinbase|binance|goldman|jpmorgan|bank of america|citigroup)\b", "🏛️"),
    # NFT / فن رقمي / ميتافيرس
    (r"\b(?:nft|digital.*art|collectible|metaverse?|vr|virtual)\b", "🎨"),
    # DeFi / إقراض / ستيكينغ
    (r"\b(?:defi|lending|stak(?:e|ing)|yield|farm(?:ing)?|liquid|aave|uniswap|sui)\b", "🏗️"),
    # تنظيم / قانون / SEC / سياسة
    (r"\b(?:regulat(?:ion|ory|e)?|sec|ban|law|legal|legislation|compliance|senator|cfpb|bill|congress|sue(?:s|d)?|clarity|pardon|regulator|federal|antitrust|deregulation)\b", "⚖️"),
    # أسواق / مؤشرات / أسهم
    (r"\b(?:stock|stock market|share|equity|nasdaq|s&p|dow|dji|nyse|rally|index|bull market|bear market|ipo|merger|acquisition|quarterly report|earnings)\b", "📊"),
    # حرب / نزاع / جيوسياسي
    (r"\b(?:war|military|missile|strike|conflict|sanctions?|ceasefire|tension|escalat(?:ion|e)?|iran|gulf|hormuz|drones?|geopolitical)\b", "⚔️"),
    # نفط / طاقة / سلع
    (r"\b(?:oil|crude|energy|gas|petrol|pipeline|commodity|gold|silver|copper)\b", "🛢️"),
    # بنك مركزي / فائدة / تضخم / اقتصاد كلي
    (r"\b(?:fed|federal reserve|interest\s+rate|inflation|cpi|ppi|rate\s+hike|rate\s+cut|central\s+bank|bank\s+of\s+england|ecb|monetary\s+policy|gdp|recession|economic\s+growth|treasury|bond|yield)\b", "🏦"),
    # AI / ذكاء اصطناعي / تكنولوجيا
    (r"\b(?:ai|artificial\s+intelligence|machine\s+learning|deep\s+learning|openai|chatgpt|grok|nvidia|amd|intel|chip|semiconductor|data center|cloud|quantum|robotics|automation)\b", "🤖"),
    # تعدين / هاشريت
    (r"\b(?:min(?:e|ing)|hashrate|hash\s+rate|pool|block|consensus)\b", "⛏️"),
    # XRP / Ripple / مدفوعات / تحويلات
    (r"\b(?:xrp|ripple|swift|payment|remittance|cross\b.?border|fintech|paypal|stripe)\b", "💱"),
    # توقعات / تحليلات
    (r"\b(?:predict(?:ion)?|forecast|outlook|analysis|analyst|price\s+target|pattern)\b", "🔮"),
    # بيتكوين / كريبتو
    (r"\b(?:bitcoin|btc|crypto|blockchain)\b", "🪙"),
    # سوق / تداول / سعر / عملة
    (r"\b(?:price|market|trade|trading|volume|liquidat(?:ion|e)|currency|dollar|forex|usd)\b|(?:^|\s)[$¥€£]\d", "💹"),
    # شركات تكنولوجيا كبرى
    (r"\b(?:apple|microsoft|google|alphabet|meta|amazon|big tech|tech|software|hardware|startup|venture\s+capital|vc\s+funding|unicorn)\b", "💻"),
    # توظيف / اقتصاد
    (r"\b(?:jobs?|employment|unemployment|payroll|workforce|labor|wage|salary)\b", "👔"),
]

# إيموجي بداية المتن — حسب اتجاه الخبر
# ملاحظة: الكلمات العربية فقط في ARABIC_STEMS أدناه، لأن \b لا يعمل مع العربية
BODY_EMOJI_MAP = [
    # إيجابي/صعود (إنجليزي فقط — العربي في ARABIC_STEMS)
    (r"\bsurge(s|d)?\b|\brally\b|\brise(s|d)?\b|\bhigh\b|\brecord\b|\bgain(s|ed)?\b|\bjump(s|ed)?\b|\bup\b|\bbullish\b|\bpositive\b|\bgreen\b|\bgrowth\b|\bboost\b|\bmoon\b|\b新高|\bclimb(s|ed)?\b|\bsoar(s|ed)?\b|\bspike\b", "📈"),
    # سلبي/هبوط (إنجليزي فقط — العربي في ARABIC_STEMS)
    (r"\bdrop(s|ped)?\b|\bcrash\b|\bfall(s|ing|en)?\b|\blow\b|\bslip(s|ped)?\b|\bdecline\b|\bdown\b|\bbearish\b|\bred\b|\bnegative\b|\btumble\b|\bplunge\b|\bshed\b|\bslump\b|\bdip\b|\bcorrection\b|\brecession\b", "📉"),
    # اختراق/أمان (إنجليزي فقط — العربي في ARABIC_STEMS)
    (r"\bhack\b|\bexploit\b|\bbreach\b|\bscam\b|\btheft\b|\bstolen\b|\battack\b|\bleak\b|\bcompromised\b", "🚨"),
    # حار/عاجل (إنجليزي فقط — العربي في ARABIC_STEMS)
    (r"\bbreaking\b|\burgent\b|\bjust in\b|\bflash\b", "🔥"),
    # تطور سريع (إنجليزي فقط — العربي في ARABIC_STEMS)
    (r"\brapid\b|\bspeed\b|\bquick\b", "⚡"),
    # أموال/تمويل (إنجليزي فقط — العربي في ARABIC_STEMS)
    (r"\b[bB]illion\b|\bmillion\b|\bfunding\b|\braise\b", "💰"),
    # نمو/طفرة (إنجليزي فقط — العربي في ARABIC_STEMS)
    (r"\bboom\b|\bskyrocket\b|\bmoon\b|\bexplosive\b|\bsurge\b", "🚀"),
]

# إيموجيات عامة متنوعة — ممنوع إيموجي الصحيفة تماماً
GENERAL_EMOJIS = ["💡", "🔍", "🎯", "⚡", "💎", "🔷", "🪙", "🏆", "🌟", "✨", "💫", "🔗", "💼", "📋", "🗂️", "🪪", "📀", "🧩", "🎲", "🏅", "🎪", "🔮", "🧿", "💠", "🌟", "⭐", "🌐", "🌍", "📡", "🧭", "💹", "📦", "🎁", "🧰", "⚙️", "🛡️", "🧬", "🔬", "🪄", "🎭", "🎨", "🎵"]


def _choose_start_emoji(title: str, summary: str = "", title_ar: str = "") -> str:
    """إيموجي بداية المنشور — يبحث في النص الأصلي والنص العربي معاً"""
    text = f"{title} {summary} {title_ar}"
    for pattern, emoji in EMOJI_MAP:
        if re.search(pattern, text, re.IGNORECASE):
            return emoji
    # الفلاش باك العربي — للعناوين العربية التي لم تطابق الأنماط الإنجليزية
    ARABIC_START_STEMS = {
        "🏛️": ["مؤسس", "صندوق", "استثمار", "سايلور", "بلاك روك", "إستراتيجية", "شركة", "strateg", "بنك", "مصرف", "goldman"],
        "⚖️": ["تنظيم", "قانون", "قوانين", "تشريع", "هيئة", "لجنة", "تصويت", "clarity", "ترخيص", "موافقة", "سناتور", "سياسة", "عقوبات"],
        "💱": ["xrp", "ريبل", "تحويل", "دفع", "ripple", "cross.border", "fintech"],
        "🏦": ["تضخم", "فائدة", "فيدرالي", "مركزي", "cpi", "بنك", "مصرف", "اقتصاد", "gdp", "ركود", "سندات"],
        "💰": ["مليار", "مليون", "تمويل", "استثما", "حوت", "محفظة"],
        "📊": ["سوق", "مؤشر", "تداول", "سعر", "سهم", "أسهم", "بورصة", "وول ستريت"],
        "🔮": ["توقع", "تحليل", "توقعات"],
        "🤖": ["ai", "ذكاء", "grok", "nvidia", "رقاقة", "تقنية", "تكنولوجيا"],
        "⛏️": ["تعدين", "pool", "بلوك"],
        "💹": ["تصفية", "شراء", "بيع", "سهم"],
        "🪙": ["بيتكوين", "بتكوين", "bitcoin", "btc", "عملات رقمية", "كريبتو"],
        "🌍": ["الإمارات", "أمريكي", "uae", "دبي", "صين", "صيني", "أوروبا", "عالم"],
        "💻": ["appl", "microsoft", "google", "meta", "amazon", "تقنية", "تكنولوجيا", "برمج", "رقائق", "شريحة"],
        "🛢️": ["نفط", "طاقة", "خام", "ذهب", "سلع"],
        "👔": ["وظائف", "توظيف", "عمالة", "بطالة", "رواتب"],
        "⚔️": ["حرب", "نزاع", "عقوبات", "توتر", "غزو", "غارة"],
    }
    for emoji, stems in ARABIC_START_STEMS.items():
        for stem in stems:
            if stem.lower() in text.lower():
                return emoji
    return random.choice(GENERAL_EMOJIS)


def _choose_body_emoji(title: str, summary: str = "", title_emoji: str = "") -> str:
    """إيموجي بداية المتن حسب اتجاه الخبر — يضمن عدم التكرار مع إيموجي العنوان"""
    text = f"{title} {summary}"
    
    # 1. Arabic stems أولاً — لأن النص العربي هو المنشور الفعلي، والإنجليزي قد يحتوي كلمات مضللة من RSS
    # بدون \b عشان البادئات واللواحق (يقفز، ارتفاعه، الانهيار...)
    ARABIC_STEMS = {
        "📈": ["قفز", "ارتفاع", "صعود", "قياسي", "سجل", "أعلى", "قفزة", "صعد", "يرتفع", "يحقق", "ارتفعت"],
        "📉": ["خسائر", "انهيار", "تراجع", "هبوط", "سلبية", "انخفاض", "يهبط", "تراج", "انخفض", "هبط"],
        "🚨": ["اختراق", "سرقة", "ثغرة", "تهديد", "قرصنة", "خرق"],
        "🔥": ["عاجل", "طارئ", "مستجد", "فوري"],
        "⚡": ["سريع", "فوري", "مفاجئ", "سريعة"],
        "💰": ["مليار", "مليون", "تمويل", "تريليون", "مليارات", "ملايين", "حوت", "استثمار", "صندوق"],
        "🚀": ["طفرة", "انفجار", "نمو", "قفزة", "انطلاق"],
        "🏛️": ["مؤسسي", "صندوق", "استثمار", "ETF", "بنك", "مصرف"],
        "⚖️": ["تنظيم", "قانون", "تشريع", "الرقاب", "هيئة", "عقوبات"],
        "💱": ["xrp", "ريبل", "تحويل", "دفع", "ripple", "SWIFT", "cross.border", "payment", "fintech"],
        "💹": ["سعر", "سهم", "شراء", "بيع", "تصفية", "تداول", "محفظة"],
        "🏦": ["تضخم", "فائدة", "فيدرالي", "مركزي", "اقتصاد", "سندات", "عائد"],
        "🤖": ["ذكاء", "اصطناعي", "رقاقة", "شريحة", "معالج", "nvidia"],
        "💻": ["appl", "microsoft", "google", "تقنية", "برمج", "سحاب"],
        "🛢️": ["نفط", "خام", "برميل", "طاقة", "ذهب"],
    }
    for emoji, stems in ARABIC_STEMS.items():
        if emoji == title_emoji:
            continue
        for stem in stems:
            if stem in text:
                return emoji
    
    # 2. English patterns مع \b و IGNORECASE — بعد العربي مباشرة عشان الإنجليزي ما يغلب على العربي
    for pattern, emoji in BODY_EMOJI_MAP:
        if re.search(pattern, text, re.IGNORECASE) and emoji != title_emoji:
            return emoji
    
    # 3. خيار عشوائي من الإيموجيات العامة
    candidates = [e for e in GENERAL_EMOJIS if e != title_emoji]
    if not candidates:
        candidates = GENERAL_EMOJIS
    return random.choice(candidates)


def _send(chat_id: str, text: str) -> bool:
    """إرسال بتنسيق HTML مع منطق إعادة المحاولة والاسترداد المتقدم"""
    cfg = config.load()
    token = cfg.get("bot", {}).get("token", "")
    if not token:
        print("❌ No bot token configured")
        return False

    url = f"{TELEGRAM_API}{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}

    max_retries = cfg.get("publisher", {}).get("telegram_retries", 3)
    base_delay = cfg.get("publisher", {}).get("telegram_retry_delay", 5)

    for attempt in range(max_retries):
        try:
            # tuple timeout = (connect, read) — fail fast on stalled routes,
            # allow 30s for Telegram's normal response (expanded from 10s)
            resp = requests.post(url, json=payload, timeout=(10, 30))
            if resp.ok:
                return True
            logger.error("Telegram error [%d]: %s (attempt %d/%d)", 
                        resp.status_code, resp.text[:200], attempt + 1, max_retries)
            if resp.status_code == 403:
                logger.warning("Bot is not admin in %s or channel not found", chat_id)
            elif resp.status_code == 400:
                logger.warning("HTML error — retrying as plain text")
                # 🛡️ Build a fresh payload copy to avoid mutating the original —
                # if the 5xx retry path runs after this, parse_mode is still
                # available on the original payload for that retry.
                plain_payload = {**payload}
                plain_payload.pop("parse_mode", None)
                resp2 = requests.post(url, json=plain_payload, timeout=(10, 30))
                if resp2.ok:
                    return True
                logger.error("HTML retry failed [%d]", resp2.status_code)
            elif resp.status_code in (404, 500, 502, 503, 429):
                logger.warning("Transient error [%d] — إعادة المحاولة", resp.status_code)
            elif "timeout" in str(resp):
                logger.warning("طلب Telegram مهلة (attempt %d/%d)", attempt + 1, max_retries)
            else:
                logger.error("خطأ غير متوقع [%d]", resp.status_code)

        except requests.Timeout:
            logger.warning("طلب Telegram مهلة (attempt %d/%d)", attempt + 1, max_retries)
        except requests.ConnectionError:
            logger.warning("خطأ في الاتصال بـ Telegram (attempt %d/%d)", attempt + 1, max_retries)
        except Exception as e:
            logger.error("طلب Telegram failed: %s (attempt %d/%d)", e, attempt + 1, max_retries)

        if attempt < max_retries - 1:
            delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
            logger.info("🔄 إعادة المحاولة بعد %.1f ثانية...", delay)
            time.sleep(delay)

    logger.error("❌ فشل نشر المنشور بعد %d محاولة", max_retries)
    return False


def build_post(item: dict, translated: dict) -> str:
    """منشور عربي فقط: إيموجي + عنوان عربي + إيموجي + ملخص"""
    title_ar = translated.get("title_ar", "")
    body_ar = translated.get("body_ar", "")
    
    # ممنوع النشر بدون عنوان عربي
    if not title_ar:
        return ""
    
    # إزالة رمز البيتكوين المحظور
    banned_bitcoin_symbol = "\u20bf"
    title_ar = title_ar.replace(banned_bitcoin_symbol, "").strip()
    body_ar = body_ar.replace(banned_bitcoin_symbol, "").strip()
    
    # تنظيف العلامات والروابط
    import re as _re
    _artifacts = [
        r'📰\s*العنوان\s*:?\s*', r'📄\s*الملخص\s*:?\s*',
        r'📰\s*', r'📄\s*', r'🔗\s*',
        r'العنوان العربي\s*:?\s*', r'المحتوى العربي\s*:?\s*',
        r'عنوان عربي\s*:?\s*', r'عنوان\s*:?\s*',
        r'ملخص عربي\s*:?\s*', r'ملخص\s*:?\s*',
        r'العربي\s*:?\s*',
        r'رابط\s*:?\s*', r'Read Full Article\s*:?\s*', r'اقرأ المقال\s*:?\s*',
        # تسريبات تعليمات الـ prompt
        r'يرجى مراعاة[^.،\n]*', r'مع مراعاة استخدام[^.،\n]*',
        r'استخدام المصطلحات[^.،\n]*', r'المصطلحات المذكورة[^.،\n]*',
        r'ملاحظة\s*:?\s*', r'تنبيه\s*:?\s*',
        r'وفقاً للمصطلحات[^.،\n]*', r'حسب القاموس[^.،\n]*',
    ]
    for pat in _artifacts:
        title_ar = _re.sub(pat, '', title_ar).strip()
        body_ar = _re.sub(pat, '', body_ar).strip()

    # إزالة رموز Markdown (نجوم/شرطات سفلية) التي تسرّبها بعض النماذج
    for _md in ['**', '__', '*', '`', '#']:
        title_ar = title_ar.replace(_md, '')
        body_ar = body_ar.replace(_md, '')

    # إزالة الإنجليزية الملتصقة بالعربي بدون مسافة (مثل: هيدراScaling أو Testnetالشبكة)
    # تحذف سلسلة الحروف اللاتينية فقط عندما تكون ملاصقة مباشرة لحرف عربي
    def _strip_glued_latin(text: str) -> str:
        # لاتيني ملتصق بعربي: احذف اللاتيني
        text = _re.sub(r'(?<=[\u0600-\u06FF])[A-Za-z]+', '', text)
        text = _re.sub(r'[A-Za-z]+(?=[\u0600-\u06FF])', '', text)
        return text

    title_ar = _strip_glued_latin(title_ar).strip()
    body_ar = _strip_glued_latin(body_ar).strip()

    # تنظيف المسافات الزائدة الناتجة عن حذف الكلمات (مثل "هيدرا ،" أو مسافتين)
    def _fix_spacing(text: str) -> str:
        text = _re.sub(r'\s+([،.!؟:;])', r'\1', text)   # مسافة قبل الترقيم
        text = _re.sub(r'\s{2,}', ' ', text)             # مسافات متعددة
        return text.strip()

    title_ar = _fix_spacing(title_ar)
    body_ar = _fix_spacing(body_ar)
    
    # إزالة الحروف الصينية/الكورية/اليابانية
    _cjk = re.compile(
        r'[\u3400-\u4DBF\u4E00-\u9FFF\u3040-\u309F\u30A0-\u30FF'
        r'\uAC00-\uD7AF\uF900-\uFAFF\uFF00-\uFFEF]'
    )
    title_ar = _cjk.sub('', title_ar).strip()
    body_ar = _cjk.sub('', body_ar).strip()
    
    # إزالة الكلمات الإنجليزية الحقيقية فقط — مع الحفاظ على الأرقام والأسعار ورموز العملات
    # رموز العملات المعروفة المسموح بها (تبقى كما هي لأنها معروفة عالمياً)
    _ALLOWED_TICKERS = {
        "BTC", "ETH", "USDT", "USDC", "SOL", "XRP", "ADA", "DOGE", "AVAX", "DOT",
        "LINK", "UNI", "AAVE", "COMP", "MKR", "LDO", "BNB", "USD", "EUR", "GBP",
        "JPY", "CNY", "ETF", "DEFI", "DAO", "NFT", "AI", "SEC", "FED", "CPI",
        "GDP", "TVL", "APY", "APR", "DEX", "CEX", "POS", "POW", "L1", "L2",
        "SUI", "TON", "TRX", "LTC", "BCH", "ATOM", "NEAR", "OP", "ARB", "PEPE",
        "SHIB", "WLD", "INJ", "RNDR", "FET", "TAO",
    }

    def _keep_word(w: str) -> bool:
        # 1) فيها رقم؟ (سعر/نسبة/مبلغ مثل 0.16 أو 40 أو 5% أو $0.16) → احتفظ بها
        if any(c.isdigit() for c in w):
            return True
        # 2) فيها أي حرف عربي؟ → احتفظ بها
        if any('\u0600' <= c <= '\u06FF' for c in w):
            return True
        # 3) رمز عملة/مصطلح معروف؟ (بعد إزالة الترقيم) → احتفظ به
        stripped = w.strip(".,!?؟;:()[]{}«»\"'$£€¥%").upper()
        if stripped in _ALLOWED_TICKERS:
            return True
        # 4) رمز عملة/علامة فقط بدون أحرف؟ ($ £ € % …) → احتفظ
        if not any(c.isalpha() for c in w):
            return True
        # غير ذلك = كلمة إنجليزية حقيقية → احذف
        return False

    # تنظيف العنوان
    title_ar = ' '.join(w for w in title_ar.split() if _keep_word(w)).strip()

    # تنظيف الملخص بنفس المنطق
    if body_ar:
        body_ar = ' '.join(w for w in body_ar.split() if _keep_word(w)).strip()
    
    # إذا لم يتبق عنوان عربي بعد التنظيف، ارفض
    if not title_ar or sum(1 for c in title_ar if '\u0600' <= c <= '\u06FF') < 3:
        return ""
    
    # إيموجي
    emoji = _choose_start_emoji(item.get("title", ""), item.get("summary", ""), title_ar)
    
    # المنشور النهائي - بدون روابط، بدون إضافات
    post = f"{emoji} {title_ar}"
    
    if body_ar:
        # تنظيف الملخص
        body_ar = body_ar.replace("\n\n", "\n").strip()
        if body_ar:
            emoji_body = _choose_body_emoji(item.get("title", ""), body_ar, title_emoji=emoji)
            post += f"\n\n{emoji_body} {body_ar}"
    
    return post


def publish(item, translated):
    """نشر خبر إلى كل القنوات النشطة مع إعادة محاولة قوية وفحص قبل النشر"""
    cfg = config.load()
    publisher_cfg = cfg.get("publisher", {})
    token = cfg.get("bot", {}).get("token", "")
    if not token:
        print("❌ لا يوجد توكن البوت في config.yaml أو .env")
        return []

    # 🛡️ فحص الجودة قبل النشر (في الذاكرة)
    from yjcryptonews.quality_check import check_post_quality
    if not check_post_quality(item, translated):
        print("❌ فشل فحص الجودة — الخبر مرفوض قبل النشر")
        return []

    headers = {"Content-Type": "application/json; charset=utf-8"}
    base = "https://api.telegram.org/bot" + token
    channels = database.get_channels(active_only=True)
    results = []

    max_attempts = publisher_cfg.get("max_attempts", 3)
    retry_delays = publisher_cfg.get("retry_delays", [5, 10, 20])
    timeout_sec = publisher_cfg.get("timeout_ms", 5000) // 1000

    for ch in channels:
        post = build_post(item, translated)
        if not post:
            logger.warning("تم رفض النشر — لا يوجد عنوان عربي")
            continue
        url = f"{base}/sendMessage"
        payload = {
            "chat_id": ch["chat_id"],
            "text": post,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }

        last_error = None
        for attempt in range(max_attempts):
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=timeout_sec)
                if resp.status_code == 200:
                    results.append({"channel": ch, "status": "success"})
                    database.mark_seen(item.get("url", ""), item["title"])
                    break
                else:
                    last_error = f"HTTP {resp.status_code}: {resp.text}"
                    if resp.status_code in (400, 401, 403):
                        break
            except Exception as e:
                last_error = str(e)

            if attempt < max_attempts - 1:
                time.sleep(retry_delays[attempt])
        else:
            results.append({"channel": ch, "status": "failed", "error": last_error})

    return results
