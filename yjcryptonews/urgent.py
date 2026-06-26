"""🚨 كشف الأخبار العاجلة — كشف بـ 5+ مصادر، تحقق بالذكاء الاصطناعي، ترجمة ونشر"""
import re
import difflib
import time
import random
import json
import sqlite3
from collections import defaultdict
from datetime import datetime
from . import config, database, fetcher, publisher
from . import ai as ai_client
from .log import get_logger

logger = get_logger("urgent")

# كم مصدر لازم يكرر الخبر عشان يعتبر مرشح عاجل
URGENT_THRESHOLD = 5

# نسبة التشابه بين العناوين عشان نعتبرهم نفس الخبر
SIMILARITY_THRESHOLD = 0.65  # 65%

# كلمات ممنوعة — تجاهل الأخبار التافهة
BANNED_KEYWORDS = [
    "price prediction", "price analysis", "technical analysis",
    "weekly roundup", "daily digest", "market update",
    "top 10", "top 5", "best crypto", "how to",
    "gambling", "lottery", "giveaway",
    "horoscope", "zodiac",
]

# كلمات تدل على خبر عاجل حقيقي — تعطي وزن إضافي
URGENT_KEYWORDS = [
    "breaking", "urgent", "just in", "flash", "developing",
    "confirmed", "official", "announcement", "declare",
    "crisis", "emergency", "hack", "breach", "crash",
    "surge", "plunge", "shock", "dramatic", "major",
    "approves", "approve", "approval", "reject", "rejection",
    "lawsuit", "indict", "arrest", "sanction", "war",
    "ceasefire", "attack", "strike", "explosion",
]


