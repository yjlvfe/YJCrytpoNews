#!/usr/bin/env python3
"""
🤖 YJCryptoNews v3.0 - نظام نشر أخبار الكريبتو الذكي
نسخة مدمجة: تجربة الإنتاج + معمارية الطبقات الجديدة
"""
import sys
import os
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Legacy imports (for backward compatibility)
from yjcryptonews import database, fetcher, publisher, market, daily_queue, urgent
from yjcryptonews import translator as legacy_translator
from yjcryptonews import filter as legacy_filter

# NEW: v3 Layered Architecture imports
from yjcryptonews.lib import (
    DataAcquisitionEngine, run_acquisition_cycle,
    QualityScorer, score_articles, fact_check_articles,
    deduplicate_articles, AIProcessingPipeline, run_ai_pipeline,
    TelegramPublisher, Publisher, run_publish_cycle,
    HourlySingleArticleScheduler, run_hourly_cycle, run_breaking_check,
    AnalyticsEngine,
)
from yjcryptonews import config
from yjcryptonews.log import setup_logging, get_logger, cleanup_old_logs
from yjcryptonews.ai import spread_delay


def run_cycle_v3():
    """
    دورة كاملة باستخدام المعمارية الجديدة:
    Data Acquisition → Quality Engine → AI Processing → Publishing
    """
    logger = get_logger("cycle_v3")
    cfg = config
    cycle_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    logger.info("=" * 50)
    logger.info("🔁 دورة v3 #%s", cycle_id)
    logger.info("=" * 50)

    # 1. Data Acquisition Layer
    logger.info("📡 Layer 1: Data Acquisition...")
    import hashlib

    def _src_id(url: str) -> int:
        # Deterministic across processes (Python's hash() is salted per-process)
        return int(hashlib.md5(url.encode()).hexdigest()[:8], 16) % 1000000

    async def acquire():
        from yjcryptonews.models.source import Source, SourceType, SourceStatus
        # Get active sources from database
        sources = []
        # Use rss_feeds from config
        for s in cfg.get("sources", {}).get("rss_feeds", []):
            if s.get("active", True):
                sources.append(Source(
                    id=_src_id(s["url"]),
                    name=s.get("name", s["url"]),
                    url=s["url"],
                    type=SourceType.RSS.value,
                    trust_score=s.get("trust_score", 85),
                    status=SourceStatus.ACTIVE.value,
                ))
        
        async with DataAcquisitionEngine() as engine:
            articles = await engine.acquire_all(sources)
        return articles

    import asyncio
    articles = asyncio.run(acquire())
    max_posts = cfg.get("publisher", {}).get("max_posts_per_cycle", 3)
    logger.info("✅ %d خبر جديد — نختار %d", len(articles), max_posts)

    if not articles:
        logger.info("ℹ️ لا توجد أخبار جديدة")
        return {"cycle": cycle_id, "published": 0}

    # 2. Quality Engine Layer
    logger.info("🧠 Layer 2: Quality Engine...")
    from yjcryptonews.models.source import Source, SourceType, SourceStatus, ArticleStatus
    
    # Build proper source map from the config sources
    source_map = {}
    for s in cfg.get("sources", {}).get("rss_feeds", []):
        source_map[_src_id(s["url"])] = Source(
            id=_src_id(s["url"]),
            name=s.get("name", s["url"]),
            url=s["url"],
            type=SourceType.RSS.value,
            trust_score=s.get("trust_score", 85),
            status=SourceStatus.ACTIVE.value,
        )
    
    async def quality_pipeline(arts):
        # Score articles
        arts = await score_articles(arts, source_map, arts)
        # Filter by quality (handle None scores)
        arts = [a for a in arts if a.quality_score and float(a.quality_score) >= 60]
        # Fact check
        arts = await fact_check_articles(arts)
        # Deduplicate against existing articles in database (not against self)
        from yjcryptonews import database
        existing_articles = database.get_recent_articles(limit=1000)  # We'll add this function
        arts, _ = await deduplicate_articles(arts, existing_articles)
        return arts

    articles = asyncio.run(quality_pipeline(articles))
    
    if not articles:
        logger.info("ℹ️ لا توجد أخبار اجتازت فحص الجودة")
        return {"cycle": cycle_id, "published": 0}

    logger.info("✅ %d خبر اجتاز فحص الجودة", len(articles))

    # 3. AI Processing Layer (always enabled for v3)
    logger.info("🤖 Layer 3: AI Processing...")
    # Only process the top articles we'll actually publish
    articles_to_process = articles[:max_posts]
    logger.info(f"Processing top {len(articles_to_process)} articles for AI")
    processed_articles = asyncio.run(run_ai_pipeline(articles_to_process))
    logger.info("✅ AI Processing complete")
    
    # Replace the processed articles in the list
    articles = processed_articles + articles[max_posts:]

    # 4. Publishing Layer
    logger.info("📤 Layer 4: Publishing...")
    published = 0
    for i, item in enumerate(articles[:max_posts]):
        logger.info("📄 (%d/%d) %s...", i + 1, len(articles[:max_posts]), item.title[:80])

        if i > 0:
            spread_delay()

        # Use new AI translator results (already translated by AI pipeline)
        title_ar = item.translated_title or item.title
        body_ar = item.translated_content or item.summary or ""
        summary = item.summary or ""

        if not title_ar or title_ar == item.title:
            logger.warning("❌ Failed translation — skipping")
            continue

        logger.info("📝 %s...", title_ar[:80])

        # Quality check - use body_ar with summary fallback
        quality_ok = True
        if not body_ar or len(body_ar) < 50:
            body_ar = summary
            if not body_ar or len(body_ar) < 50:
                logger.warning("❌ Quality failed: summary too short")
                quality_ok = False
        if len(title_ar) < 10:
            logger.warning("❌ Quality failed: title too short")
            quality_ok = False

        if not quality_ok:
            continue

        # Clean banned words
        removed_any = False
        banned_words = ["الجدير بالذكر", "جدير بالذكر", "📰"]
        for bw in banned_words:
            if bw in title_ar:
                title_ar = title_ar.replace(bw, "").strip()
                removed_any = True
            if bw in body_ar:
                body_ar = body_ar.replace(bw, "").strip()
                removed_any = True
        if "حيث " in title_ar or " حيث" in title_ar:
            title_ar = title_ar.replace("حيث ", "").replace(" حيث", "").strip()
            removed_any = True
        if "حيث " in body_ar or " حيث" in body_ar:
            body_ar = body_ar.replace("حيث ", "").replace(" حيث", "").strip()
            removed_any = True

        if removed_any:
            logger.info("🧹 تم تنظيف المنشور من الكلمات الممنوعة")

        if body_ar and title_ar in body_ar:
            logger.warning("⚠️ تحذير: العنوان مكرر في الملخص")

        # Publish using legacy publisher
        item_dict = {
            "title": item.title,
            "summary": item.summary or item.translated_content or "",
            "url": item.url,
            "source": item.metadata.get("source_name", "Unknown"),
        }
        t = {"title_ar": title_ar, "body_ar": body_ar}
        results = publisher.publish(item_dict, t)

        for r in results:
            ch = r["channel"]
            status = "success" if r["status"] == "success" else "failed"
            try:
                database.log_publish(
                    cycle_id=cycle_id,
                    channel_id=ch["id"],
                    title=item.title,
                    news_url=item.url,
                    status=status,
                )
            except Exception as e:
                logger.error("❌ Failed to log publish: %s", e)
            if status == "success":
                published += 1
                try:
                    database.mark_seen(item.url, item.title)
                except Exception as e:
                    logger.error("❌ Failed to mark_seen: %s", e)

    # 5. Market Analysis
    market_snapshot = None
    if cfg.get("market", {}).get("enabled", True):
        logger.info("📊 تحليل السوق...")
        market_snapshot = market.get_market_snapshot()
        if market_snapshot:
            logger.info("✅ تم جلب بيانات السوق")

    if market_snapshot:
        logger.info("📊 نشر تحليل السوق...")
        channels = database.get_channels(active_only=True)
        for ch in channels:
            ok = publisher._send(ch["chat_id"], market_snapshot)
            if ok:
                logger.info("✅ %s: تحليل السوق", ch.get("title", ch["chat_id"]))
            else:
                logger.error("❌ %s: فشل", ch.get("title", ch["chat_id"]))
            try:
                database.log_publish(
                    cycle_id=cycle_id,
                    channel_id=ch["id"],
                    title="📊 تحليل السوق",
                    status="success" if ok else "failed",
                )
            except Exception as e:
                logger.error("❌ فشل تسجيل تحليل السوق: %s", e)

    logger.info("=" * 50)
    logger.info("✅ انتهت الدورة v3: %d منشورات", published)
    logger.info("=" * 50)
    return {"cycle": cycle_id, "published": published}


