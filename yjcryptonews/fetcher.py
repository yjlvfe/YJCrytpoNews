"""جلب الأخبار من مصادر RSS — متعدد المصادر (كريبتو + سياسي + مالي) + منع التكرار"""
import hashlib
import re
import difflib
import socket
import feedparser
from datetime import datetime, timezone, timedelta
from typing import Optional
from . import config
from .log import get_logger

logger = get_logger("fetcher")

# User-Agent ثابت — بعض المصادر ترفض الطلبات بدونه
USER_AGENT = "YJCryptoNews/1.0 (+https://github.com/yjcryptonews; news aggregator)"
RSS_TIMEOUT = 15  # ثانية كحد أقصى لكل مصدر
# Phase 2: hard cap (seconds) for any single RSS fetch — guards against feeds
# that ignore urllib's timeout setting.
RSS_FETCH_HARD_CAP = 20

# كلمات مفتاحية للكشف عن المحتوى المؤثر على الأسواق المالية
KEYWORDS = [
    # 🪙 كريبتو
    "bitcoin", "btc", "ethereum", "eth", "crypto", "blockchain", "defi", "nft",
    "token", "coin", "wallet", "mining", "staking", "altcoin", "web3", "dex",
    "exchange", "binance", "coinbase", "solana", "sol", "xrp", "ripple",
    "cardano", "ada", "polygon", "matic", "avalanche", "avax", "chainlink",
    "uniswap", "aave", "tether", "usdt", "usdc", "stablecoin",
    "dogecoin", "doge", "shiba", "meme coin",
    "etf", "halving", "whale",
    "layer 2", "l2", "rollup", "zk", "proof of stake", "proof of work",
    "on-chain", "mainnet", "tokenomics", "airdrop", "ico",
    "bridge", "oracle", "validator", "fork", "lightning network",
    "grayscale", "blackrock", "fidelity", "microstrategy",
    "crypto.com", "kraken", "okx", "bybit",
    "كريبتو", "بيتكوين", "إيثريوم", "بلوكتشين", "عملات رقمية",

    # 📊 اقتصاد + أسهم
    "stock market", "stock", "share", "equity", "nasdaq", "s&p 500", "dow jones",
    "dji", "nyse", "index", "rally", "bull market", "bear market",
    "gdp", "economic growth", "recession", "inflation", "cpi", "ppi",
    "interest rate", "rate hike", "rate cut", "federal reserve", "fed",
    "central bank", "monetary policy", "tightening", "quantitative easing",
    "treasury", "bond yield", "yield curve", "securities",
    "earnings", "revenue", "profit", "quarterly report", "ipo",
    "merger", "acquisition", "liquidity", "capital markets",
    "investor", "investment", "portfolio", "fund",
    "bank", "banking", "financial", "finance",
    "economy", "economic", "trade deficit", "trade war", "tariff",
    "oil", "crude", "energy", "gas", "commodity", "gold", "silver",
    "forex", "currency", "dollar", "usd",

    # 🏛️ سياسة مؤثرة في الأسواق
    "trade deal", "tax", "tax cut", "stimulus", "government spending",
    "regulation", "regulatory", "deregulation", "antitrust",
    "tariff", "sanctions", "war", "conflict", "ceasefire",
    "congress", "senate", "legislation", "bill", "policy",
    "sec", "cfpb", "federal",

    # 🤖 تكنولوجيا مؤثرة في الأسواق
    "ai", "artificial intelligence", "machine learning", "deep learning",
    "chip", "semiconductor", "nvidia", "amd", "intel",
    "data center", "cloud", "aws", "microsoft", "google", "apple",
    "meta", "amazon", "big tech", "tech",
    "software", "hardware", "automation", "robotics",
    "5g", "quantum", "cybersecurity",
    "startup", "venture capital", "vc funding", "unicorn",
]

# كلمات لاستبعاد المحتوى غير المالي
EXCLUDE_KEYWORDS = [
    "sport", "football", "soccer", "basketball", "tennis",
    "celebrity", "movie", "film review", "tv show",
    "weather", "recipe", "fashion", "music album",
    "game score", "playoff", "championship",
    "royal family", "prince", "princess", "wedding",
    "earthquake", "hurricane", "natural disaster",
    "obituary", "death", "funeral",
]


def _hash_url(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()


def _normalize(text: str) -> str:
    """تطبيع النص للمقارنة — إزالة علامات ورموز ومسافات زائدة"""
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)  # إزالة علامات الترقيم
    text = re.sub(r"\s+", " ", text).strip()  # توحيد المسافات
    return text