def _normalize_title(title: str) -> str:
    """تطبيع العنوان للمقارنة"""
    t = title.lower()
    t = re.sub(r'[^\w\s]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def _extract_keywords(title: str) -> set:
    """استخراج الكلمات المفتاحية من العنوان — الأسماء الخاصة، الأرقام، الكلمات المهمة"""
    # الكلمات المهمة التي تدل على موضوع الخبر
    important_words = {
        'iran', 'us', 'peace', 'deal', 'war', 'ceasefire', 'attack', 'strike',
        'hack', 'breach', 'crash', 'surge', 'crisis', 'emergency',
        'bitcoin', 'ethereum', 'crypto', 'btc', 'eth', 'sec', 'fed',
        'nft', 'defi', 'bank', 'market', 'stock', 'oil', 'gold',
        'trump', 'biden', 'putin', 'china', 'russia', 'ukraine',
        'nvidia', 'apple', 'meta', 'google', 'microsoft', 'openai',
        'ceo', 'president', 'chairman', 'congress', 'senate',
        'billion', 'million', 'trillion', 'ipo', 'merger', 'lawsuit',
        'approves', 'approve', 'approval', 'reject', 'ban', 'banned',
        'launch', 'unveil', 'introduce', 'release', 'partnership',
        'record', 'high', 'low', 'rally', 'plunge', 'tumble',
        'sanction', 'nuclear', 'missile', 'drone', 'military',
        'arrest', 'indict', 'guilty', 'fraud', 'scam', 'theft',
    }
    
    words = title.lower().split()
    keywords = set()
    
    for w in words:
        w_clean = w.strip(".,!?;:'\"()[]{}$#@&*+-=/\\")
        if not w_clean or len(w_clean) < 3:
            continue
        # الكلمات المهمة
        if w_clean in important_words:
            keywords.add(w_clean)
        # الأسماء الكبيرة (Capitalized في النص الأصلي)
        # الأرقام
        if w_clean.isdigit() or (w_clean[:-1].isdigit() and len(w_clean) > 1):
            keywords.add(w_clean)
        # كلمات طويلة (>6 أحرف) — غالباً كلمات مهمة
        if len(w_clean) > 6:
            keywords.add(w_clean)
    
    return keywords


def _similarity(a: str, b: str) -> float:
    """نسبة التشابه بين عنوانين — تعتمد على تقاطع الكلمات المفتاحية"""
    kw_a = _extract_keywords(a)
    kw_b = _extract_keywords(b)
    
    if not kw_a or not kw_b:
        # Fallback: SequenceMatcher
        return difflib.SequenceMatcher(None, a, b).ratio()
    
    intersection = kw_a & kw_b
    union = kw_a | kw_b
    
    # معيار جديد: إذا في 2+ كلمات مفتاحية مشتركة → خبر واحد
    if len(intersection) >= 2:
        return 1.0  # نفس الخبر
    
    jaccard = len(intersection) / len(union) if union else 0
    
    # إذا في كلمة مفتاحية وحدة مشتركة → احتمال كبير
    if len(intersection) >= 1 and jaccard > 0.15:
        return 0.7
    
    return max(jaccard, difflib.SequenceMatcher(None, a, b).ratio())


def _is_banned(title: str) -> bool:
    """هل الخبر ممنوع؟"""
    t = title.lower()
    for kw in BANNED_KEYWORDS:
        if kw in t:
            return True
    return False


def _urgency_boost(title: str) -> int:
    """وزن إضافي للعناوين العاجلة"""
    t = title.lower()
    boost = 0
    for kw in URGENT_KEYWORDS:
        if kw in t:
            boost += 1
    return boost


def detect_urgent(items: list) -> list:
    """كشف الأخبار المتكررة في 5+ مصادر — بدون ذكاء اصطناعي"""
    if not items:
        return []
    
    # 1. تجاهل الممنوع أولاً
    items = [it for it in items if not _is_banned(it.get("title", ""))]
    if not items:
        return []
    
    # 2. تطبيع العناوين
    normalized = []
    for it in items:
        norm = _normalize_title(it.get("title", ""))
        if norm:
            normalized.append((norm, it))
    
    # 3. تجميع المتشابهين
    groups = []  # [(best_title, [items]), ...]
    used = set()
    
    for i, (norm_i, item_i) in enumerate(normalized):
        if i in used:
            continue
        
        group = [item_i]
        used.add(i)
        
        for j, (norm_j, item_j) in enumerate(normalized):
            if j in used:
                continue
            if _similarity(norm_i, norm_j) >= SIMILARITY_THRESHOLD:
                group.append(item_j)
                used.add(j)
        
        if len(group) >= 2:  # على الأقل 2 عشان نعتبره مجموعة
            # اختيار أفضل عنوان (الأطول غالباً الأكثر وصفاً)
            best_item = max(group, key=lambda x: len(x.get("title", "")))
            groups.append((best_item, group))
    
    # 4. فلترة: فقط المجموعات اللي فيها ≥5 مصادر
    urgent = []
    for best_item, group in groups:
        count = len(group)
        if count >= URGENT_THRESHOLD:
            boost = _urgency_boost(best_item.get("title", ""))
            urgent.append({
                "item": best_item,
                "sources": group,
                "source_count": count,
                "urgency_score": count + boost,
            })
    
    # 5. ترتيب حسب درجة العاجلية
    urgent.sort(key=lambda x: x["urgency_score"], reverse=True)
    
    return urgent


def _get_unique_sources(group: list) -> list:
    """استخراج أسماء المصادر الفريدة"""
    seen = set()
    sources = []
    for item in group:
        src = item.get("source", "Unknown")
        if src not in seen:
            seen.add(src)
            sources.append(src)
    return sources


def _ai_verify_and_translate(story: dict) -> dict | None:
    """🧠 الذكاء الاصطناعي يتحقق من الخبر العاجل ويترجمه
    Returns: dict with title_ar, body_ar, emoji, sources, url, is_urgent
    or None if AI confirms it's NOT urgent
    """
    item = story["item"]
    sources = _get_unique_sources(story["sources"])
    count = story["source_count"]
    
    title = item.get("title", "")
    url = item.get("url", "")
    summary = (item.get("summary", "") or "")[:300]
    src_names = ", ".join(sources[:8])
    
    prompt = f"""أنت محلل أخبار عاجلة. أمامك خبر ظهر في {count} مصادر مختلفة.

📰 العنوان: {title}
📄 الملخص: {summary}

🚨 **مهمتك:**
1. هل هذا خبر **عاجل حقاً**؟ (حادث كبير، قرار مفاجئ، أزمة، اختراق أمني، تطور جيوسياسي خطير)
2. إذا كان عاجلاً: اكتب عنوان عربي + ملخص عربي مختصر
3. إذا **ليس** عاجلاً (إعلان عادي، تحديث سوق روتيني، تكهنات): أخرج is_urgent=false

⚠️ **معايير الخبر العاجل الحقيقي:**
- ✅ حادث له تأثير فوري على الأسواق أو الأمن أو المجتمع
- ✅ إعلان مفاجئ من حكومة أو مؤسسة كبرى
- ✅ اختراق أمني أو سرقة أو هجوم إلكتروني كبير
- ✅ كارثة أو أزمة أو حادث جيوسياسي
- ❌ **ليس** عاجلاً: تحليل سوق عادي، توقعات، أخبار تطوير منتج، تحديثات روتينية

**أخرج JSON فقط بهذا التنسيق:**
{{
  "is_urgent": true/false,
  "title_ar": "العنوان العربي",
  "body_ar": "الملخص العربي في جملة إلى ثلاث جمل",
  "emoji": "🚨"
}}

إذا ليس عاجلاً: {{"is_urgent": false}}"""

    messages = [
        {"role": "system", "content": "أنت محلل أخبار عاجلة خبير. أخرج JSON فقط."},
        {"role": "user", "content": prompt},
    ]
    
    result = ai_client.call_with_multi_fallback(messages, max_tokens=512, temperature=0.1)
    
    if not result:
        logger.warning("🧠 AI لم يجب — نشر الخبر كحل احتياطي (إنجليزي)")
        return {
            "is_urgent": True,
            "title_ar": None,
            "body_ar": None,
            "emoji": "🚨",
            "url": url,
            "sources": sources,
            "source_count": count,
        }
    
    # استخراج JSON من رد AI
    data = ai_client.extract_json(result)
    if not data:
        logger.warning("🧠 AI رد بدون JSON صالح — نشر احتياطي")
        return {
            "is_urgent": True,
            "title_ar": None,
            "body_ar": None,
            "emoji": "🚨",
            "url": url,
            "sources": sources,
            "source_count": count,
        }
    
    if not data.get("is_urgent", False):
        logger.info("🧠 AI: الخبر ليس عاجلاً — تخطي")
        return None
    
    return {
        "is_urgent": True,
        "title_ar": data.get("title_ar", ""),
        "body_ar": data.get("body_ar", ""),
        "emoji": data.get("emoji", "🚨"),
        "url": url,
        "sources": sources,
        "source_count": count,
    }


def build_post(ai_result: dict) -> str:
    """🚨 بناء منشور عاجل نظيف: عنوان + ملخص + هاشتاقات فقط"""
    title_ar = ai_result.get("title_ar", "")
    body_ar = ai_result.get("body_ar", "")
    emoji = ai_result.get("emoji", "🚨")
    
    if title_ar:
        post = f"{emoji} {title_ar}"
        if body_ar:
            post += f"\n\n{body_ar}"
    else:
        # Fallback: إنجليزي (نادر)
        post = f"{emoji} **URGENT | Breaking News**"
    
    post += "\n\n#عاجل"
    
    return post


def run_urgent_check() -> dict:
    """🚨 دورة عاجلة: جلب RSS ← كشف متكرر ← AI يتحقق ويترجم ← نشر فوري"""
    cycle_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.info("=" * 50)
    logger.info("🚨 دورة عاجلة #%s", cycle_id)
    logger.info("=" * 50)
    
    # 1. جلب الأخبار (كل المصادر النشطة)
    seen_urls = database.get_seen_urls(days=1)
    logger.info("📡 جلب الأخبار من كل المصادر...")
    items = fetcher.fetch_all(seen_urls=seen_urls)
    logger.info("✅ %d خبر جديد", len(items))
    
    if not items:
        logger.info("ℹ️ لا توجد أخبار جديدة")
        return {"cycle": cycle_id, "candidates": 0, "published": 0}
    
    # 2. كشف المرشحين (بدون AI)
    logger.info("🔍 كشف الأخبار المتكررة (≥%d مصادر)...", URGENT_THRESHOLD)
    candidates = detect_urgent(items)
    
    if not candidates:
        logger.info("ℹ️ لا توجد أخبار في %d+ مصادر", URGENT_THRESHOLD)
        return {"cycle": cycle_id, "candidates": 0, "published": 0}
    
    logger.info("🚀 %d مرشح عاجل — نرسل للذكاء الاصطناعي للتحقق", len(candidates))
    
    # 3. لكل مرشح: AI يتحقق + يترجم + ينشر
    published = 0
    ai_verified = 0
    
    for i, story in enumerate(candidates):
        count = story["source_count"]
        title = story["item"].get("title", "")[:80]
        logger.info("📰 [%d/%d] في %d مصادر — %s", i + 1, len(candidates), count, title)
        
        # 🧠 AI يتحقق
        logger.info("🧠 جاري التحقق بالذكاء الاصطناعي...")
        ai_result = _ai_verify_and_translate(story)
        
        if ai_result is None:
            logger.info("⏭️ AI: الخبر ليس عاجلاً — تخطي")
            continue
        
        ai_verified += 1
        logger.info("✅ AI: خبر عاجل — جاري النشر")
        
        # بناء المنشور (عربي مع ترجمة AI)
        post = build_post(ai_result)
        
        # نشر لكل القنوات
        channels = database.get_channels(active_only=True)
        for ch in channels:
            ok = publisher._send(ch["chat_id"], post)
            if ok:
                published += 1
                logger.info("✅ %s: تم نشر الخبر العاجل", ch.get("title", ch["chat_id"]))
            else:
                logger.error("❌ %s: فشل النشر العاجل", ch.get("title", ch["chat_id"]))

            try:
                database.log_publish(
                    cycle_id=cycle_id,
                    channel_id=ch["id"],
                    title=ai_result.get("title_ar", title),
                    news_url=story["item"].get("url", ""),
                    status="success" if ok else "failed",
                )
            except sqlite3.Error as e:
                logger.error("❌ فشل تسجيل log_publish في urgent: %s", e)

        # منع التكرار
        try:
            database.mark_seen(story["item"].get("url", ""), story["item"]["title"])
        except sqlite3.Error as e:
            logger.error("❌ فشل تسجيل mark_seen للقصة الرئيسية: %s", e)
        for src_item in story["sources"]:
            try:
                database.mark_seen(src_item.get("url", ""), src_item["title"])
            except sqlite3.Error as e:
                logger.error("❌ فشل تسجيل mark_seen لمصدر: %s", e)
        
        # تأخير بين المنشورات
        if i < len(candidates) - 1:
            delay = random.uniform(3, 6)
            time.sleep(delay)
    
    logger.info("=" * 50)
    logger.info("✅ دورة عاجلة: %d مرشح → %d تحقق AI → %d منشورات", 
                len(candidates), ai_verified, published)
    logger.info("=" * 50)
    
    return {
        "cycle": cycle_id,
        "candidates": len(candidates),
        "ai_verified": ai_verified,
        "published": published,
    }