def run_cycle():
    """دورة كاملة: جلب → فلترة ذكية → ترجمة → نشر (الأصلي للتوافق الخلفي)"""
    return run_cycle_v3()


def run_daily_summary():
    """تقرير مسائي شامل"""
    logger = get_logger("summary")
    cfg = config
    cycle_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    logger.info("=" * 50)
    logger.info("📊 تقرير مسائي #%s", cycle_id)
    logger.info("=" * 50)

    snapshot = market.get_market_snapshot()
    recent = database.get_recent_publishes(limit=10)

    lines = ["📊 **التقرير المسائي**\n"]

    if snapshot:
        lines.append(snapshot)
        lines.append("")

    if recent:
        lines.append("📰 **أبرز أخبار اليوم**")
        for r in recent:
            title = r.get("item_title", "")
            if title and title not in ("📊 تحليل السوق", "📊 التقرير المسائي"):
                short = title[:60] + "..." if len(title) > 60 else title
                lines.append(f"• {short}")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━")
    lines.append("#تقرير_مسائي #كريبتو #تحليل_السوق")

    post = "\n".join(lines)

    from yjcryptonews import publisher as pub
    channels = database.get_channels(active_only=True)
    for ch in channels:
        ok = pub._send(ch["chat_id"], post)
        st = "success" if ok else "failed"
        try:
            database.log_publish(cycle_id, ch["id"], "📊 التقرير المسائي", st)
        except Exception as e:
            logger.error("❌ فشل تسجيل التقرير المسائي: %s", e)
        logger.info("%s %s", "✅" if ok else "❌", ch.get("title", ch["chat_id"]))

    return {"cycle": cycle_id, "published": len(channels)}


