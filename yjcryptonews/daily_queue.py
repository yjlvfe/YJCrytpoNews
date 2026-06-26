"""إدارة طابور الأخبار اليومي — تخزين 10 أخبار محضّرة ونشرها تباعاً"""
import json
from pathlib import Path
from datetime import datetime
from .log import get_logger

logger = get_logger("daily_queue")

QUEUE_FILE = Path(__file__).parent.parent / ".daily_queue.json"


def save(items: list):
    """حفظ قائمة الأخبار المجهزة"""
    data = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "generated_at": datetime.now().isoformat(),
        "items": items,
    }
    QUEUE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("✅ حفظ %d خبر في الطابور اليومي", len(items))


def load() -> list:
    """تحميل قائمة الأخبار"""
    if not QUEUE_FILE.exists():
        return []
    try:
        data = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
        return data.get("items", [])
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("⚠️ ملف الطابور تالف: %s", e)
        return []


def get_next() -> dict | None:
    """الحصول على أول خبر غير منشور في الطابور"""
    items = load()
    for item in items:
        if not item.get("published", False):
            return item
    return None


def mark_published(index: int):
    """تحديد خبر كمنشور"""
    items = load()
    if 0 <= index < len(items):
        items[index]["published"] = True
        items[index]["published_at"] = datetime.now().isoformat()
        save(items)
        logger.info("📌 تم تحديث الخبر %d كمنشور", index + 1)
        return True
    return False


def get_stats() -> dict:
    """إحصائيات عن الطابور"""
    items = load()
    total = len(items)
    published = sum(1 for i in items if i.get("published", False))
    pending = total - published
    return {
        "total": total,
        "published": published,
        "pending": pending,
        "date": items[0].get("_queue_date", "") if items else "",
    }


def clear():
    """مسح الطابور"""
    if QUEUE_FILE.exists():
        QUEUE_FILE.unlink()
        logger.info("🗑️ تم مسح الطابور اليومي")