def _is_duplicate(title: str, existing_titles: list, threshold: float = 0.6) -> bool:
    """فحص إذا كان الخبر مكرر بناءً على تشابه العنوان"""
    norm_title = _normalize(title)
    if not norm_title:
        return False

    for existing in existing_titles:
        norm_existing = _normalize(existing)
        if not norm_existing:
            continue
        # إذا title موجود داخل الخبر الآخر أو العكس
        if norm_title in norm_existing or norm_existing in norm_title:
            return True
        # تشابه بين العناوين
        ratio = difflib.SequenceMatcher(None, norm_title, norm_existing).ratio()
        if ratio > threshold:
            return True
    return False


def _is_relevant(title: str, summary: str) -> bool:
    """فحص إذا المحتوى قد يؤثر على الكريبتو/الأسواق"""
    text = f"{title} {summary}".lower()

    # استبعاد محتوى غير مالي
    for kw in EXCLUDE_KEYWORDS:
        if kw in text:
            return False

    # فلترة الكلمات المفتاحية
    return any(kw in text for kw in KEYWORDS)


def fetch_all(seen_urls: Optional[set] = None, cfg: Optional[dict] = None) -> list:
    """جلب الأخبار من كل المصادر النشطة — مع منع التكرار

    Args:
        seen_urls: set of URLs already published (for dedup)
        cfg: optional pre-loaded config (avoids re-reading config.yaml
             when the caller already has it in memory)
    """
    if cfg is None:
        cfg = config.load()
    sources = cfg.get("sources", [])
    window_hours = cfg.get("scheduler", {}).get("news_window_hours", 12)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    seen = seen_urls or set()
    items = []
    seen_titles = []  # للكشف عن الأخبار المتشابهة

    for src in sources:
        if not src.get("active", True):
            continue

        try:
            # Phase 2: feedparser uses urllib under the hood. We pass the timeout
            # via socket.create_connection monkey-patch (the only reliable way
            # to enforce a hard cap on urllib-based fetchers). We restore the
            # original immediately after the call to avoid global state leaks.
            # This is scoped to a single thread and only affects the call below.
            # NOTE: urllib3 may call socket.create_connection with up to 3
            # positional args (address, timeout, source_address) on some
            # Python versions, so we accept *args and forward them, pinning
            # the timeout if the caller left it at the default sentinel.
            _orig_create_connection = socket.create_connection
            def _bounded_create_connection(*args, **kwargs):
                # Pin our timeout if caller didn't set one explicitly.
                if "timeout" not in kwargs and len(args) < 2:
                    kwargs["timeout"] = RSS_TIMEOUT
                elif len(args) >= 2 and "timeout" not in kwargs:
                    a = list(args)
                    a[1] = RSS_TIMEOUT
                    args = tuple(a)
                return _orig_create_connection(*args, **kwargs)
            socket.create_connection = _bounded_create_connection
            try:
                feed = feedparser.parse(
                    src["url"],
                    agent=USER_AGENT,
                )
            finally:
                socket.create_connection = _orig_create_connection

            if feed.bozo and not feed.entries:
                logger.warning("مصدر مشبوه [%s]: %s", src["name"], feed.bozo_exception or "unknown")
                continue
            for entry in feed.entries[:15]:
                url = entry.get("link", "").strip()
                if not url or _hash_url(url) in seen:
                    continue

                published = entry.get("published_parsed") or entry.get("updated_parsed")
                if published:
                    pub_dt = datetime(*published[:6], tzinfo=timezone.utc)
                    if pub_dt < cutoff:
                        continue

                title = entry.get("title", "").strip()
                if not title:
                    continue

                # منع التكرار: نفس الخبر من مصدر آخر
                if _is_duplicate(title, seen_titles):
                    continue

                summary = entry.get("summary", "") or entry.get("description", "") or ""
                summary = re.sub(r"<[^>]+>", "", summary).strip()[:800]

                # فلترة: هل المحتوى مؤثر على الكريبتو/الأسواق؟
                if not _is_relevant(title, summary):
                    continue

                items.append({
                    "title": title,
                    "url": url,
                    "summary": summary,
                    "source": src["name"],
                    "lang": src.get("lang", "en"),
                    "published": pub_dt.isoformat() if published else "",
                })
                seen.add(_hash_url(url))
                seen_titles.append(title)  # نضيفه للمقارنة
        except Exception as e:
            # وقت انتهاء أو خطأ اتصال — مش حرج، المصادر أحياناً تعلق
            err_str = str(e)
            if "timed out" in err_str or "timeout" in err_str or "Connection" in err_str:
                logger.warning("RSS timeout [%s]: %s", src["name"], err_str[:80])
            else:
                logger.warning("RSS error [%s]: %s", src["name"], err_str[:80])

    # ترتيب من الأحدث للأقدم
    items.sort(key=lambda x: x.get("published", ""), reverse=True)
    return items