def cmd_prepare():
    """تحضير 10 أخبار اليوم — مرة يومياً"""
    logger = get_logger("prepare")
    cfg = config
    cycle_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    logger.info("=" * 50)
    logger.info("📰 تحضير أخبار اليوم #%s", cycle_id)
    logger.info("=" * 50)

    seen_urls = database.get_seen_urls(days=7)
    logger.info("📚 %d رابط منشور سابقاً في الذاكرة", len(seen_urls))

    logger.info("📡 جلب الأخبار من كل المصادر...")
    original_window = cfg.get("scheduler", {}).get("news_window_hours", 12)
    cfg.setdefault("scheduler", {})["news_window_hours"] = max(24, original_window)

    items = fetcher.fetch_all(seen_urls=seen_urls, cfg=cfg)

    target_count = cfg.get("publisher", {}).get("max_posts_per_cycle", 10)
    logger.info("✅ %d خبر جديد — نختار %d", len(items), target_count)

    if not items:
        logger.info("ℹ️ لا توجد أخبار جديدة اليوم")
        return {"cycle": cycle_id, "prepared": 0}

    logger.info("🧠 تقييم ذكي للأخبار...")
    top_items = legacy_filter.rank_news(items, top_n=target_count + 5)

    if not top_items:
        logger.info("ℹ️ لا توجد أخبار ذات صلة")
        return {"cycle": cycle_id, "prepared": 0}

    logger.info("✅ تم اختيار %d خبر", len(top_items))
    for it in top_items[:target_count]:
        score = it.get("_ai_score", "?")
        logger.info("[%s] %s: %s", score, it["source"], it["title"][:70])

    prepared = []
    selected = top_items[:target_count]

    for i, item in enumerate(selected):
        logger.info("📄 (%d/%d) %s...", i + 1, len(selected), item["title"][:80])

        if i > 0:
            spread_delay()

        logger.info("🔄 جاري الترجمة...")
        translated = legacy_translator.translate(item["title"], item.get("summary", ""))
        title_ar = translated.get("title_ar", "")

        if not title_ar or title_ar == item["title"]:
            logger.warning("❌ فشلت الترجمة — تخطي الخبر")
            continue

        logger.info("📝 %s...", title_ar[:80])

        prepared.append({
            "index": i,
            "original_title": item["title"],
            "url": item.get("url", ""),
            "source": item["source"],
            "summary": item.get("summary", ""),
            "translated": translated,
            "published": False,
            "_queue_date": datetime.now().strftime("%Y-%m-%d"),
        })
        try:
            database.mark_seen(item.get("url", ""), item["title"])
        except Exception as e:
            logger.error("❌ فشل تسجيل mark_seen في prepare: %s", e)

    if prepared:
        daily_queue.save(prepared)
        logger.info("✅ تم تجهيز %d أخبار لليوم", len(prepared))
    else:
        logger.info("ℹ️ لم يتم تجهيز أي خبر — الطابور فارغ")

    logger.info("=" * 50)
    logger.info("✅ انتهى التحضير: %d خبر", len(prepared))
    logger.info("=" * 50)
    return {"cycle": cycle_id, "prepared": len(prepared)}


