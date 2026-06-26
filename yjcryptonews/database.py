"""قاعدة البيانات - SQLite لإدارة القنوات والسجل"""
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path("/root/YJCryptoNews-data.db")


def get_conn():
    """الحصول على اتصال بقاعدة البيانات — مع busy_timeout صريح (defense in depth)"""
    # timeout=30.0 على مستوى Python يضمن انتظار 30 ثانية عند القفل قبل رفع OperationalError
    # PRAGMA busy_timeout يضاعف الحماية على مستوى SQLite نفسه
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def init_db():
    """إنشاء الجداول المطلوبة إن لم توجد"""
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL UNIQUE,
            username TEXT,
            title TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS publications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER NOT NULL,
            news_title TEXT NOT NULL,
            news_url TEXT,
            source TEXT,
            translated_title TEXT,
            published_at TEXT DEFAULT (datetime('now')),
            status TEXT DEFAULT 'success',
            FOREIGN KEY (channel_id) REFERENCES channels(id)
        );

        CREATE TABLE IF NOT EXISTS publish_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_id TEXT NOT NULL,
            channel_id INTEGER,
            item_title TEXT,
            news_url TEXT,
            status TEXT,
            error TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        -- جدول لتتبع الأخبار المنشورة سابقاً (لمنع التكرار)
        CREATE TABLE IF NOT EXISTS seen_news (
            url_hash TEXT PRIMARY KEY,
            news_url TEXT NOT NULL,
            title TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        -- فهارس لتسريع الاستعلامات
        CREATE INDEX IF NOT EXISTS idx_publish_log_cycle ON publish_log(cycle_id);
        CREATE INDEX IF NOT EXISTS idx_publish_log_created ON publish_log(created_at);
        CREATE INDEX IF NOT EXISTS idx_seen_news_created ON seen_news(created_at);
        CREATE INDEX IF NOT EXISTS idx_publications_published ON publications(published_at);
    """)
        conn.commit()


# ─── Channel Management ─────────────────────────────────


def add_channel(chat_id: str, username: str = "", title: str = ""):
    """إضافة قناة جديدة"""
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO channels (chat_id, username, title) VALUES (?, ?, ?)",
                (chat_id, username, title),
            )
            conn.commit()
        return True
    except Exception as e:
        return False


def remove_channel(chat_id: str):
    """حذف قناة"""
    with get_conn() as conn:
        conn.execute("DELETE FROM channels WHERE chat_id = ?", (chat_id,))
        conn.commit()


def toggle_channel(chat_id: str, active: bool = None):
    """تشغيل/إيقاف النشر في قناة"""
    with get_conn() as conn:
        if active is not None:
            conn.execute("UPDATE channels SET is_active = ? WHERE chat_id = ?", (1 if active else 0, chat_id))
        else:
            conn.execute("UPDATE channels SET is_active = CASE WHEN is_active THEN 0 ELSE 1 END WHERE chat_id = ?", (chat_id,))
        conn.commit()


def get_channels(active_only: bool = False) -> list:
    """جلب كل القنوات"""
    with get_conn() as conn:
        if active_only:
            rows = conn.execute("SELECT * FROM channels WHERE is_active = 1 ORDER BY id").fetchall()
        else:
            rows = conn.execute("SELECT * FROM channels ORDER BY is_active DESC, id").fetchall()
    return [dict(r) for r in rows]


def get_channel(chat_id: str) -> dict | None:
    """جلب قناة واحدة"""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM channels WHERE chat_id = ?", (chat_id,)).fetchone()
    return dict(row) if row else None


# ─── Publish Log ──────────────────────────────────────


def log_publish(cycle_id: str, channel_id: int, title: str, status: str, error: str = "", news_url: str = ""):
    """تسجيل عملية نشر"""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO publish_log (cycle_id, channel_id, item_title, news_url, status, error) VALUES (?, ?, ?, ?, ?, ?)",
            (cycle_id, channel_id, title, news_url, status, error),
        )
        conn.commit()


def get_recent_publishes(limit: int = 20) -> list:
    """آخر المنشورات"""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT pl.*, c.title as channel_name, c.username
            FROM publish_log pl
            LEFT JOIN channels c ON c.id = pl.channel_id
            ORDER BY pl.created_at DESC LIMIT ?
        """, (limit,)).fetchall()
    return [dict(r) for r in rows]


# ─── Seen News (لمنع التكرار) ─────────────────────────


def get_seen_urls(days: int = 7) -> set:
    """جلب الـ URLs المنشورة سابقاً لمنع التكرار"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT url_hash FROM seen_news WHERE created_at > datetime('now', ? || ' days')",
            (f"-{days}",),
        ).fetchall()
    return {r["url_hash"] for r in rows}


def get_recent_articles(limit: int = 1000):
    """Get recent articles from publications+publish_log for deduplication"""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT id, news_title as title, news_url as url, source,
                   translated_title, published_at
            FROM publications
            WHERE status = 'success'
            ORDER BY published_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
    
    # publications table has no content column, add empty content
    rows = [dict(r) for r in rows]
    for r in rows:
        r['content'] = ''

    # If publications is empty, fallback to publish_log
    if not rows:
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT id, item_title as title, news_url as url, cycle_id as source,
                       item_title as translated_title, created_at as published_at, '' as content
                FROM publish_log
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,)).fetchall()
        rows = [dict(r) for r in rows]

    # Drop rows with NULL/empty title or url (would crash dedup hashing)
    rows = [r for r in rows if (r.get("title") or "").strip() and (r.get("url") or "").strip()]
    for r in rows:
        if r.get("title") is None:
            r["title"] = ""
        if r.get("url") is None:
            r["url"] = ""

    return rows


def get_last_publish_for_channel_id(channel_id: int, hours: int = 1):
    """Get the last published article for a specific channel within hours"""
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT news_title as title FROM publications
            WHERE channel_id = ? AND published_at > datetime('now', ? || ' hours')
            ORDER BY published_at DESC LIMIT 1
            """,
            (channel_id, f"-{hours}")
        ).fetchone()
    return dict(row) if row else None


def mark_seen(url: str, title: str = ""):
    """تسجيل URL كمنشور سابقاً"""
    import hashlib
    url_hash = hashlib.md5(url.encode()).hexdigest()
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO seen_news (url_hash, news_url, title) VALUES (?, ?, ?)",
            (url_hash, url, title),
        )
        conn.commit()


def is_article_published(url: str) -> bool:
    """Check if an article URL has been published before"""
    import hashlib
    url_hash = hashlib.md5(url.encode()).hexdigest()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM seen_news WHERE url_hash = ?",
            (url_hash,)
        ).fetchone()
    return row is not None