def cmd_publish_next():
    """نشر الخبر التالي من الطابور اليومي"""
    logger = get_logger("publish_next")
    cycle_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    logger.info("=" * 50)
    logger.info("📤 نشر الخبر التالي #%s", cycle_id)
    logger.info("=" * 50)

    next_item = daily_queue.get_next()
    if not next_item:
        stats = daily_queue.get_stats()
        if stats["total"] == 0:
            logger.info("ℹ️ لا يوجد طابور اليوم — نفذ الأمر prepare أولاً")
        else:
            logger.info("ℹ️ تم نشر كل الأخبار لليوم (%d/%d)", stats["published"], stats["total"])
        return {"cycle": cycle_id, "published": 0}

    item_index = next_item.get("index", 0)
    translated = next_item.get("translated", {})

    title_ar = translated.get("title_ar", "")
    body_ar = translated.get("body_ar", "")

    quality_ok = True
    if not body_ar or len(body_ar) < 20:
        logger.warning("❌ فشل فحص الجودة: الملخص قصير جداً")
        quality_ok = False
    if len(title_ar) < 10:
        logger.warning("❌ فشل فحص الجودة: العنوان قصير جداً")
        quality_ok = False

    if not quality_ok:
        logger.warning("❌ تخطي الخبر رقم %d — فشل فحص الجودة", item_index + 1)
        daily_queue.mark_published(item_index)
        return {"cycle": cycle_id, "published": 0, "skipped": True}

    item = {
        "title": next_item["original_title"],
        "url": next_item.get("url", ""),
        "summary": next_item.get("summary", ""),
        "source": next_item.get("source", ""),
    }

    logger.info("📤 نشر: %s...", title_ar[:60])
    results = publisher.publish(item, translated)

    published_count = 0
    for r in results:
        ch = r["channel"]
        status = "success" if r["status"] == "success" else "failed"
        try:
            database.log_publish(
                cycle_id=cycle_id,
                channel_id=ch["id"],
                title=next_item["original_title"],
                news_url=next_item.get("url", ""),
                status=status,
            )
        except Exception as e:
            logger.error("❌ فشل تسجيل log_publish في publish_next: %s", e)
        if status == "success":
            published_count += 1

    if published_count > 0:
        daily_queue.mark_published(item_index)
        logger.info("✅ تم النشر في %d قناة", published_count)
    else:
        logger.warning("❌ فشل النشر — الطابور لم يتغير")

    delay = config.load().get("publisher", {}).get("delay_between_posts", 120)
    if delay > 0:
        logger.info("⏳ انتظار %d ثانية قبل الخروج...", delay)
        time.sleep(delay)

    logger.info("=" * 50)
    logger.info("✅ تم")
    logger.info("=" * 50)
    return {"cycle": cycle_id, "published": published_count}


def cmd_daily_stats():
    """إحصائيات الطابور اليومي"""
    stats = daily_queue.get_stats()
    print(f"\n📊 إحصائيات الطابور اليومي:")
    print(f"   📰 إجمالي: {stats['total']}")
    print(f"   ✅ منشور: {stats['published']}")
    print(f"   ⏳ متبقي: {stats['pending']}")
    print(f"   📅 التاريخ: {stats['date']}")
    return stats


def cmd_daily_clear():
    """مسح الطابور اليومي"""
    daily_queue.clear()
    print("🗑️ تم مسح الطابور اليومي")


def cmd_channels(args):
    """إدارة القنوات"""
    from yjcryptonews import database as db

    if len(args) < 2:
        print("\n📋 القنوات:")
        print("-" * 40)
        for ch in db.get_channels():
            status = "✅" if ch["is_active"] else "⛔"
            name = ch.get("title") or ch.get("username") or ch["chat_id"]
            print(f"  {status} {name}")
            print(f"     ID: {ch['chat_id']}")
        return

    action = args[1]
    if action == "add" and len(args) >= 3:
        chat_id = args[2]
        username = args[3] if len(args) > 3 else ""
        title = args[4] if len(args) > 4 else ""
        db.add_channel(chat_id, username, title)
        print(f"✅ تم إضافة القناة {chat_id}")

    elif action == "remove" and len(args) >= 3:
        db.remove_channel(args[2])
        print(f"✅ تم حذف القناة {args[2]}")

    elif action == "toggle" and len(args) >= 3:
        db.toggle_channel(args[2])
        ch = db.get_channel(args[2])
        status = "🟢 نشط" if ch and ch["is_active"] else "🔴 متوقف"
        print(f"✅ القناة {args[2]}: {status}")

    else:
        print("""
📋 أوامر القنوات:
  python bot.py channels                  ← عرض القنوات
  python bot.py channels add <chat_id>    ← إضافة قناة
  python bot.py channels remove <chat_id> ← حذف قناة
  python bot.py channels toggle <chat_id> ← تشغيل/إيقاف
""")


def cmd_hourly(args):
    """⏰ تشغيل الدورة الساعة (لل cron: كل ساعة) - خبر واحد طازج = ترجمة واحدة = نشر"""
    import asyncio
    from yjcryptonews.lib.scheduler import run_hourly_cycle
    logger = get_logger("hourly")
    logger.info("⏰ Running hourly single-article cycle...")
    result = asyncio.run(run_hourly_cycle())
    logger.info(f"✅ Hourly cycle result: {result}")
    return result


def cmd_breaking_check(args):
    """🚨 فحص عاجل فقط (لل cron المتكرر: كل 15-30 دقيقة) - يكتشف وينشر خبر واحد عاجل"""
    import asyncio
    from yjcryptonews.lib.scheduler import run_breaking_check
    logger = get_logger("breaking_check")
    logger.info("🔍 Checking for breaking news...")
    result = asyncio.run(run_breaking_check())
    logger.info(f"✅ Breaking check result: {result}")
    return result


def cmd_prepare_hourly(args):
    """🔍-preview ما سيُختار للساعة القادمة (بدون نشر)"""
    import asyncio
    from yjcryptonews.lib.scheduler import HourlySingleArticleScheduler
    logger = get_logger("prepare_hourly")
    logger.info("🔍 Previewing next hourly article...")
    
    async def preview():
        scheduler = HourlySingleArticleScheduler()
        
        # Check breaking first (ALL verified)
        breaking = await scheduler.detect_all_verified_breaking()
        if breaking:
            best = breaking[0]
            logger.info(f"🚨 VERIFIED BREAKING: {best.source_count} sources | "
                       f"Impact: {best.market_impact_score:.2f} | "
                       f"Quality: {best.avg_quality:.1f} | "
                       f"Coins: {best.coins_affected} | Action: {best.action_type} | "
                       f"{best.primary_article.title[:80]}")
            return {
                "type": "breaking", 
                "title": best.primary_article.title, 
                "sources": best.source_count,
                "market_impact": best.market_impact_score,
                "avg_quality": best.avg_quality,
                "coins": best.coins_affected,
                "action": best.action_type
            }
        
        # Regular: get best single
        articles = await scheduler.acquire_all_articles(hours_back=2)
        articles = await scheduler.quality_filter(articles)
        if articles:
            best = articles[0]
            logger.info(f"📰 Regular best: {best.title[:80]} (score: {best.quality_score})")
            return {"type": "hourly", "title": best.title, "score": best.quality_score}
        
        logger.info("No articles found")
        return {"type": "none"}
    
    return asyncio.run(preview())


def cmd_run(args):
    """تشغيل دورة واحدة"""
    run_cycle()


def cmd_summary():
    """تشغيل التقرير المسائي"""
    run_daily_summary()


def cmd_urgent():
    """🚨 دورة عاجلة: فحص سريع كل 5 دقايق"""
    urgent.run_urgent_check()


def cmd_v3(args):
    """🚀 تشغيل دورة v3 الكاملة مع المعمارية الجديدة"""
    return run_cycle_v3()


def main():
    logger = get_logger("main")

    setup_logging()
    cleanup_old_logs(days=14)
    database.init_db()

    if len(sys.argv) < 2:
        print("""
🤖 YJCryptoNews v3.0 - نظام نشر الأخبار الذكي (توفير توكنات)

أوامر رئيسية:
  python bot.py run              ← تشغيل دورة واحدة (v3: كامل الطبقات)
  python bot.py v3               ← 🚀 تشغيل دورة v3 (المعمارية الجديدة 4 طبقات)
  python bot.py urgent           ← 🚨 دورة عاجلة (فحص 5+ مصادر = نشر فوري)

أوامر النشر بالساعة (موفر توكنات - خبر واحد = ترجمة واحدة):
  python bot.py hourly           ← ⏰ الدورة الرئيسية: خبر واحد طازج = ترجمة واحدة = نشر (cron كل ساعة)
  python bot.py breaking_check   ← 🚨 فحص عاجل متكرر (cron كل 15-30 دقيقة) - ينشر فوراً لو عاجل
  python bot.py prepare_hourly   ← 🔍 معاينة ما سيُختار للساعة القادمة (بدون نشر)

أوامر الطابور اليومي (تقليدي):
  python bot.py prepare          ← تحضير 10 أخبار اليوم (مرة يومياً 8 صباحاً)
  python bot.py publish_next     ← نشر الخبر التالي من الطابور
  python bot.py daily_stats      ← إحصائيات الطابور اليومي
  python bot.py daily_clear      ← مسح الطابور اليومي

أوامر أخرى:
  python bot.py channels         ← إدارة القنوات
  python bot.py summary          ← تقرير مسائي
  python bot.py run              ← تشغيل دورة واحدة (v3)
""")
        return

    command = sys.argv[1]
    args = sys.argv[1:]

    commands = {
        "run": cmd_run,
        "v3": cmd_v3,
        "urgent": cmd_urgent,
        "hourly": cmd_hourly,          # ⏰ Main hourly: 1 article = 1 translation = publish
        "breaking_check": cmd_breaking_check,  # 🚨 Frequent check for breaking news
        "prepare_hourly": cmd_prepare_hourly,  # 🔍 Preview next article
        "prepare": cmd_prepare,
        "publish_next": cmd_publish_next,
        "daily_stats": cmd_daily_stats,
        "daily_clear": cmd_daily_clear,
        "channels": cmd_channels,
        "summary": cmd_summary,
    }

    if command in commands:
        commands[command](args)
    else:
        print(f"❌ أمر غير معروف: {command}")
        print("استخدم: python bot.py بدون معاملات لرؤية قائمة الأوامر")


if __name__ == "__main__":
    main()